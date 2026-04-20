"""
トレンド・ステータス判定

責務:
- 3本の移動平均線（5日, 25日, 75日）の状態を判定
- Up / Down / Range / Sideways の4分類

やらないこと:
- 移動平均線自体の計算（TechnicalIndicators が担当）
- エントリー判断（あくまで参考情報として表示）
"""
import pandas as pd
import logging
from typing import Optional

from src.screener import config

logger = logging.getLogger(__name__)

# ステータス定数
STATUS_UP = "Up"           # パーフェクトオーダー（上昇トレンド）
STATUS_DOWN = "Down"       # 逆パーフェクトオーダー（下降トレンド）
STATUS_RANGE = "Range"     # 5日MAと25日MAの乖離3%以内（逆張り推奨）
STATUS_SIDEWAYS = "Sideways"  # ボックス圏（いずれにも該当しない）


class TrendJudge:
    """
    移動平均線の配列状態からトレンドステータスを判定する。

    判定優先順位:
    1. Range: 5日MAと25日MAの乖離が3%以内 → 逆張り推奨
    2. Up: パーフェクトオーダー（SMA_5 > SMA_25 > SMA_75）
    3. Down: 逆パーフェクトオーダー（SMA_5 < SMA_25 < SMA_75）
    4. Sideways: 上記いずれにも該当しない
    """

    def __init__(self, range_threshold_pct: float = config.RANGE_THRESHOLD_PCT):
        self.range_threshold_pct = range_threshold_pct

    def judge(self, df: pd.DataFrame) -> str:
        """
        トレンドステータスを判定

        Args:
            df: SMA_5, SMA_25, SMA_75 を含む指標計算済みDataFrame

        Returns:
            "Up", "Down", "Range", "Sideways" のいずれか
        """
        if df is None or df.empty:
            return STATUS_SIDEWAYS

        last = df.iloc[-1]

        sma_5 = last.get('SMA_5')
        sma_25 = last.get('SMA_25')
        sma_75 = last.get('SMA_75')

        # いずれかのSMAが取得不可の場合
        if any(v is None or pd.isna(v) for v in [sma_5, sma_25, sma_75]):
            return STATUS_SIDEWAYS

        sma_5 = float(sma_5)
        sma_25 = float(sma_25)
        sma_75 = float(sma_75)

        # ゼロ除算防止
        if sma_25 == 0:
            return STATUS_SIDEWAYS

        # --- 判定1: Range ---
        # 5日MAと25日MAの乖離率（絶対値）
        divergence_pct = abs(sma_5 - sma_25) / sma_25 * 100
        if divergence_pct <= self.range_threshold_pct:
            return STATUS_RANGE

        # --- 判定2: Up（パーフェクトオーダー） ---
        if sma_5 > sma_25 > sma_75:
            return STATUS_UP

        # --- 判定3: Down（逆パーフェクトオーダー） ---
        if sma_5 < sma_25 < sma_75:
            return STATUS_DOWN

        # --- 判定4: Sideways ---
        return STATUS_SIDEWAYS
