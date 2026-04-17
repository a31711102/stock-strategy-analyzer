"""
Project-low-hunter: 悉皆バックテストエンジン

責務:
- 1銘柄に対して61パターン（-1.0%〜-7.0%、0.1%刻み）の
  下落率バックテストを一括実行し、各パターンの勝率・中央値リターンを算出する。

ロジック:
  各営業日 d について:
    target_price[d] = Close[d-1] × (1 + drop_pct / 100)
    is_hit[d]       = Low[d] ≤ target_price[d]
    pnl[d]          = Close[d] - target_price[d]
    is_win[d]       = is_hit[d] AND (pnl[d] > 0)

やらないこと:
- "The One" の選定（the_one_selector.py が担当）
- データ取得
"""
import logging
from typing import List

import numpy as np
import pandas as pd

from src.low_hunter import config
from src.low_hunter.models import BacktestResult

logger = logging.getLogger(__name__)


class BacktestEngine:
    """0.1%刻み悉皆バックテストエンジン"""

    def __init__(
        self,
        drop_min: float = config.DROP_RANGE_MIN,
        drop_max: float = config.DROP_RANGE_MAX,
        drop_step: float = config.DROP_STEP,
    ):
        # -1.0 から -7.0 まで 0.1 刻みの配列を生成
        # np.arange で浮動小数点の刻みを正確に生成
        self.drop_levels = np.round(
            np.arange(drop_min, drop_max - drop_step / 2, -drop_step),
            1,
        )

    def run(self, df: pd.DataFrame) -> List[BacktestResult]:
        """
        1銘柄に対して全パターンのバックテストを実行する。

        Args:
            df: OHLCVデータ（最低 config.MIN_VALID_DAYS 日分必要）

        Returns:
            各下落率パターンの BacktestResult リスト（61個）。
            データ不足の場合は空リスト。
        """
        if len(df) < config.MIN_VALID_DAYS:
            return []

        # 直近 LOOKBACK_DAYS 日分に限定
        df_bt = df.tail(config.LOOKBACK_DAYS + 1).copy()

        close = df_bt['Close'].values
        low = df_bt['Low'].values

        # 前日終値（1日ずらし）
        prev_close = close[:-1]  # d-1 の Close
        day_low = low[1:]        # d の Low
        day_close = close[1:]    # d の Close

        trading_days = len(prev_close)

        results: List[BacktestResult] = []

        for drop_pct in self.drop_levels:
            # 各日の指値 = 前日終値 × (1 + drop_pct / 100)
            target_prices = prev_close * (1.0 + drop_pct / 100.0)

            # 約定判定: その日の安値が指値以下なら約定
            is_hit = day_low <= target_prices

            hit_count = int(np.sum(is_hit))

            if hit_count == 0:
                results.append(BacktestResult(
                    drop_pct=float(drop_pct),
                    trading_days=trading_days,
                    hit_count=0,
                    win_count=0,
                    win_rate=0.0,
                    median_return=0.0,
                ))
                continue

            # 約定した日の損益率（%）
            hit_targets = target_prices[is_hit]
            hit_closes = day_close[is_hit]
            pnl_pct = (hit_closes - hit_targets) / hit_targets * 100.0

            win_count = int(np.sum(pnl_pct > 0))
            win_rate = win_count / hit_count * 100.0
            median_return = float(np.median(pnl_pct))

            results.append(BacktestResult(
                drop_pct=float(drop_pct),
                trading_days=trading_days,
                hit_count=hit_count,
                win_count=win_count,
                win_rate=round(win_rate, 2),
                median_return=round(median_return, 3),
            ))

        return results
