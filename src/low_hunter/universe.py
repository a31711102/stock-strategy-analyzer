"""
Project-low-hunter: ユニバース選定

責務:
- 日経225銘柄リストから、流動性・ボラティリティ・β値の3条件を
  満たす「デイトレ適性」の高い銘柄を抽出する。
- ヒステリシスにより、閾値境界上の銘柄のチャタリングを防止する。

フィルタ条件（新規採用 / 継続採用）:
1. 5日平均出来高 ≥ 100万株 / ≥ 80万株
2. Norm_ATR(10) ≥ 2.0% / ≥ 1.8%
3. β ≥ 1.2（ヒステリシス対象外）

やらないこと:
- 銘柄リストの取得（nikkei225_fetcher.py が担当）
- バックテスト（backtest_engine.py が担当）
- 前回ユニバースの永続化（呼び出し元が管理）
"""
import logging
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from src.low_hunter import config
from src.low_hunter.beta_calculator import BetaCalculator
from src.low_hunter.models import UniverseStock

logger = logging.getLogger(__name__)


class UniverseFilter:
    """ユニバース選定フィルタ（ヒステリシス対応）"""

    def __init__(
        self,
        min_avg_volume: int = config.MIN_AVG_VOLUME,
        min_norm_atr: float = config.MIN_NORM_ATR,
        min_beta: float = config.MIN_BETA,
        hysteresis_min_avg_volume: int = config.HYSTERESIS_MIN_AVG_VOLUME,
        hysteresis_min_norm_atr: float = config.HYSTERESIS_MIN_NORM_ATR,
    ):
        self.min_avg_volume = min_avg_volume
        self.min_norm_atr = min_norm_atr
        self.min_beta = min_beta
        self.hysteresis_min_avg_volume = hysteresis_min_avg_volume
        self.hysteresis_min_norm_atr = hysteresis_min_norm_atr

    def apply(
        self,
        stock_list: List[Tuple[str, str]],
        stock_data: Dict[str, pd.DataFrame],
        market_df: pd.DataFrame,
        previous_universe_codes: Optional[Set[str]] = None,
    ) -> List[UniverseStock]:
        """
        日経225銘柄リストにフィルタを適用し、ユニバースを選定する。

        前回ユニバースに含まれる銘柄には緩和閾値（ヒステリシス）を適用し、
        新規銘柄には厳格閾値を適用する。

        Args:
            stock_list: [(銘柄コード, 銘柄名), ...] のリスト
            stock_data: {銘柄コード: 指標計算済みDataFrame} の辞書
            market_df: 日経平均のOHLCVデータ
            previous_universe_codes: 前回ユニバースの銘柄コード集合。
                None の場合は全銘柄に厳格閾値を適用（初回実行時）。

        Returns:
            フィルタ通過した UniverseStock のリスト。
        """
        prev_codes = previous_universe_codes or set()
        passed: List[UniverseStock] = []
        rejected = {'no_data': 0, 'volume': 0, 'norm_atr': 0, 'beta': 0}
        new_count = 0
        continued_count = 0

        for code, name in stock_list:
            df = stock_data.get(code)
            if df is None or len(df) < config.MIN_VALID_DAYS:
                rejected['no_data'] += 1
                continue

            is_continuation = code in prev_codes
            last = df.iloc[-1]

            # --- 閾値の選択（ヒステリシス） ---
            vol_threshold = (
                self.hysteresis_min_avg_volume if is_continuation
                else self.min_avg_volume
            )
            atr_threshold = (
                self.hysteresis_min_norm_atr if is_continuation
                else self.min_norm_atr
            )

            # --- 1. 流動性: 5日平均出来高 ---
            avg_vol = last.get('Volume_MA_5')
            if avg_vol is None or pd.isna(avg_vol) or avg_vol < vol_threshold:
                rejected['volume'] += 1
                continue

            # --- 2. ボラティリティ: Norm_ATR ---
            atr_10 = last.get('ATR_10')
            close = last.get('Close')
            if atr_10 is None or close is None or pd.isna(atr_10) or pd.isna(close) or close <= 0:
                rejected['norm_atr'] += 1
                continue

            norm_atr = float(atr_10) / float(close) * 100.0
            if norm_atr < atr_threshold:
                rejected['norm_atr'] += 1
                continue

            # --- 3. β値（ヒステリシス対象外） ---
            beta = BetaCalculator.calculate(df, market_df)
            if beta < self.min_beta:
                rejected['beta'] += 1
                continue

            # --- 通過 ---
            if is_continuation:
                continued_count += 1
            else:
                new_count += 1

            passed.append(UniverseStock(
                code=code,
                name=name,
                beta=round(beta, 3),
                norm_atr=round(norm_atr, 2),
                avg_volume_5d=float(avg_vol),
                prev_close=float(close),
                atr_10=float(atr_10),
            ))

        hysteresis_status = (
            f"新規: {new_count}, 継続: {continued_count}"
            if prev_codes
            else "ヒステリシスなし（初回実行）"
        )
        logger.info(
            f"ユニバース選定完了: {len(passed)}/{len(stock_list)}銘柄通過 "
            f"（{hysteresis_status}）"
            f"（除外内訳: データ不足={rejected['no_data']}, "
            f"出来高={rejected['volume']}, "
            f"Norm_ATR={rejected['norm_atr']}, "
            f"β値={rejected['beta']}）"
        )

        return passed

