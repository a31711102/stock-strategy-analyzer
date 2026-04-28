"""
Project-high-hunter: 悉皆バックテストエンジン（空売り版）

責務:
- 1銘柄に対して61パターン（+1.0%〜+7.0%、0.1%刻み）の
  上昇率バックテストを一括実行し、各パターンの勝率・中央値リターンを算出する。

ロジック（空売り）:
  各営業日 d について:
    target_price[d] = Close[d-1] × (1 + rise_pct / 100)
    is_hit[d]       = High[d] >= target_price[d]
    pnl[d]          = target_price[d] - Close[d]
    is_win[d]       = is_hit[d] AND (pnl[d] > 0)
"""
import logging
from typing import List

import numpy as np
import pandas as pd

from src.high_hunter import config
from src.high_hunter.models import BacktestResultShort

logger = logging.getLogger(__name__)


class BacktestEngineShort:
    """0.1%刻み悉皆バックテストエンジン（空売り）"""

    def __init__(
        self,
        rise_min: float = config.RISE_RANGE_MIN,
        rise_max: float = config.RISE_RANGE_MAX,
        rise_step: float = config.RISE_STEP,
    ):
        # 1.0 から 7.0 まで 0.1 刻みの配列を生成
        self.rise_levels = np.round(
            np.arange(rise_min, rise_max + rise_step / 2, rise_step),
            1,
        )

    def run(self, df: pd.DataFrame) -> List[BacktestResultShort]:
        """
        1銘柄に対して全パターンのバックテストを実行する。

        Args:
            df: OHLCVデータ（最低 config.MIN_VALID_DAYS 日分必要）

        Returns:
            各上昇率パターンの BacktestResultShort リスト（61個）。
            データ不足の場合は空リスト。
        """
        if len(df) < config.MIN_VALID_DAYS:
            return []

        df_bt = df.tail(config.LOOKBACK_DAYS + 1).copy()

        close = df_bt['Close'].values
        high = df_bt['High'].values

        prev_close = close[:-1]  # d-1 の Close
        day_high = high[1:]      # d の High
        day_close = close[1:]    # d の Close

        trading_days = len(prev_close)

        results: List[BacktestResultShort] = []

        for rise_pct in self.rise_levels:
            # 各日の空売り指値 = 前日終値 × (1 + rise_pct / 100)
            target_prices = prev_close * (1.0 + rise_pct / 100.0)

            # 約定判定: その日の高値が指値以上なら約定
            is_hit = day_high >= target_prices

            hit_count = int(np.sum(is_hit))

            if hit_count == 0:
                results.append(BacktestResultShort(
                    rise_pct=float(rise_pct),
                    trading_days=trading_days,
                    hit_count=0,
                    win_count=0,
                    win_rate=0.0,
                    median_return=0.0,
                ))
                continue

            # 約定した日の損益率（空売り: 売値-買戻値）
            hit_targets = target_prices[is_hit]
            hit_closes = day_close[is_hit]
            pnl_pct = (hit_targets - hit_closes) / hit_targets * 100.0

            win_count = int(np.sum(pnl_pct > 0))
            win_rate = win_count / hit_count * 100.0
            median_return = float(np.median(pnl_pct))

            results.append(BacktestResultShort(
                rise_pct=float(rise_pct),
                trading_days=trading_days,
                hit_count=hit_count,
                win_count=win_count,
                win_rate=round(win_rate, 2),
                median_return=round(median_return, 3),
            ))

        return results
