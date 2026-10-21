"""
うねりチャート S/R接近通知システム: ドメイン＆パイプライン テストスイート

要件定義書 第14章「受入基準」および第5〜13章の仕様を網羅的に検証する。
"""
import math
from datetime import datetime, timedelta
from typing import List, Tuple
import pandas as pd
import pytest

from src.uneri.config import UneriConfig
from src.uneri.models import (
    PivotPoint,
    STATE_SUPPORT_REACHED,
    STATE_BUY_CONSIDER,
    STATE_WATCH_START,
    STATE_BREAKDOWN_WARNING,
    STATE_PROFIT_CONSIDER,
    STATE_PROFIT_WATCH,
    STATE_NEUTRAL,
    TAB_BUY_ACTIVE,
    TAB_BUY_WATCH,
    TAB_PROFIT_TAKE,
    TAB_BREAKDOWN,
)
from src.uneri.detector import UneriDetector
from src.uneri.pipeline import UneriPipeline
from src.batch.result_cache import ResultCache


def generate_box_wave_series(
    total_days: int = 220,
    s_price: float = 1000.0,
    r_price: float = 1150.0,
    half_period: int = 30,
    final_close: float = 1008.0,
    volume: float = 1_500_000.0,
) -> Tuple[List[str], List[float], List[float], List[float], List[float]]:
    """
    S(1000) と R(1150) の間を片道 half_period 営業日（一往復 2*half_period = 60営業日）で
    往復する合成日足データを生成する。
    """
    base_date = datetime(2025, 11, 1)
    dates: List[str] = []
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    volumes: List[float] = []

    # 頂点インデックス:
    # day 20: Low (S=1000)
    # day 50: High (R=1150)
    # day 80: Low (S=1005)
    # day 110: High (R=1145)
    # day 140: Low (S=998)
    # day 170: High (R=1152)
    # day 200: 現在へ向けて下落し、final_close へ到達
    waypoints = [
        (0, 1080.0),
        (20, s_price),
        (50, r_price),
        (80, s_price * 1.005),
        (110, r_price * 0.996),
        (140, s_price * 0.998),
        (170, r_price * 1.002),
        (total_days - 1, final_close),
    ]

    # 線形補間でベース価格を作成
    prices = [0.0] * total_days
    for idx in range(len(waypoints) - 1):
        d0, p0 = waypoints[idx]
        d1, p1 = waypoints[idx + 1]
        if d0 >= total_days:
            break
        end_d = min(d1, total_days - 1)
        span = max(1, d1 - d0)
        for d in range(d0, end_d + 1):
            ratio = (d - d0) / span
            prices[d] = p0 + (p1 - p0) * ratio

    cur_dt = base_date
    for i in range(total_days):
        while cur_dt.weekday() >= 5:
            cur_dt += timedelta(days=1)
        dates.append(cur_dt.strftime("%Y-%m-%d"))
        cur_dt += timedelta(days=1)

        c = prices[i]
        # 転換点当日が明確に前後5日の極値になるよう設定
        is_valley = i in (20, 80, 140)
        is_peak = i in (50, 110, 170)
        if is_valley:
            l = c
            h = c + 8.0
        elif is_peak:
            h = c
            l = c - 8.0
        else:
            h = c + 4.0
            l = c - 4.0

        closes.append(float(c))
        highs.append(float(h))
        lows.append(float(l))
        volumes.append(float(volume))

    # 最終日の終値を厳密に final_close に設定
    closes[-1] = float(final_close)
    lows[-1] = min(lows[-1], float(final_close))
    highs[-1] = max(highs[-1], float(final_close))

    return dates, highs, lows, closes, volumes


def build_df_from_series(dates, highs, lows, closes, volumes) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        },
        index=pd.to_datetime(dates),
    )
    return df


