"""
Project-high-hunter: 単独実行スクリプト

使い方:
    python scripts/run_high_hunter.py
    python scripts/run_high_hunter.py --risk 5   # 許容リスク5万円
    python scripts/run_high_hunter.py --limit 10  # 10銘柄でテスト実行
"""
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from tqdm import tqdm

from src.data.fetcher import StockDataFetcher
from src.indicators.technical import TechnicalIndicators
from src.high_hunter.pipeline import HighHunterPipeline
from src.high_hunter import config
from src.batch.result_cache import ResultCache

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def run():
    parser = argparse.ArgumentParser(description='High Hunter - 黄金の空売りボード生成')
    parser.add_argument('--risk', type=float, default=3.0, help='許容リスク（万円）')
    parser.add_argument('--limit', type=int, default=None, help='処理する銘柄数の上限（テスト用）')
    args = parser.parse_args()

    logger.info("=== High Hunter 独立実行 ===")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=500)).strftime("%Y-%m-%d")
    fetcher = StockDataFetcher(start_date=start_date)

    # 1. 日経225銘柄リスト取得
    pipeline = HighHunterPipeline()
    stock_list = pipeline.nikkei_fetcher.fetch()
    if args.limit:
        stock_list = stock_list[:args.limit]
        logger.info(f"テスト実行: 対象銘柄を {args.limit} 件に制限します")
    logger.info(f"対象銘柄: {len(stock_list)}")

    # 2. 日経平均データ取得
    logger.info("--- 日経平均データ取得 ---")
    market_df = fetcher.fetch_stock_data(config.NIKKEI225_INDEX_CODE, start_date, end_date)
    if market_df is None or market_df.empty:
        logger.error("日経平均データの取得に失敗しました。処理を中断します。")
        sys.exit(1)
    logger.info(f"日経平均: {len(market_df)}日分取得（{market_df.index[0].date()} ~ {market_df.index[-1].date()}）")

    # 3. 個別銘柄データ取得 + 指標計算
    logger.info("--- 個別銘柄データ取得・指標計算 ---")
    stock_data = {}
    indicators = TechnicalIndicators()

    for code, name in tqdm(stock_list, desc="データ取得"):
        try:
            df = fetcher.fetch_stock_data(code, start_date, end_date)
            if df is not None and not df.empty and len(df) >= config.MIN_VALID_DAYS:
                df = indicators.calculate_all_indicators(df, 'daily')
                stock_data[code] = df
        except Exception as e:
            logger.debug(f"{code} データ取得エラー: {e}")
            continue

    logger.info(f"有効データ: {len(stock_data)}/{len(stock_list)}銘柄")

    # 4. パイプライン実行
    logger.info("--- バックテスト実行 ---")
    results = pipeline.run(stock_data, market_df)

    # 5. 結果保存
    result_dict = pipeline.to_json_dict(results)
    result_dict['parameters']['default_risk_jpy'] = int(args.risk * 10000)
    cache = ResultCache(str(PROJECT_ROOT / 'results'))
    cache.save_high_hunter_result(result_dict)

    # 6. サマリ表示
    if results:
        logger.info(f"\n{'='*70}")
        logger.info(f"  黄金の空売りボード: {len(results)}銘柄")
        logger.info(f"{'='*70}")
        logger.info(f"{'#':>3} {'コード':>6} {'銘柄名':<12} {'勝率':>6} {'中央値R':>8} {'上昇率':>6} {'指値':>10} {'β値':>5}")
        logger.info(f"{'-'*70}")
        for r in results:
            logger.info(
                f"{r.rank:>3} {r.ticker:>6} {r.name:<12} "
                f"{r.win_rate:>5.1f}% {r.median_return:>7.2f}% "
                f"+{r.best_rise_pct:>4.1f}% ¥{r.target_price:>9,.0f} "
                f"{r.beta:>5.2f}"
            )
        logger.info(f"{'='*70}")
    else:
        logger.info("該当銘柄なし: 優位性のある銘柄が見つかりませんでした。")

    logger.info("=== High Hunter 完了 ===")


if __name__ == '__main__':
    run()
