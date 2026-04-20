"""
第一段階フィルタ: 流動性・需給

責務:
- 5日平均出来高による流動性フィルタ
- 出来高急増比（仕手化銘柄排除）
- 信用倍率フィルタ（将来実装用インターフェース）

やらないこと:
- データ取得（呼び出し元が DataFrame を渡す）
- ボラティリティ評価（Stage2 が担当）
"""
import pandas as pd
import numpy as np
import logging
from typing import Optional
from dataclasses import dataclass

from src.screener import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiquidityFilterParams:
    """フィルタパラメータ（テスト時の注入用）"""
    min_avg_volume_5d: int = config.MIN_AVG_VOLUME_5D
    max_volume_ratio: float = config.MAX_VOLUME_RATIO
    credit_ratio_min: float = config.CREDIT_RATIO_MIN
    credit_ratio_max: float = config.CREDIT_RATIO_MAX
    credit_ratio_enabled: bool = config.CREDIT_RATIO_ENABLED


class LiquidityFilter:
    """
    第一段階: 流動性・需給フィルタ

    全銘柄の指標計算済みDataFrameを受け取り、
    流動性と需給の条件を満たす銘柄コードのリストを返す。
    """

    def __init__(self, params: Optional[LiquidityFilterParams] = None):
        self.params = params or LiquidityFilterParams()

    def apply(
        self,
        stock_indicators: dict[str, pd.DataFrame],
    ) -> list[str]:
        """
        全銘柄に流動性・需給フィルタを適用

        Args:
            stock_indicators: {銘柄コード: 指標計算済みDataFrame} の辞書

        Returns:
            フィルタを通過した銘柄コードのリスト
        """
        passed_codes: list[str] = []

        for code, df in stock_indicators.items():
            if df is None or df.empty:
                continue

            if self._passes_filter(df):
                passed_codes.append(code)

        logger.info(
            f"LiquidityFilter: {len(stock_indicators)}銘柄 → "
            f"{len(passed_codes)}銘柄通過"
        )
        return passed_codes

    def _passes_filter(self, df: pd.DataFrame) -> bool:
        """
        単一銘柄のフィルタ判定

        Args:
            df: 指標計算済みDataFrame（最低限 Volume, Volume_MA_5, Volume_MA_10, Volume_MA_100 を含む）

        Returns:
            全条件を満たす場合 True
        """
        last = df.iloc[-1]

        # --- 条件1: 5日平均出来高 ≧ MIN_AVG_VOLUME_5D ---
        vol_ma_5 = last.get('Volume_MA_5')
        if vol_ma_5 is None or pd.isna(vol_ma_5):
            return False
        if vol_ma_5 < self.params.min_avg_volume_5d:
            return False

        # --- 条件2: 出来高急増比 < MAX_VOLUME_RATIO ---
        # Volume_MA_10 / Volume_MA_100 が大きい = 仕手化の兆候
        vol_ma_10 = last.get('Volume_MA_10')
        vol_ma_100 = last.get('Volume_MA_100')
        if vol_ma_10 is not None and vol_ma_100 is not None:
            if pd.notna(vol_ma_10) and pd.notna(vol_ma_100) and vol_ma_100 > 0:
                volume_ratio = vol_ma_10 / vol_ma_100
                if volume_ratio >= self.params.max_volume_ratio:
                    return False

        # --- 条件3: 信用倍率フィルタ（将来実装用） ---
        if self.params.credit_ratio_enabled:
            credit_ratio = last.get('credit_ratio')
            if credit_ratio is not None and pd.notna(credit_ratio):
                if credit_ratio <= self.params.credit_ratio_min:
                    return False
                if credit_ratio >= self.params.credit_ratio_max:
                    return False

        return True