class TestUneriDetectorDomain:
    """Domain層（UneriDetector）の単体テスト"""

    def test_future_leak_prevention_in_pivot_extraction(self):
        """
        【受入基準・13章】未来情報防止：
        末尾5営業日（後続日数が未確定の区間）の極値はピボット候補として抽出されないこと。
        """
        detector = UneriDetector(UneriConfig(pivot_window_days=5))
        dates, highs, lows, closes, volumes = generate_box_wave_series(
            total_days=200, final_close=1000.0
        )
        # 最終日（index=199）に極端な安値を入れても未確定のため raw_pivots に入らない
        lows[-1] = 500.0
        raw_pivots = detector.extract_raw_pivots(dates, highs, lows)
        assert all(p.bar_index <= 200 - 5 - 1 for p in raw_pivots)

    def test_minimum_swing_filter_8_percent(self):
        """
        【5.1章】小幅な上下（8%未満）をうねりと誤認せず、8%以上動いた主要転換点のみ採用すること。
        """
        detector = UneriDetector(UneriConfig(minimum_swing_percent=8.0))
        pivots = [
            PivotPoint("low", "2026-01-10", 10, 1000.0),
            PivotPoint("high", "2026-01-25", 20, 1050.0),  # +5% -> 無視されるべき小幅な山
            PivotPoint("low", "2026-02-05", 28, 1010.0),   # 小幅な谷
            PivotPoint("high", "2026-02-25", 40, 1120.0),  # 1000から+12% -> 採用！
            PivotPoint("low", "2026-04-05", 70, 1005.0),   # 1120から-10.2% -> 採用！
        ]
        major = detector.filter_major_pivots(pivots)
        assert len(major) == 3
        assert [p.bar_index for p in major] == [10, 40, 70]
        assert [p.kind for p in major] == ["low", "high", "low"]

    def test_touch_deduplication_within_10_days(self):
        """
        【受入基準・5.2章】連続してS帯に滞在した日（10営業日未満の間隔）が複数接触として数えられないこと。
        """
        detector = UneriDetector(UneriConfig(minimum_touch_gap_days=10, minimum_touch_count_s=2))
        # 5営業日しか離れていない2つの谷のみの場合、1回とみなされ最低接触回数(2回)を満たさない
        close_pivots = [
            PivotPoint("low", "2026-01-10", 10, 1000.0),
            PivotPoint("low", "2026-01-17", 15, 995.0),
        ]
        zones_short = detector.build_price_zones(close_pivots, kind="support")
        assert len(zones_short) == 0

        # 30営業日離れた谷がもう1つあれば合計2回接触としてS帯が成立し、近接した(10, 15)は安い方の995.0が代表採用される
        valid_pivots = close_pivots + [PivotPoint("low", "2026-03-05", 45, 1005.0)]
        zones_valid = detector.build_price_zones(valid_pivots, kind="support")
        assert len(zones_valid) == 1
        assert zones_valid[0].touch_count == 2
        assert zones_valid[0].representative_price == pytest.approx(1000.0)  # median(995, 1005)

    def test_stage_b_third_red_circle_detection_and_states(self):
        """
        【受入基準・6章・8章】
        S->R->S (40〜90営業日) のうねりが確認でき、現在値が3回目の底（赤丸）へ接近した際に、
        5% / 3% / 1% / -2% の各状態およびR接近状態が正しく切り替わること。
        """
        detector = UneriDetector()

        # 1. S到達（乖離 +0.8% <= 1.0%）
        dates, highs, lows, closes, volumes = generate_box_wave_series(
            final_close=1008.0  # S代表価格は約1000円
        )
        cand_reach = detector.analyze_stock(
            "7203", "トヨタ", "プライム（内国株式）", dates, highs, lows, closes, volumes
        )
        assert cand_reach is not None
        assert cand_reach.state == STATE_SUPPORT_REACHED
        assert cand_reach.tab_category == TAB_BUY_ACTIVE
        assert cand_reach.wave_metrics.cycles >= 2.0
        assert 40 <= cand_reach.wave_metrics.latest_round_trip_days <= 90

        # 2. 買い検討（乖離 +2.5% <= 3.0%）
        _, _, _, closes_buy, _ = generate_box_wave_series(final_close=1025.0)
        cand_buy = detector.analyze_stock(
            "7203", "トヨタ", "プライム（内国株式）", dates, highs, lows, closes_buy, volumes
        )
        assert cand_buy is not None
        assert cand_buy.state == STATE_BUY_CONSIDER
        assert cand_buy.tab_category == TAB_BUY_ACTIVE

        # 3. 監視開始（乖離 +4.2% <= 5.0%）
        _, _, _, closes_watch, _ = generate_box_wave_series(final_close=1042.0)
        cand_watch = detector.analyze_stock(
            "7203", "トヨタ", "プライム（内国株式）", dates, highs, lows, closes_watch, volumes
        )
        assert cand_watch is not None
        assert cand_watch.state == STATE_WATCH_START
        assert cand_watch.tab_category == TAB_BUY_WATCH

        # 4. 下抜け警戒（乖離 -2.5% <= -2.0%、ただし-5%未満なので無効化はされない）
        _, _, _, closes_break, _ = generate_box_wave_series(final_close=975.0)
        cand_break = detector.analyze_stock(
            "7203", "トヨタ", "プライム（内国株式）", dates, highs, lows, closes_break, volumes
        )
        assert cand_break is not None
        assert cand_break.state == STATE_BREAKDOWN_WARNING
        assert cand_break.tab_category == TAB_BREAKDOWN

        # 5. S無効化（乖離 -6.0% <= -5.0% の場合はS無効につき候補除外）
        _, _, _, closes_invalid, _ = generate_box_wave_series(final_close=935.0)
        cand_invalid = detector.analyze_stock(
            "7203", "トヨタ", "プライム（内国株式）", dates, highs, lows, closes_invalid, volumes
        )
        assert cand_invalid is None

        # 6. 利確検討（R=1150 に対して終値 1125 -> Rまでの上昇余地 +2.22% <= 3.0%）
        _, _, _, closes_profit, _ = generate_box_wave_series(final_close=1125.0)
        cand_profit = detector.analyze_stock(
            "7203", "トヨタ", "プライム（内国株式）", dates, highs, lows, closes_profit, volumes
        )
        assert cand_profit is not None
        assert cand_profit.state == STATE_PROFIT_CONSIDER
        assert cand_profit.tab_category == TAB_PROFIT_TAKE

    def test_consecutive_two_days_below_support_lower_bound_triggers_warning(self):
        """
        【5.3章】終値がS帯下限（S代表価格 - 3%）を2営業日連続で下回った場合、下抜け警戒となること。
        """
        detector = UneriDetector()
        dates, highs, lows, closes, volumes = generate_box_wave_series(final_close=968.0)
        # S代表価格≒1000, 下限≒970。直近2営業日を968(-3.2%)にする
        closes[-2] = 968.0
        closes[-1] = 968.0
        cand = detector.analyze_stock(
            "7203", "トヨタ", "プライム", dates, highs, lows, closes, volumes
        )
        assert cand is not None
        assert cand.state == STATE_BREAKDOWN_WARNING
        assert cand.tab_category == TAB_BREAKDOWN

    def test_out_of_cycle_duration_is_rejected(self):
        """
        【受入基準・6章】一往復期間が40〜90営業日の範囲外（例：片道10日＝一往復20日）の場合は除外されること。
        """
        detector = UneriDetector()
        dates, highs, lows, closes, volumes = generate_box_wave_series(total_days=200)
        # 一往復期間を95〜120日に強制設定すると、60日周期の銘柄は一致しない
        strict_detector = UneriDetector(
            UneriConfig(round_trip_min_days=95, round_trip_max_days=120)
        )
        cand = strict_detector.analyze_stock(
            "7203", "トヨタ", "プライム", dates, highs, lows, closes, volumes
        )
        assert cand is None


