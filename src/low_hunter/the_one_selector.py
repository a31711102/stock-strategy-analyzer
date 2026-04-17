"""
Project-low-hunter: "The One" 選定ロジック

責務:
- 61パターンのバックテスト結果から、最高勝率のポイントを1つだけ選定する。

選定基準:
1. 勝ち回数（win_count）≥ MIN_WIN_COUNT のパターンに限定
2. 勝率が最も高いパターンを採用
3. 勝率同率の場合は中央値リターンが高い方を採用
4. 最高勝率が MIN_WIN_RATE 未満の銘柄は除外（None を返す）

やらないこと:
- バックテストの実行（backtest_engine.py が担当）
- ランキング順位の付与（pipeline.py が担当）
"""
import logging
from typing import List, Optional

from src.low_hunter import config
from src.low_hunter.models import BacktestResult, TheOneResult, UniverseStock

logger = logging.getLogger(__name__)


class TheOneSelector:
    """最高勝率ポイントの選定"""

    def __init__(
        self,
        min_win_rate: float = config.MIN_WIN_RATE,
        min_win_count: int = config.MIN_WIN_COUNT,
    ):
        self.min_win_rate = min_win_rate
        self.min_win_count = min_win_count

    def select(
        self,
        bt_results: List[BacktestResult],
        stock: UniverseStock,
    ) -> Optional[TheOneResult]:
        """
        61パターンの結果から "The One" を選定する。

        Args:
            bt_results: バックテスト結果リスト（61個）
            stock: ユニバース通過銘柄の情報

        Returns:
            TheOneResult。条件を満たすパターンが無い場合は None。
        """
        if not bt_results:
            return None

        # 勝ち回数フィルタ
        candidates = [
            r for r in bt_results
            if r.win_count >= self.min_win_count
        ]

        if not candidates:
            return None

        # 勝率降順 → 同率なら中央値リターン降順でソート
        best = max(
            candidates,
            key=lambda r: (r.win_rate, r.median_return),
        )

        # 最低勝率チェック
        if best.win_rate < self.min_win_rate:
            return None

        # target_price = 前日終値 × (1 + best_drop_pct / 100)
        target_price = stock.prev_close * (1.0 + best.drop_pct / 100.0)

        if target_price <= 0:
            return None

        return TheOneResult(
            rank=0,  # pipeline で後から付与
            ticker=stock.code,
            name=stock.name,
            best_drop_pct=best.drop_pct,
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
