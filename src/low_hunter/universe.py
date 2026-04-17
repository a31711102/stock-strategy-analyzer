"""
Project-low-hunter: ユニバース選定

責務:
- 日経225銘柄リストから、流動性・ボラティリティ・β値の3条件を
  満たす「デイトレ適性」の高い銘柄を抽出する。

フィルタ条件:
1. 5日平均出来高 ≥ 100万株
2. Norm_ATR(10) ≥ 2.0%
3. β ≥ 1.2

やらないこと:
- 銘柄リストの取得（nikkei225_fetcher.py が担当）
- バックテスト（backtest_engine.py が担当）
"""
import logging
from typing import Dict, List, Tuple

import pandas as pd

from src.low_hunter import config
from src.low_hunter.beta_calculator import BetaCalculator
from src.low_hunter.models import UniverseStock

logger = logging.getLogger(__name__)


class UniverseFilter:
    """ユニバース選定フィルタ"""

    def __init__(
        self,
        min_avg_volume: int = config.MIN_AVG_VOLUME,
        min_norm_atr: float = config.MIN_NORM_ATR,
        min_beta: float = config.MIN_BETA,
    ):
        self.min_avg_volume = min_avg_volume
        self.min_norm_atr = min_norm_atr
        self.min_beta = min_beta

    def apply(
        self,
        stock_list: List[Tuple[str, str]],
        stock_data: Dict[str, pd.DataFrame],
        market_df: pd.DataFrame,
    ) -> List[UniverseStock]:
        """
        日経225銘柄リストにフィルタを適用し、ユニバースを選定する。

        Args:
            stock_list: [(銘柄コード, 銘柄名), ...] のリスト
            stock_data: {銘柄コード: 指標計算済みDataFrame} の辞書
            market_df: 日経平均のOHLCVデータ

        Returns:
            フィルタ通過した UniverseStock のリスト。
        """
        passed: List[UniverseStock] = []
        rejected = {'no_data': 0, 'volume': 0, 'norm_atr': 0, 'beta': 0}

        for code, name in stock_list:
            df = stock_data.get(code)
            if df is None or len(df) < config.MIN_VALID_DAYS:
                rejected['no_data'] += 1
                continue

            last = df.iloc[-1]

            # --- 1. 流動性: 5日平均出来高 ---
            avg_vol = last.get('Volume_MA_5')
            if avg_vol is None or pd.isna(avg_vol) or avg_vol < self.min_avg_volume:
                rejected['volume'] += 1
                continue

            # --- 2. ボラティリティ: Norm_ATR ---
            atr_10 = last.get('ATR_10')
            close = last.get('Close')
            if atr_10 is None or close is None or pd.isna(atr_10) or pd.isna(close) or close <= 0:
                rejected['norm_atr'] += 1
                continue

            norm_atr = float(atr_10) / float(close) * 100.0
            if norm_atr < self.min_norm_atr:
                rejected['norm_atr'] += 1
                continue

            # --- 3. β値 ---
            beta = BetaCalculator.calculate(df, market_df)
            if beta < self.min_beta:
                rejected['beta'] += 1
                continue

            passed.append(UniverseStock(
                code=code,
                name=name,
                beta=round(beta, 3),
                norm_atr=round(norm_atr, 2),
                avg_volume_5d=float(avg_vol),
                prev_close=float(close),
                atr_10=float(atr_10),
            ))

        logger.info(
            f"ユニバース選定完了: {len(passed)}/{len(stock_list)}銘柄通過 "
            f"（除外内訳: データ不足={rejected['no_data']}, "
            f"出来高={rejected['volume']}, "
            f"Norm_ATR={rejected['norm_atr']}, "
            f"β値={rejected['beta']}）"
        )

        return passed