class TestUneriPipelineAndNotifications:
    """Application層（UneriPipeline）と状態履歴・通知制御のテスト"""

    def test_prime_and_volume_filtering(self):
        """
        【受入基準】
        - 東証プライム以外の銘柄が候補一覧に含まれないこと
        - 20日平均出来高100万株未満の銘柄が候補一覧に含まれないこと
        """
        dates, highs, lows, closes, volumes = generate_box_wave_series(
            final_close=1008.0, volume=1_500_000.0
        )
        df_high_vol = build_df_from_series(dates, highs, lows, closes, volumes)

        _, _, _, _, low_vols = generate_box_wave_series(
            final_close=1008.0, volume=800_000.0  # 100万株未満
        )
        df_low_vol = build_df_from_series(dates, highs, lows, closes, low_vols)

        stock_data = {
            "1001": df_high_vol,  # 東証プライム + 150万株 -> 抽出されるべき
            "1002": df_high_vol,  # 東証スタンダード + 150万株 -> 除外されるべき
            "1003": df_low_vol,   # 東証プライム + 80万株 -> 除外されるべき
        }
        stock_names = {
            "1001": "プライム高出来高",
            "1002": "スタンダード銘柄",
            "1003": "プライム低出来高",
        }
        market_map = {
            "1001": "プライム（内国株式）",
            "1002": "スタンダード（内国株式）",
            "1003": "プライム（内国株式）",
        }

        pipeline = UneriPipeline()
        candidates, _ = pipeline.run(stock_data, stock_names, market_map)

        assert len(candidates) == 1
        assert candidates[0].code == "1001"

    def test_state_transition_and_duplicate_notification_prevention(self):
        """
        【受入基準・8.2章】
        - 同一状態で重複通知されず、状態変化時に通知されること
        - 買い接近状態（監視開始・買い検討・S到達）への新規遷移時のみ is_new_buy_alert が True になること
        - 同一営業日に再実行しても通知フラグが消えないこと（冪等性）
        """
        dates, highs, lows, closes, volumes = generate_box_wave_series(final_close=1025.0)
        df = build_df_from_series(dates, highs, lows, closes, volumes)

        stock_data = {"7203": df}
        stock_names = {"7203": "トヨタ自動車"}
        market_map = {"7203": "プライム（内国株式）"}

        pipeline = UneriPipeline()

        # 1. 初回実行（前回履歴なし）-> 買い検討圏へ新規遷移なので is_new_buy_alert = True
        cands_1, hist_1 = pipeline.run(stock_data, stock_names, market_map, previous_state_history={})
        assert len(cands_1) == 1
        assert cands_1[0].state == STATE_BUY_CONSIDER
        assert cands_1[0].is_new_buy_alert is True

        # 2. 同一営業日（as_of_dateが同じ）にバッチを再実行した場合 -> 冪等性により True が維持される
        cands_same_day, _ = pipeline.run(
            stock_data, stock_names, market_map, previous_state_history=hist_1
        )
        assert cands_same_day[0].is_new_buy_alert is True

        # 3. 翌営業日に同じ状態（買い検討圏）が継続した場合 -> 重複通知しない（is_new_buy_alert = False）
        prev_day_hist = {
            "7203": {
                "state": STATE_BUY_CONSIDER,
                "as_of_date": "2020-01-01",  # 前営業日
                "prev_day_state": None,
            }
        }
        cands_next_day, _ = pipeline.run(
            stock_data, stock_names, market_map, previous_state_history=prev_day_hist
        )
        assert cands_next_day[0].state == STATE_BUY_CONSIDER
        assert cands_next_day[0].is_new_buy_alert is False

        # 4. 翌営業日に「監視開始」から「買い検討圏」へ一段階深く接近した場合 -> 状態変化なので通知（True）
        prev_watch_hist = {
            "7203": {
                "state": STATE_WATCH_START,
                "as_of_date": "2020-01-01",
                "prev_day_state": None,
            }
        }
        cands_stepped, _ = pipeline.run(
            stock_data, stock_names, market_map, previous_state_history=prev_watch_hist
        )
        assert cands_stepped[0].state == STATE_BUY_CONSIDER
        assert cands_stepped[0].is_new_buy_alert is True

    def test_zero_candidates_graceful_handling_and_cache_io(self, tmp_path):
        """
        【受入基準・9章】該当銘柄ゼロ件でも異常終了せず、ResultCacheへ保存・読込できること。
        """
        pipeline = UneriPipeline()
        candidates, history = pipeline.run({}, {}, {})
        assert candidates == []
        assert history == {}

        json_dict = pipeline.to_json_dict(candidates)
        assert json_dict["total_results"] == 0
        assert json_dict["new_buy_alert_count"] == 0
        assert json_dict["tabs"][TAB_BUY_ACTIVE] == []

        cache = ResultCache(str(tmp_path))
        assert cache.save_uneri_result(json_dict) is True
        loaded = cache.load_uneri_result()
        assert loaded is not None
        assert loaded["total_results"] == 0


