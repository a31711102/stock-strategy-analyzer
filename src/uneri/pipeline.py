"""
うねりチャート S/R接近通知システム: アプリケーションパイプライン

責務:
- 対象銘柄の絞込（東証プライム判定、日足データ検証、20日平均出来高100万株以上）
- 日足データから週足OHLCデータの集約
- UneriDetector を用いた各銘柄のうねり＆接近判定
- 前回状態履歴との比較と新状態の生成（同一日付での再実行時は冪等性を保つ）
- 初期表示順（S乖離率の小さい順）でのソートとタブ別集計・JSONシリアライズ

やらないこと:
- ファイルI/O（ResultCache が担当）
- HTMLの直接生成（Flask routes / generate_static_pages.py が担当）
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

from src.data.market_segments import is_prime
from src.uneri.config import UneriConfig
from src.uneri.detector import UneriDetector
from src.uneri.models import (
    UneriCandidate,
    TAB_BUY_ACTIVE,
    TAB_BUY_WATCH,
    TAB_PROFIT_TAKE,
    TAB_BREAKDOWN,
)

logger = logging.getLogger(__name__)


class UneriPipeline:
    """うねりチャート底値買い・S/R接近検出パイプライン"""

    def __init__(self, config: Optional[UneriConfig] = None):
        self.config = config or UneriConfig()
        self.detector = UneriDetector(self.config)
        self.exclusion_reasons: Dict[str, int] = {}

    def run(
        self,
        stock_data: Dict[str, pd.DataFrame],
        stock_names: Dict[str, str],
        market_map: Dict[str, str],
        previous_state_history: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[List[UneriCandidate], Dict[str, Dict[str, Any]]]:
        """
        全対象銘柄に対してうねり判定・接近判定を実行する。

        Args:
            stock_data: {銘柄コード: 日足OHLCV DataFrame}
            stock_names: {銘柄コード: 銘柄名}
            market_map: {銘柄コード: 市場区分文字列}
            previous_state_history: 前回保存された状態履歴
                {
                    code: {
                        "state": str,
                        "as_of_date": str,
                        "prev_day_state": Optional[str],
                        "updated_at": str
                    }
                }

        Returns:
            (UneriCandidate のリスト（S乖離率昇順）, 更新後の状態履歴辞書)
        """
        prev_history = previous_state_history or {}
        new_history: Dict[str, Dict[str, Any]] = {}
        candidates: List[UneriCandidate] = []
        self.exclusion_reasons = {
            "non_prime": 0,
            "insufficient_data": 0,
            "stale_or_delisted": 0,
            "low_liquidity_or_no_wave": 0,
            "error": 0,
        }

        total_input = len(stock_data)
        prime_count = 0

        # 市場全体の最新営業日を特定（上場廃止や長期売買停止による古いキャッシュデータを除外するため）
        market_latest_dt: Optional[datetime] = None
        for df in stock_data.values():
            if df is not None and not df.empty:
                last_idx = df.index[-1]
                dt_str = last_idx.strftime("%Y-%m-%d") if hasattr(last_idx, "strftime") else str(last_idx)[:10]
                try:
                    dt_val = datetime.strptime(dt_str, "%Y-%m-%d")
                    if market_latest_dt is None or dt_val > market_latest_dt:
                        market_latest_dt = dt_val
                except ValueError:
                    continue

        for code, df in stock_data.items():
            code_str = str(code).replace(".JP", "").strip()
            market = market_map.get(code_str, "")

            # 1. 東証プライム判定（3.1章・9章番号1）
            if not is_prime(market):
                self.exclusion_reasons["non_prime"] += 1
                continue

            prime_count += 1

            # 2. データ欠損・行数チェック（13章：必要データ不足銘柄は除外理由を記録し全体処理を継続）
            if df is None or df.empty or len(df) < 120:
                self.exclusion_reasons["insufficient_data"] += 1
                continue

            required_cols = {"High", "Low", "Close", "Volume"}
            if not required_cols.issubset(set(df.columns)):
                self.exclusion_reasons["insufficient_data"] += 1
                continue

            try:
                # NaN除去
                clean_df = df.dropna(subset=["High", "Low", "Close", "Volume"])
                if len(clean_df) < 120:
                    self.exclusion_reasons["insufficient_data"] += 1
                    continue

                dates = [
                    d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                    for d in clean_df.index
                ]
                as_of_date = dates[-1]

                # 2.5 データ鮮度チェック（上場廃止・長期売買停止銘柄の除外）
                if market_latest_dt is not None:
                    stock_last_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
                    if (market_latest_dt - stock_last_dt).days > self.config.max_stale_calendar_days:
                        self.exclusion_reasons["stale_or_delisted"] += 1
                        continue

                # 冪等性対応: 同一営業日（as_of_date）に複数回バッチを回した場合でも、
                # 「前営業日時点の状態（prev_day_state）」と比較して新規通知フラグが消えないようにする
                prev_record = prev_history.get(code_str)
                effective_prev_state: Optional[str] = None
                if prev_record:
                    if prev_record.get("as_of_date") == as_of_date:
                        effective_prev_state = prev_record.get("prev_day_state")
                    else:
                        effective_prev_state = prev_record.get("state")

                highs = clean_df["High"].astype(float).tolist()
                lows = clean_df["Low"].astype(float).tolist()
                closes = clean_df["Close"].astype(float).tolist()
                volumes = clean_df["Volume"].astype(float).tolist()

                # 週足OHLCの集約（日足から週次集約：11章）
                weekly_highs, weekly_lows = self._resample_weekly_high_low(clean_df)

                name = stock_names.get(code_str, code_str)
                candidate = self.detector.analyze_stock(
                    code=code_str,
                    name=name,
                    market=market,
                    dates=dates,
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    volumes=volumes,
                    weekly_highs=weekly_highs,
                    weekly_lows=weekly_lows,
                    previous_state=effective_prev_state,
                )

                if candidate is not None:
                    candidates.append(candidate)
                    new_history[code_str] = {
                        "state": candidate.state,
                        "state_label": candidate.state_label,
                        "as_of_date": as_of_date,
                        "prev_day_state": effective_prev_state,
                        "is_new_buy_alert": candidate.is_new_buy_alert,
                        "updated_at": datetime.now().isoformat(),
                    }
                else:
                    self.exclusion_reasons["low_liquidity_or_no_wave"] += 1

            except Exception as e:
                self.exclusion_reasons["error"] += 1
                logger.warning(f"うねり分析エラー ({code_str}): {e}")
                continue

        # 10.2章: 初期表示はS乖離率の小さい順とする（同率なら往復数の多い順、平均出来高の多い順）
        candidates.sort(
            key=lambda c: (
                c.support_distance_pct,
                -c.wave_metrics.cycles,
                -c.avg_volume_20d,
            )
        )

        for idx, c in enumerate(candidates, 1):
            c.rank = idx

        new_alert_count = sum(1 for c in candidates if c.is_new_buy_alert)
        logger.info(
            f"=== うねりチャート分析完了: 入力{total_input}銘柄 (東証プライム:{prime_count}) "
            f"→ 抽出:{len(candidates)}銘柄 (うち新規買い接近通知:{new_alert_count}銘柄) | "
            f"除外内訳: 非プライム={self.exclusion_reasons['non_prime']}, "
            f"データ不足={self.exclusion_reasons['insufficient_data']}, "
            f"鮮度切れ/上場廃止={self.exclusion_reasons['stale_or_delisted']}, "
            f"うねり/接近条件外={self.exclusion_reasons['low_liquidity_or_no_wave']}, "
            f"エラー={self.exclusion_reasons['error']} ==="
        )

        return candidates, new_history

    @staticmethod
    def _resample_weekly_high_low(df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """日足DataFrameから週足の高値・安値系列を集約する"""
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                temp = df.copy()
                temp.index = pd.to_datetime(temp.index)
            except Exception:
                return [], []
        else:
            temp = df

        weekly = temp.resample("W-FRI").agg({"High": "max", "Low": "min"}).dropna()
        if weekly.empty:
            return [], []
        return weekly["High"].astype(float).tolist(), weekly["Low"].astype(float).tolist()

    def to_json_dict(self, candidates: List[UneriCandidate]) -> Dict[str, Any]:
        """分析結果をJSON保存・Web表示用の辞書へ変換する"""
        all_dicts = [c.to_dict() for c in candidates]

        # 4つのタブ別に整理し、各タブ内でも順位（tab_rank）を付与
        tabs = {
            TAB_BUY_ACTIVE: [],   # 買い検討・S到達
            TAB_BUY_WATCH: [],    # 監視開始
            TAB_PROFIT_TAKE: [],  # 利確目安
            TAB_BREAKDOWN: [],    # 下抜け警戒
        }

        for item in all_dicts:
            cat = item.get("tab_category")
            if cat in tabs:
                tabs[cat].append(item)

        # 利確目安タブは「Rまでの距離が小さい順（上昇余地の昇順）」を初期順序とする
        tabs[TAB_PROFIT_TAKE].sort(key=lambda x: x["resistance"]["upside_pct"])

        for cat_items in tabs.values():
            for idx, item in enumerate(cat_items, 1):
                item["tab_rank"] = idx

        new_buy_alerts = [item for item in all_dicts if item.get("is_new_buy_alert")]

        return {
            "generated_at": datetime.now().isoformat(),
            "parameters": self.config.to_dict(),
            "total_results": len(all_dicts),
            "new_buy_alert_count": len(new_buy_alerts),
            "counts_by_tab": {
                k: len(v) for k, v in tabs.items()
            },
            "new_buy_alerts": new_buy_alerts,
            "tabs": tabs,
            "stocks": all_dicts,
        }
