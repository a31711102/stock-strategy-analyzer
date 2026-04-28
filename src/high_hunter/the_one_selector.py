"""
Project-high-hunter: "The One" 選定ロジック（空売り版）

責務:
- 61パターンのバックテスト結果から、最高勝率のポイントを1つだけ選定する。
"""
import logging
from typing import List, Optional

from src.high_hunter import config
from src.high_hunter.models import BacktestResultShort, TheOneShortResult
from src.low_hunter.models import UniverseStock

logger = logging.getLogger(__name__)


class TheOneShortSelector:
    """最高勝率ポイントの選定（空売り）"""

    def __init__(
        self,
        min_win_rate: float = config.MIN_WIN_RATE,
        min_win_count: int = config.MIN_WIN_COUNT,
    ):
        self.min_win_rate = min_win_rate
        self.min_win_count = min_win_count

    def select(
        self,
        bt_results: List[BacktestResultShort],
        stock: UniverseStock,
    ) -> Optional[TheOneShortResult]:
        """
        61パターンの結果から "The One" を選定する。

        Returns:
            TheOneShortResult。条件を満たすパターンが無い場合は None。
        """
        if not bt_results:
            return None

        candidates = [
            r for r in bt_results
            if r.win_count >= self.min_win_count
        ]

        if not candidates:
            return None

        best = max(
            candidates,
            key=lambda r: (r.win_rate, r.median_return),
        )

        if best.win_rate < self.min_win_rate:
            return None

        # target_price = 前日終値 × (1 + best_rise_pct / 100)
        target_price = stock.prev_close * (1.0 + best.rise_pct / 100.0)

        if target_price <= 0:
            return None

        return TheOneShortResult(
            rank=0,
            ticker=stock.code,
            name=stock.name,
            best_rise_pct=best.rise_pct,
            target_price=round(target_price, 1),
            win_rate=best.win_rate,
            win_count=best.win_count,
            median_return=best.median_return,
            hit_count=best.hit_count,
            beta=stock.beta,
            norm_atr=stock.norm_atr,
            prev_close=stock.prev_close,
            atr_10=stock.atr_10,
        )
