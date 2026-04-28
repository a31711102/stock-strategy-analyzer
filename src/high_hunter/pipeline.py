"""
Project-high-hunter: 統合パイプライン（空売り版）

処理フロー:
1. 日経225銘柄リストの取得
2. ユニバース選定（low_hunterと同一基準）
3. 悉皆バックテスト実行（空売りロジック）
4. "The One" 選定
5. Win_Rate 降順でランキング付与
6. JSON dict を返却
"""
import logging
from datetime import datetime
from typing import Dict, List

import pandas as pd

from src.high_hunter import config
from src.high_hunter.backtest_engine import BacktestEngineShort
from src.high_hunter.models import TheOneShortResult
from src.high_hunter.the_one_selector import TheOneShortSelector
from src.low_hunter.nikkei225_fetcher import Nikkei225Fetcher
from src.low_hunter.universe import UniverseFilter

logger = logging.getLogger(__name__)


class HighHunterPipeline:
    """Project-high-hunter 統合パイプライン"""

    def __init__(self):
        self.nikkei_fetcher = Nikkei225Fetcher()
        self.universe_filter = UniverseFilter()
        self.backtest_engine = BacktestEngineShort()
        self.selector = TheOneShortSelector()

    def run(
        self,
        stock_data: Dict[str, pd.DataFrame],
        market_df: pd.DataFrame,
    ) -> List[TheOneShortResult]:
        """
        パイプラインを実行する。

        Args:
            stock_data: {銘柄コード: 指標計算済みDataFrame} の辞書
            market_df: 日経平均のOHLCVデータ

        Returns:
            TheOneShortResult のリスト（Win_Rate 降順、ランク付き）。
        """
        stock_list = self.nikkei_fetcher.fetch()
        logger.info(f"日経225銘柄リスト: {len(stock_list)}銘柄")

        universe = self.universe_filter.apply(stock_list, stock_data, market_df)
        if not universe:
            logger.warning("ユニバースに該当する銘柄がありません")
            return []

        the_ones: List[TheOneShortResult] = []
        for stock in universe:
            df = stock_data.get(stock.code)
            if df is None:
                continue

            bt_results = self.backtest_engine.run(df)
            if not bt_results:
                continue

            result = self.selector.select(bt_results, stock)
            if result is not None:
                the_ones.append(result)

        the_ones.sort(key=lambda r: (r.win_rate, r.median_return), reverse=True)

        for rank, result in enumerate(the_ones, 1):
            result.rank = rank

        logger.info(
            f"=== High Hunter 完了: {len(stock_list)}銘柄 → "
            f"ユニバース:{len(universe)} → 最終:{len(the_ones)} ==="
        )

        return the_ones

    def to_json_dict(self, results: List[TheOneShortResult]) -> dict:
        """結果をJSON保存用の辞書に変換"""
        return {
            'generated_at': datetime.now().isoformat(),
            'parameters': {
                'lookback_days': config.LOOKBACK_DAYS,
                'rise_range': f"{config.RISE_RANGE_MIN}% ~ {config.RISE_RANGE_MAX}%",
                'rise_step': config.RISE_STEP,
                'min_win_rate': config.MIN_WIN_RATE,
                'min_win_count': config.MIN_WIN_COUNT,
                'min_beta': config.MIN_BETA,
                'min_norm_atr': config.MIN_NORM_ATR,
                'min_avg_volume': config.MIN_AVG_VOLUME,
                'default_risk_jpy': config.DEFAULT_RISK_JPY,
            },
            'total_results': len(results),
            'stocks': [r.to_dict() for r in results],
        }
