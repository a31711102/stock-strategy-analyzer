"""
Project-low-hunter: 統合パイプライン

責務:
- 各コンポーネントを正しい順序で実行し、最終結果を生成する。

処理フロー:
1. 日経225銘柄リストの取得
2. 日経平均データの取得
3. 個別銘柄のデータ取得＋指標計算
4. ユニバース選定
5. 悉皆バックテスト実行
6. "The One" 選定
7. Win_Rate 降順でランキング付与
8. JSON dict を返却

やらないこと:
- 結果の永続化（ResultCache が担当）
- HTML生成
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.low_hunter import config
from src.low_hunter.backtest_engine import BacktestEngine
from src.low_hunter.models import TheOneResult
from src.low_hunter.nikkei225_fetcher import Nikkei225Fetcher
from src.low_hunter.the_one_selector import TheOneSelector
from src.low_hunter.universe import UniverseFilter

logger = logging.getLogger(__name__)


class LowHunterPipeline:
    """Project-low-hunter 統合パイプライン"""

    def __init__(self):
        self.nikkei_fetcher = Nikkei225Fetcher()
        self.universe_filter = UniverseFilter()
        self.backtest_engine = BacktestEngine()
        self.selector = TheOneSelector()

    def run(
        self,
        stock_data: Dict[str, pd.DataFrame],
        market_df: pd.DataFrame,
    ) -> List[TheOneResult]:
        """
        パイプラインを実行する。

        Args:
            stock_data: {銘柄コード: 指標計算済みDataFrame} の辞書
            market_df: 日経平均のOHLCVデータ

        Returns:
            TheOneResult のリスト（Win_Rate 降順、ランク付き）。
        """
        # 1. 日経225銘柄リスト取得
        stock_list = self.nikkei_fetcher.fetch()
        logger.info(f"日経225銘柄リスト: {len(stock_list)}銘柄")

        # 2. ユニバース選定
        universe = self.universe_filter.apply(stock_list, stock_data, market_df)
        if not universe:
            logger.warning("ユニバースに該当する銘柄がありません")
            return []

        # 3. 悉皆バックテスト + "The One" 選定
        the_ones: List[TheOneResult] = []
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

        # 4. Win_Rate 降順 → 同率なら median_return 降順でソート
        the_ones.sort(key=lambda r: (r.win_rate, r.median_return), reverse=True)

        # 5. ランク付与
        for rank, result in enumerate(the_ones, 1):
            result.rank = rank

        logger.info(
            f"=== Low Hunter 完了: {len(stock_list)}銘柄 → "
            f"ユニバース:{len(universe)} → 最終:{len(the_ones)} ==="
        )

        return the_ones

    def to_json_dict(self, results: List[TheOneResult]) -> dict:
        """結果をJSON保存用の辞書に変換"""
        return {
            'generated_at': datetime.now().isoformat(),
            'parameters': {
                'lookback_days': config.LOOKBACK_DAYS,
                'drop_range': f"{config.DROP_RANGE_MIN}% ~ {config.DROP_RANGE_MAX}%",
                'drop_step': config.DROP_STEP,
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
