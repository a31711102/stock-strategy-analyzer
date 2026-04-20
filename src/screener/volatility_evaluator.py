"""
第二段階: ボラティリティ評価

責務:
- Norm_ATR（正規化ATR）の計算とフィルタリング
- RVR（相対ボラ比）の計算
- RVR降順で上位N銘柄を選定

やらないこと:
- ATR自体の計算（TechnicalIndicators が担当）
- ターゲット価格の算出（Stage3 が担当）
"""
import pandas as pd
import numpy as np
import logging
from typing import Optional
from dataclasses import dataclass

from src.screener import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VolatilityEvalParams:
    """ボラティリティ評価パラメータ"""
    min_norm_atr: float = config.MIN_NORM_ATR
    top_n: int = config.TOP_N


@dataclass
class VolatilityScore:
    """1銘柄分のボラティリティ評価結果"""
    code: str
    norm_atr: float   # ATR_10 / Close × 100 (%)
    rvr: float        # ATR_10 / ATR_100 (相対ボラ比)
    atr_10: float     # ATR(10) 絶対値
    atr_100: float    # ATR(100) 絶対値
    close: float      # 直近終値


class VolatilityEvaluator:
    """
    第二段階: ボラティリティ評価

    Stage1を通過した銘柄に対し、
    ボラティリティの急拡大度合いでランキングし上位N銘柄を選定する。
    """

    def __init__(self, params: Optional[VolatilityEvalParams] = None):
        self.params = params or VolatilityEvalParams()

    def evaluate(
        self,
        codes: list[str],
        stock_indicators: dict[str, pd.DataFrame],
    ) -> list[VolatilityScore]:
        """
        ボラティリティ評価を実施し、RVR上位N銘柄を返す

        Args:
            codes: Stage1を通過した銘柄コードリスト
            stock_indicators: {銘柄コード: 指標計算済みDataFrame} の辞書

        Returns:
            RVR降順でソートされた上位N銘柄のVolatilityScoreリスト。
            該当銘柄がない場合は空リスト。
        """
        scores: list[VolatilityScore] = []

        for code in codes:
            df = stock_indicators.get(code)
            if df is None or df.empty:
                continue

            score = self._evaluate_single(code, df)
            if score is not None:
                scores.append(score)

        logger.info(
            f"VolatilityEvaluator: {len(codes)}銘柄 → "
            f"{len(scores)}銘柄（Norm_ATR通過）"
        )
        return scores

    def _evaluate_single(
        self, code: str, df: pd.DataFrame
    ) -> Optional[VolatilityScore]:
        """
        単一銘柄のボラティリティ評価

        Args:
            code: 銘柄コード
            df: 指標計算済みDataFrame

        Returns:
            VolatilityScore。条件未達の場合はNone。
        """
        last = df.iloc[-1]

        # 必要カラムの取得
        atr_10 = last.get('ATR_10')
        atr_100 = last.get('ATR_100')
        close = last.get('Close')

        # データ欠損チェック
        if any(v is None or pd.isna(v) for v in [atr_10, atr_100, close]):
            return None
        if close == 0 or atr_100 == 0:
            return None

        atr_10 = float(atr_10)
        atr_100 = float(atr_100)
        close = float(close)

        # Norm_ATR = ATR_10 / Close × 100
        norm_atr = (atr_10 / close) * 100

        # フィルタ: Norm_ATR ≧ MIN_NORM_ATR
        if norm_atr < self.params.min_norm_atr:
            return None

        # RVR = ATR_10 / ATR_100
        rvr = atr_10 / atr_100

        return VolatilityScore(
            code=code,
            norm_atr=round(norm_atr, 3),
            rvr=round(rvr, 3),
            atr_10=round(atr_10, 2),
            atr_100=round(atr_100, 2),
            close=round(close, 1),
        )