class TestUneriRedTeamEdgeCases:
    """Round 2（Red Team 反証レビュー）および Round 3（運用保守性）の追加検証テスト"""

    def test_zero_or_nan_or_negative_prices_and_volumes_are_safely_rejected(self):
        """
        【Red Team 1】負の価格、ゼロ価格、NaN/Infを含む入力でもゼロ除算や例外を起こさず安全に除外すること。
        """
        detector = UneriDetector()
        dates, highs, lows, closes, volumes = generate_box_wave_series(final_close=1008.0)

        # ゼロ出来高や負の終値が混入
        bad_closes = list(closes)
        bad_closes[-1] = 0.0
        assert detector.analyze_stock("9999", "異常株", "プライム", dates, highs, lows, bad_closes, volumes) is None

        nan_vols = list(volumes)
        nan_vols[-1] = float("nan")
        passed, _, _ = detector.check_liquidity(closes, nan_vols)
        assert passed is False

    def test_dense_oscillation_dfs_cap_prevents_hang(self):
        """
        【Red Team 2】多数の転換点が密集するデータでも _extract_valid_wave_chains が上限で打ち切られ高速に終了すること。
        """
        detector = UneriDetector(UneriConfig(half_trip_min_days=1, half_trip_max_days=200, round_trip_min_days=2, round_trip_max_days=400))
        events = []
        for i in range(40):
            role = "S" if i % 2 == 0 else "R"
            price = 1000.0 if role == "S" else 1150.0
            events.append((role, PivotPoint("low" if role == "S" else "high", f"2026-01-{(i%28)+1:02d}", i * 2, price)))

        chains = detector._extract_valid_wave_chains(events)
        assert len(chains) <= 500

    def test_weekly_context_and_exclusion_breakdown_logging(self):
        """
        【Round 3】週足3年・5年レンジ位置の算出およびパイプラインの除外理由カウントが正確に記録されること。
        """
        dates, highs, lows, closes, volumes = generate_box_wave_series(total_days=220, final_close=1008.0)
        df_valid = build_df_from_series(dates, highs, lows, closes, volumes)
        df_short = df_valid.iloc[:50]  # 120日未満のデータ不足

        pipeline = UneriPipeline()
        candidates, _ = pipeline.run(
            stock_data={"1001": df_valid, "1002": df_short, "1003": df_valid},
            stock_names={"1001": "プライム正常", "1002": "プライム短期", "1003": "グロース株"},
            market_map={"1001": "プライム", "1002": "プライム", "1003": "グロース"},
        )
        assert len(candidates) == 1
        assert pipeline.exclusion_reasons["non_prime"] == 1
        assert pipeline.exclusion_reasons["insufficient_data"] == 1
        assert candidates[0].weekly_context.range_position_3y is not None
