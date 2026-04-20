"""
ボラティリティ乖離スクリーナー 独立実行スクリプト

バッチ処理とは独立して、全銘柄のデータをyfinanceから取得し、
三段階フィルタリングを実行してスクリーナー結果を保存する。

使い方:
    python scripts/run_screener.py
    python scripts/run_screener.py --risk 5  # 許容リスク5万円
"""
import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from tqdm import tqdm

from src.data.fetcher import StockDataFetcher
from src.indicators.technical import TechnicalIndicators
from src.screener.pipeline import ScreenerPipeline
from src.batch.result_cache import ResultCache

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def load_stock_list() -> pd.DataFrame:
    """data_j.xls から銘柄リストを読み込み"""
    xls_path = PROJECT_ROOT / 'data_j.xls'
    if not xls_path.exists():
        logger.error(f"銘柄リストが見つかりません: {xls_path}")
        sys.exit(1)

    df = pd.read_excel(str(xls_path))
    # ETF等を除外
    if '市場・商品区分' in df.columns:
        exclude_markets = ['ETF・ETN', 'REIT・ベンチャーファンド・カントリーファンド・インフラファンド']
        df = df[~df['市場・商品区分'].isin(exclude_markets)]
    return df


def run_screener(risk_jpy: int = 30_000):
    """
    スクリーナーを独立実行

    1. 銘柄リスト読み込み
    2. 各銘柄のOHLCV取得 + 指標計算
    3. 三段階フィルタリング
    4. 結果をJSONに保存
    """
    logger.info("=== ボラティリティスクリーナー 独立実行 ===")

    stock_df = load_stock_list()
    all_codes = stock_df['コード'].astype(str).tolist()
    logger.info(f"対象銘柄: {len(all_codes)}")

    fetcher = StockDataFetcher()
    stock_indicators: dict[str, pd.DataFrame] = {}
    stock_names: dict[str, str] = {}

    logger.info("--- データ取得・指標計算 ---")
    start_date = (pd.Timestamp.now() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    for _, row in tqdm(stock_df.iterrows(), total=len(stock_df), desc="データ取得"):
        code = str(row['コード'])
        name = row['銘柄名']

        try:
            df = fetcher.fetch_stock_data(code, start_date=start_date)
            if df is None or len(df) < 200:
                continue

            df = TechnicalIndicators.calculate_all_indicators(df)
            stock_indicators[code] = df
            stock_names[code] = name

        except Exception as e:
            logger.debug(f"スキップ ({code}): {e}")
            continue

    logger.info(f"取得完了: {len(stock_indicators)}銘柄")

    # スクリーナー実行
    logger.info("--- 三段階フィルタリング ---")
    pipeline = ScreenerPipeline(risk_jpy=risk_jpy)
    results = pipeline.run(stock_indicators, stock_names)

    # 結果保存
    result_dict = pipeline.to_json_dict(results)
    cache = ResultCache(str(PROJECT_ROOT / 'results'))
    cache.save_screener_result(result_dict)

    total_found = len(results.get('dynamic', [])) + len(results.get('large_cap', []))
    logger.info(f"=== スクリーナー完了: 計{total_found}銘柄 ===")

    # サマリ表示
    if total_found > 0:
        for key, title in [('dynamic', '【急拡大銘柄（RVR順）】'), ('large_cap', '【大型ハイボラ銘柄（Norm_ATR順）】')]:
            stocks = result_dict.get('stocks' if key == 'dynamic' else 'stocks_large_cap', [])
            if stocks:
                print(f"\n{title}")
                print("=" * 70)
                print(f"{'#':>3} {'Code':<6} {'Name':<16} {'RVR':>6} {'NATR':>6} {'Target':>10} {'Status':<10}")
                print("-" * 70)
                for r in stocks:
                    print(
                        f"{r['rank']:>3} {r['ticker']:<6} {r['name'][:14]:<16} "
                        f"{r['rvr']:>6.2f} {r['norm_atr']:>5.1f}% "
                        f"\\{r['target_buy']:>9,.0f} {r['status']:<10}"
                    )
                print("=" * 70)
    else:
        print("\n該当銘柄なし")

    # メモリ解放
    stock_indicators.clear()
    stock_names.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ボラティリティスクリーナー独立実行')
    parser.add_argument('--risk', type=float, default=3.0, help='許容リスク額（万円）')
    args = parser.parse_args()

    run_screener(risk_jpy=int(args.risk * 10_000))
