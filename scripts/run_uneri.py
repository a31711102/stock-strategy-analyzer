"""
うねりチャート S/R接近通知システム: 単独実行スクリプト

東証プライムかつ20日平均出来高100万株以上の銘柄を対象に、
約3か月周期のうねり（S-R往復）と接近状態を検出し、
results/uneri/ に候補一覧および状態履歴を出力する。

使い方:
    python scripts/run_uneri.py
    python scripts/run_uneri.py --limit 100
"""
import sys
import argparse
import logging
from pathlib import Path
import yaml
import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.cache import DataCache
from src.data.fetcher import StockDataFetcher
from src.data.market_segments import is_prime
from src.batch.result_cache import ResultCache
from src.uneri.config import UneriConfig
from src.uneri.pipeline import UneriPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run():
    parser = argparse.ArgumentParser(description="うねりチャート S/R接近通知システム 単独実行")
    parser.add_argument("--limit", type=int, default=None, help="走査する東証プライム銘柄数の上限（テスト用）")
    parser.add_argument("--fetch-missing", action="store_true", help="キャッシュにない銘柄を外部取得する")
    args = parser.parse_args()

    logger.info("=== うねりチャート S/R接近通知システム 独立実行 ===")

    cfg_dict = load_config(PROJECT_ROOT / "config.yaml")
    uneri_cfg = UneriConfig.from_dict(cfg_dict.get("uneri", {}))
    stock_list_rel = cfg_dict.get("data", {}).get("stock_list_path", "data_j.xls")
    stock_list_path = PROJECT_ROOT / stock_list_rel

    if not stock_list_path.exists():
        logger.error(f"銘柄マスタが見つかりません: {stock_list_path}")
        sys.exit(1)

    df_master = pd.read_excel(stock_list_path)
    df_master.columns = [
        "日付", "コード", "銘柄名", "市場区分",
        "33業種コード", "33業種区分",
        "17業種コード", "17業種区分",
        "規模コード", "規模区分",
    ]
    df_master = df_master[~df_master["市場区分"].str.contains("ETF|ETN|PRO Market", na=False)]

    # 東証プライムのみ抽出
    prime_rows = df_master[df_master["市場区分"].apply(lambda m: is_prime(str(m)))]
    if args.limit:
        prime_rows = prime_rows.head(args.limit)
        logger.info(f"テスト制限: 東証プライム {len(prime_rows)} 銘柄を対象にします")
    else:
        logger.info(f"東証プライム対象銘柄数: {len(prime_rows)}")

    data_cache = DataCache(str(PROJECT_ROOT / "cache" / "stock_data"))
    fetcher = StockDataFetcher() if args.fetch_missing else None

    stock_data = {}
    stock_names = {}
    market_map = {}

    for _, row in tqdm(prime_rows.iterrows(), total=len(prime_rows), desc="データ読込"):
        code = str(row["コード"]).strip()
        name = str(row["銘柄名"]).strip()
        market = str(row["市場区分"]).strip()

        stock_names[code] = name
        market_map[code] = market

        df = data_cache.get(code, ignore_ttl=True)
        if df is None and fetcher is not None:
            df = fetcher.fetch_stock_data(code)
            if df is not None:
                data_cache.set(code, df)

        if df is None or len(df) < 120:
            continue

        avg_vol = df["Volume"].tail(uneri_cfg.average_volume_days).mean()
        if pd.notna(avg_vol) and avg_vol >= uneri_cfg.minimum_average_volume:
            stock_data[code] = df

    logger.info(f"20日平均出来高{uneri_cfg.minimum_average_volume:,}株以上の対象銘柄: {len(stock_data)}件")

    result_cache = ResultCache(str(PROJECT_ROOT / "results"))
    prev_history = result_cache.load_uneri_state_history()

    pipeline = UneriPipeline(uneri_cfg)
    candidates, new_history = pipeline.run(
        stock_data=stock_data,
        stock_names=stock_names,
        market_map=market_map,
        previous_state_history=prev_history,
    )

    result_dict = pipeline.to_json_dict(candidates)
    result_cache.save_uneri_result(result_dict)
    result_cache.save_uneri_state_history(new_history)

    # コンソールサマリ出力
    counts = result_dict["counts_by_tab"]
    logger.info(
        f"抽出結果合計: {len(candidates)}件 "
        f"(買い検討・S到達:{counts['buy_active']} / 監視開始:{counts['buy_watch']} / "
        f"利確目安:{counts['profit_take']} / 下抜け警戒:{counts['breakdown']})"
    )

    new_alerts = [c for c in candidates if c.is_new_buy_alert]
    if new_alerts:
        logger.info(f"=== 新規買い接近通知 ({len(new_alerts)}件) ===")
        for c in new_alerts:
            logger.info(
                f"  [NEW] {c.code} {c.name} | {c.state_label} | 終値:¥{c.close:,.1f} | "
                f"S:¥{c.support_zone.representative_price:,.1f} (乖離:{c.support_distance_pct:+.2f}%) | "
                f"R:¥{c.resistance_zone.representative_price:,.1f} (余地:+{c.resistance_upside_pct:.2f}%) | "
                f"往復:{c.wave_metrics.cycles}回"
            )
    else:
        logger.info("新規買い接近通知: 0件")


if __name__ == "__main__":
    run()
