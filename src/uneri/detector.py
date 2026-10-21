"""
うねりチャート S/R接近通知システム: ドメイン検出エンジン

要件定義書 第5章〜第9章および2段階ハイブリッド方式に基づき、
1. 山谷の抽出（前後5営業日ピボット ＋ 8% ZigZag）
2. 価格帯（S帯・R帯）への集約と無効化条件の評価
3. S-R間のうねり（往復期間・往復数）の判定
4. 週足参考情報の算出
5. 現在値からの接近状態（Stage B: 3回目の赤丸等のリアルタイム引き付け）と状態遷移通知の判定
を行う。
"""
import math
import statistics
from typing import List, Optional, Sequence, Tuple, Dict

from src.uneri.config import UneriConfig
from src.uneri.models import (
    PivotPoint,
    PriceZone,
    WaveCycleMetrics,
    WeeklyContext,
    UneriCandidate,
    STATE_SUPPORT_REACHED,
    STATE_BUY_CONSIDER,
    STATE_WATCH_START,
    STATE_BREAKDOWN_WARNING,
    STATE_PROFIT_CONSIDER,
    STATE_PROFIT_WATCH,
    STATE_NEUTRAL,
    BUY_ALERT_STATES,
    TAB_BUY_ACTIVE,
    TAB_BUY_WATCH,
    TAB_PROFIT_TAKE,
    TAB_BREAKDOWN,
    STATE_DISPLAY_LABELS,
)


class UneriDetector:
    """うねりチャート・サポート/レジスタンス接近検出器（Domain層）"""

    def __init__(self, config: Optional[UneriConfig] = None):
        self.config = config or UneriConfig()

    # ================================================================
    # 1. 流動性判定（3.1章）
    # ================================================================
    def check_liquidity(
        self,
        closes: Sequence[float],
        volumes: Sequence[float],
    ) -> Tuple[bool, float, float]:
        """
        直近N営業日の平均出来高・平均売買代金を計算し、流動性条件を判定する。

        Returns:
            (条件通過フラグ, 20日平均出来高, 20日平均売買代金)
        """
        n = self.config.average_volume_days
        if n <= 0 or len(volumes) < n or len(closes) < n:
            return False, 0.0, 0.0

        recent_vols = volumes[-n:]
        recent_closes = closes[-n:]
        if any(math.isnan(v) or math.isinf(v) or v < 0 for v in recent_vols) or any(
            math.isnan(c) or math.isinf(c) or c <= 0 for c in recent_closes
        ):
            return False, 0.0, 0.0

        avg_vol = sum(recent_vols) / n
        avg_val = sum(c * v for c, v in zip(recent_closes, recent_vols)) / n

        passed = avg_vol >= self.config.minimum_average_volume
        return passed, avg_vol, avg_val

    # ================================================================
    # 2. 山と谷の抽出：前後5営業日ピボット + 8% ZigZag（5.1章・Stage A）
    # ================================================================
    def extract_raw_pivots(
        self,
        dates: Sequence[str],
        highs: Sequence[float],
        lows: Sequence[float],
    ) -> List[PivotPoint]:
        """
        前後 w 営業日の高値・安値と比較して局所的な山候補・谷候補を抽出する。
        未来情報防止（13章）のため、末尾 w 営業日（後続日数が未確定の区間）はピボット候補としない。
        """
        w = self.config.pivot_window_days
        total = len(dates)
        if total < 2 * w + 1:
            return []

        candidates: List[PivotPoint] = []
        for i in range(w, total - w):
            h_i = highs[i]
            l_i = lows[i]

            # 前後w営業日の中で最安値か（同値許容、ただし前後区間全体の最小値に一致）
            window_lows = [lows[j] for j in range(i - w, i + w + 1) if j != i]
            window_highs = [highs[j] for j in range(i - w, i + w + 1) if j != i]

            is_low_pivot = l_i <= min(window_lows)
            is_high_pivot = h_i >= max(window_highs)

            # 同一日に両方満たす異常バーでない限り追加（両方満たす場合は前後トレンドに応じるため両方記録可だが、通常は片方）
            if is_low_pivot and not is_high_pivot:
                candidates.append(PivotPoint(kind="low", date=dates[i], bar_index=i, price=float(l_i)))
            elif is_high_pivot and not is_low_pivot:
                candidates.append(PivotPoint(kind="high", date=dates[i], bar_index=i, price=float(h_i)))
            elif is_low_pivot and is_high_pivot:
                candidates.append(PivotPoint(kind="low", date=dates[i], bar_index=i, price=float(l_i)))
                candidates.append(PivotPoint(kind="high", date=dates[i], bar_index=i, price=float(h_i)))

        return candidates

    def filter_major_pivots(self, raw_pivots: Sequence[PivotPoint]) -> List[PivotPoint]:
        """
        直前の山または谷から minimum_swing_percent (8%) 以上動いた候補のみを
        交互の主要転換点（ZigZag）として採用する（5.1章）。
        """
        if not raw_pivots:
            return []

        min_swing = self.config.minimum_swing_percent / 100.0
        major: List[PivotPoint] = []

        # 最初の起点を見つけるため、暫定極値を追跡
        current_extreme = raw_pivots[0]

        for p in raw_pivots[1:]:
            if not major:
                # まだ最初の転換点が確定していない段階
                if p.kind == current_extreme.kind:
                    if p.kind == "low" and p.price <= current_extreme.price:
                        current_extreme = p
                    elif p.kind == "high" and p.price >= current_extreme.price:
                        current_extreme = p
                else:
                    # 逆方向の候補が出た場合、8%以上動いているか判定
                    if current_extreme.kind == "low" and p.kind == "high":
                        if current_extreme.price > 0 and (p.price - current_extreme.price) / current_extreme.price >= min_swing:
                            major.append(current_extreme)
                            current_extreme = p
                        elif p.price < current_extreme.price:
                            current_extreme = PivotPoint("low", p.date, p.bar_index, p.price)
                    elif current_extreme.kind == "high" and p.kind == "low":
                        if current_extreme.price > 0 and (current_extreme.price - p.price) / current_extreme.price >= min_swing:
                            major.append(current_extreme)
                            current_extreme = p
                        elif p.price > current_extreme.price:
                            current_extreme = PivotPoint("high", p.date, p.bar_index, p.price)
            else:
                # 既に1つ以上確定しており、current_extreme は未確定の最新端
                if p.kind == current_extreme.kind:
                    # 同方向ならより極端な値で更新
                    if p.kind == "low" and p.price <= current_extreme.price:
                        current_extreme = p
                    elif p.kind == "high" and p.price >= current_extreme.price:
                        current_extreme = p
                else:
                    # 逆方向への反転が8%以上なら current_extreme を確定し、p を新たな未確定端にする
                    if current_extreme.kind == "low" and p.kind == "high":
                        if current_extreme.price > 0 and (p.price - current_extreme.price) / current_extreme.price >= min_swing:
                            major.append(current_extreme)
                            current_extreme = p
                    elif current_extreme.kind == "high" and p.kind == "low":
                        if current_extreme.price > 0 and (current_extreme.price - p.price) / current_extreme.price >= min_swing:
                            major.append(current_extreme)
                            current_extreme = p

        # 最後の current_extreme も直前の確定点から8%以上離れていれば主要転換点に含める
        if major:
            last_confirmed = major[-1]
            if last_confirmed.kind == "low" and current_extreme.kind == "high":
                if (current_extreme.price - last_confirmed.price) / last_confirmed.price >= min_swing:
                    major.append(current_extreme)
            elif last_confirmed.kind == "high" and current_extreme.kind == "low":
                if (last_confirmed.price - current_extreme.price) / last_confirmed.price >= min_swing:
                    major.append(current_extreme)

        return major

    # ================================================================
    # 3. 価格帯（S帯・R帯）への集約（5.2章）
    # ================================================================
    def build_price_zones(
        self,
        pivots: Sequence[PivotPoint],
        kind: str,  # 'support' or 'resistance'
    ) -> List[PriceZone]:
        """
        主要転換点（谷または山）から、代表価格（中央値）±3%以内に収まる価格帯を構築する。
        - 別接触とみなす間隔：10営業日以上（5.2章）
        - 最低接触回数：S 2回以上、R 2回以上（5.2章）
        """
        target_pivot_kind = "low" if kind == "support" else "high"
        min_touches = (
            self.config.minimum_touch_count_s
            if kind == "support"
            else self.config.minimum_touch_count_r
        )
        zone_tol = self.config.price_zone_percent / 100.0

        target_pivots = [p for p in pivots if p.kind == target_pivot_kind]
        if len(target_pivots) < min_touches:
            return []

        candidate_zones: List[PriceZone] = []

        # 各ピボットを基準シードとして近傍（±3%以内）のピボットを集め、中央値で再計算
        for seed in target_pivots:
            if seed.price <= 0:
                continue
            initial_members = [
                p for p in target_pivots
                if abs(p.price - seed.price) / seed.price <= zone_tol
            ]
            if len(initial_members) < min_touches:
                continue

            rep_price = float(statistics.median(p.price for p in initial_members))
            lower = rep_price * (1.0 - zone_tol)
            upper = rep_price * (1.0 + zone_tol)

            # 代表価格の±3%に入るメンバーを再抽出
            members_in_zone = [
                p for p in target_pivots
                if lower <= p.price <= upper
            ]
            if len(members_in_zone) < min_touches:
                continue

            # 10営業日以上の間隔フィルタを適用
            deduped = self._deduplicate_touches(members_in_zone, kind)
            if len(deduped) < min_touches:
                continue

            # 重複排除後のメンバーで代表価格（中央値）を確定
            final_rep = float(statistics.median(p.price for p in deduped))
            final_lower = final_rep * (1.0 - zone_tol)
            final_upper = final_rep * (1.0 + zone_tol)

            # 最終帯域にすべてのdedupedメンバーが収まるか確認
            final_touches = tuple(
                p for p in deduped if final_lower <= p.price <= final_upper
            )
            if len(final_touches) < min_touches:
                continue

            candidate_zones.append(
                PriceZone(
                    kind=kind,
                    representative_price=final_rep,
                    lower_bound=final_lower,
                    upper_bound=final_upper,
                    touches=final_touches,
                )
            )

        # 同一・重複するゾーンを統合（接触日セットが同一、または代表価格が1%以内のものは接触数が多い方を優先）
        unique_zones: List[PriceZone] = []
        # 接触回数が多い順、直近接触が新しい順に並べて重複除去
        candidate_zones.sort(
            key=lambda z: (z.touch_count, z.touches[-1].bar_index),
            reverse=True,
        )
        for z in candidate_zones:
            touch_indices = tuple(t.bar_index for t in z.touches)
            is_dup = False
            for existing in unique_zones:
                existing_indices = tuple(t.bar_index for t in existing.touches)
                if touch_indices == existing_indices:
                    is_dup = True
                    break
                if abs(z.representative_price - existing.representative_price) / existing.representative_price < 0.015:
                    is_dup = True
                    break
            if not is_dup:
                unique_zones.append(z)

        return unique_zones

    def _deduplicate_touches(
        self,
        pivots: Sequence[PivotPoint],
        kind: str,
    ) -> List[PivotPoint]:
        """
        10営業日未満の連続・近接した接触を1回の接触にまとめる（5.2章・14章）。
        谷ならより安い方、山ならより高い方を残す。
        """
        if not pivots:
            return []

        sorted_pivots = sorted(pivots, key=lambda p: p.bar_index)
        result: List[PivotPoint] = [sorted_pivots[0]]
        gap = self.config.minimum_touch_gap_days

        for p in sorted_pivots[1:]:
            prev = result[-1]
            if p.bar_index - prev.bar_index < gap:
                # 同一滞在とみなし、より極端な価格の方を採用
                if kind == "support" and p.price < prev.price:
                    result[-1] = p
                elif kind == "resistance" and p.price > prev.price:
                    result[-1] = p
            else:
                result.append(p)

        return result

    # ================================================================
    # 4. S-Rペアとうねり（往復期間・往復数）の判定（5.3章・6章）
    # ================================================================
    def evaluate_wave_cycles(
        self,
        support_zone: PriceZone,
        resistance_zone: PriceZone,
        major_pivots: Sequence[PivotPoint],
        total_bars: int,
        closes: Sequence[float],
    ) -> Optional[WaveCycleMetrics]:
        """
        指定されたサポート帯（S）とレジスタンス帯（R）のペアについて、
        5.3章の無効化条件および6章のうねり条件（値幅8%以上、片道15〜50日、一往復40〜90日、1.5往復以上）を判定する。
        """
        s_price = support_zone.representative_price
        r_price = resistance_zone.representative_price

        # 5.3 無効化条件: SがR以上になる組合せ、値幅が小さすぎる組合せ（8%未満）は採用しない
        if s_price <= 0 or r_price <= s_price:
            return None

        sr_range_pct = (r_price - s_price) / s_price * 100.0
        if sr_range_pct < self.config.min_sr_range_percent:
            return None

        current_close = closes[-1]

        # 5.3 無効化条件: 終値がS代表価格を5%以上下回った場合、当該Sを無効とする
        s_dist_pct = (current_close - s_price) / s_price * 100.0
        if s_dist_pct <= -self.config.invalidation_drop_percent:
            return None

        # 5.3 無効化条件: Rを明確に上抜けた場合（現在値がR帯上限を超えている場合）は当該S-Rボックスからは外れる
        if current_close > resistance_zone.upper_bound:
            return None

        # 主要転換点のうち、S帯またはR帯に接触しているものを時系列に抽出
        zone_events: List[Tuple[str, PivotPoint]] = []
        for p in major_pivots:
            if p.kind == "low" and support_zone.contains(p.price):
                zone_events.append(("S", p))
            elif p.kind == "high" and resistance_zone.contains(p.price):
                zone_events.append(("R", p))

        if len(zone_events) < 3:
            return None

        # 同一帯への連続接触（例: S, S）が挟まった場合、うねりの交互系列を作るため調整
        alternating_chains = self._extract_valid_wave_chains(zone_events)
        if not alternating_chains:
            return None

        # 最も往復数が多く、かつ直近まで継続しているチェインを選択
        best_chain = max(
            alternating_chains,
            key=lambda ch: (len(ch), ch[-1][1].bar_index),
        )

        # 往復数の算出:
        # 転換点数3個 (S-R-S または R-S-R) = 1.0往復（片道2回）
        # 転換点数4個 (S-R-S-R または R-S-R-S) = 1.5往復（片道3回）
        # 転換点数5個 (S-R-S-R-S) = 2.0往復（片道4回）
        half_trips = len(best_chain) - 1
        confirmed_cycles = half_trips * 0.5

        last_role, last_pivot = best_chain[-1]
        days_since_last = (total_bars - 1) - last_pivot.bar_index

        # Stage B（2段階ハイブリッド方式）:
        # 「1往復完了後に次の片道が進行中（9章番号6）」または「S->R->S->R完了後に3回目の赤丸（S）へ接近中」の評価
        # 直近の確定転換点からの経過日数が片道最大期間（または一往復最大期間）を大きく超過して放置されている場合は除外
        if days_since_last > self.config.round_trip_max_days:
            return None

        # S->R->S (1.0往復) 完了後に次の片道が進行中、または既に S->R->S->R (1.5往復) 以上確定しているか判定
        effective_cycles = confirmed_cycles
        if confirmed_cycles == 1.0:
            # 1往復完了後に次の片道が進行中（9章 番号6）とみなせる条件:
            # 直近のピボットから逆方向へ進行し、片道期間内（15〜50営業日）にあること
            if self.config.half_trip_min_days <= days_since_last <= self.config.half_trip_max_days:
                if last_role == "S" and current_close >= resistance_zone.lower_bound * 0.95:
                    effective_cycles = 1.5
                elif last_role == "R" and current_close <= support_zone.upper_bound * 1.05:
                    effective_cycles = 1.5
        elif confirmed_cycles >= 1.5 and last_role == "R":
            # S->R->S->R (1.5往復) 確定後、現在値が再び S帯付近（S乖離5%以内）まで降りてきている場合（添付画像の3回目の赤丸！）
            # 直近の谷（best_chain[-2] = S）から今日までの期間が 40〜90営業日（一往復期間）かつ
            # 直近の山（best_chain[-1] = R）から今日までが片道期間（〜50営業日程度、最大でも一往復90日以内）であれば、
            # 実質的に2往復目（S->R->S->R->現在S接近）の底値圏に到達していると評価できる
            prev_s_pivot = best_chain[-2][1]
            current_round_trip_days = (total_bars - 1) - prev_s_pivot.bar_index
            if (
                s_dist_pct <= max(self.config.support_alert_levels)
                and self.config.round_trip_min_days <= current_round_trip_days <= self.config.round_trip_max_days
            ):
                effective_cycles = confirmed_cycles + 0.5

        if effective_cycles < self.config.minimum_cycles:
            return None

        # 一往復期間（S->R->S または R->S->R）のリストを算出
        round_trip_days_list: List[int] = []
        for i in range(len(best_chain) - 2):
            rt_days = best_chain[i + 2][1].bar_index - best_chain[i][1].bar_index
            round_trip_days_list.append(rt_days)

        # もし最後の未確定レグで3回目の赤丸（S接近）に達している場合、その直近一往復日数も記録
        if last_role == "R" and s_dist_pct <= max(self.config.support_alert_levels):
            prev_s_pivot = best_chain[-2][1]
            rt_now = (total_bars - 1) - prev_s_pivot.bar_index
            if self.config.round_trip_min_days <= rt_now <= self.config.round_trip_max_days:
                round_trip_days_list.append(rt_now)

        if not round_trip_days_list:
            return None

        latest_rt = round_trip_days_list[-1]
        avg_rt = sum(round_trip_days_list) / len(round_trip_days_list)

        return WaveCycleMetrics(
            cycles=effective_cycles,
            latest_round_trip_days=latest_rt,
            average_round_trip_days=avg_rt,
            sr_range_percent=sr_range_pct,
            is_priority=(effective_cycles >= self.config.priority_cycles),
            wave_pivots=tuple(item[1] for item in best_chain),
            days_since_last_pivot=days_since_last,
        )

    def _extract_valid_wave_chains(
        self,
        zone_events: Sequence[Tuple[str, PivotPoint]],
    ) -> List[List[Tuple[str, PivotPoint]]]:
        """
        S帯・R帯の接触イベント列から、
        - SとRが交互に出現し
        - 各片道が 15〜50営業日（half_trip_min_days 〜 half_trip_max_days）
        - 各一往復（i と i+2）が 40〜90営業日（round_trip_min_days 〜 round_trip_max_days）
        を満たす有効な連続うねりチェインを探索する。
        """
        n = len(zone_events)
        valid_chains: List[List[Tuple[str, PivotPoint]]] = []
        max_explored_chains = 500  # 異常入力時の指数爆発防止上限

        min_half = self.config.half_trip_min_days
        max_half = self.config.half_trip_max_days
        min_rt = self.config.round_trip_min_days
        max_rt = self.config.round_trip_max_days

        def dfs(current_chain: List[Tuple[str, PivotPoint]], last_idx: int):
            if len(valid_chains) >= max_explored_chains:
                return
            if len(current_chain) >= 3:
                valid_chains.append(list(current_chain))

            last_role, last_piv = current_chain[-1]
            for nxt_idx in range(last_idx + 1, n):
                if len(valid_chains) >= max_explored_chains:
                    break
                nxt_role, nxt_piv = zone_events[nxt_idx]
                if nxt_role == last_role:
                    continue

                half_days = nxt_piv.bar_index - last_piv.bar_index
                if half_days < min_half:
                    continue
                if half_days > max_half:
                    # これ以上先のピボットはさらに日数が開くため打ち切り
                    break

                # 2つ前（同一ロール）との一往復期間チェック
                if len(current_chain) >= 2:
                    prev_same_piv = current_chain[-2][1]
                    rt_days = nxt_piv.bar_index - prev_same_piv.bar_index
                    if not (min_rt <= rt_days <= max_rt):
                        continue

                current_chain.append((nxt_role, nxt_piv))
                dfs(current_chain, nxt_idx)
                current_chain.pop()

        for start_i in range(n):
            if len(valid_chains) >= max_explored_chains:
                break
            dfs([zone_events[start_i]], start_i)

        return valid_chains

    # ================================================================
    # 5. 接近状態・無効化警戒・通知の判定（5.3章・8章）
    # ================================================================
    def classify_proximity_state(
        self,
        closes: Sequence[float],
        support_zone: PriceZone,
        resistance_zone: PriceZone,
    ) -> Tuple[str, str, float, float]:
        """
        現在値とS・R代表価格から、乖離率・上昇余地・状態・画面タブ種別を判定する。

        Returns:
            (state, tab_category, support_distance_pct, resistance_upside_pct)
        """
        current_close = closes[-1]
        s_price = support_zone.representative_price
        r_price = resistance_zone.representative_price

        # 8.1章: サポート乖離率は (現在値 - S) / S * 100
        s_dist_pct = (current_close - s_price) / s_price * 100.0
        # 8.1章: レジスタンスまでの上昇余地は (R - 現在値) / 現在値 * 100
        r_upside_pct = (r_price - current_close) / current_close * 100.0

        # 5.3章: 終値がS帯下限を2営業日連続で下回った場合、または 8.1章: S乖離率が-2%以下の場合 → 下抜け警戒
        consec_days = self.config.breakdown_consecutive_days
        is_consecutive_below_lower = (
            len(closes) >= consec_days
            and all(c < support_zone.lower_bound for c in closes[-consec_days:])
        )
        if s_dist_pct <= self.config.support_breakdown_percent or is_consecutive_below_lower:
            return STATE_BREAKDOWN_WARNING, TAB_BREAKDOWN, s_dist_pct, r_upside_pct

        # 8.1章: サポート接近段階（5%, 3%, 1%以下）
        lvl_watch, lvl_buy, lvl_reach = self.config.support_alert_levels  # (5.0, 3.0, 1.0)
        if s_dist_pct <= lvl_reach:
            return STATE_SUPPORT_REACHED, TAB_BUY_ACTIVE, s_dist_pct, r_upside_pct
        if s_dist_pct <= lvl_buy:
            return STATE_BUY_CONSIDER, TAB_BUY_ACTIVE, s_dist_pct, r_upside_pct
        if s_dist_pct <= lvl_watch:
            return STATE_WATCH_START, TAB_BUY_WATCH, s_dist_pct, r_upside_pct

        # 8.1章: レジスタンス接近段階（5%, 3%以下）
        r_watch, r_consider = self.config.resistance_alert_levels  # (5.0, 3.0)
        if 0.0 <= r_upside_pct <= r_consider:
            return STATE_PROFIT_CONSIDER, TAB_PROFIT_TAKE, s_dist_pct, r_upside_pct
        if 0.0 <= r_upside_pct <= r_watch:
            return STATE_PROFIT_WATCH, TAB_PROFIT_TAKE, s_dist_pct, r_upside_pct

        return STATE_NEUTRAL, STATE_NEUTRAL, s_dist_pct, r_upside_pct

    # ================================================================
    # 6. 週足参考情報の計算（7章）
    # ================================================================
    def calculate_weekly_context(
        self,
        weekly_highs: Sequence[float],
        weekly_lows: Sequence[float],
        current_close: float,
    ) -> WeeklyContext:
        """
        3年（156週）および5年（260週）の週足データから、
        長期レンジ位置（0〜100%）および長期サポート・長期レジスタンスを算出する（7章）。
        """
        if not weekly_highs or not weekly_lows or current_close <= 0:
            return WeeklyContext(None, None, None, None)

        w3 = self.config.weekly_3y_weeks
        w5 = self.config.weekly_5y_weeks

        # 3年レンジ位置
        highs_3y = weekly_highs[-w3:] if len(weekly_highs) >= 26 else []
        lows_3y = weekly_lows[-w3:] if len(weekly_lows) >= 26 else []
        pos_3y: Optional[float] = None
        low_3y_val: Optional[float] = None
        high_3y_val: Optional[float] = None
        if highs_3y and lows_3y:
            low_3y_val = float(min(lows_3y))
            high_3y_val = float(max(highs_3y))
            if high_3y_val > low_3y_val:
                pos_3y = max(0.0, min(100.0, (current_close - low_3y_val) / (high_3y_val - low_3y_val) * 100.0))

        # 5年レンジ位置（3年以上のデータがある場合）
        pos_5y: Optional[float] = None
        low_5y_val: Optional[float] = None
        high_5y_val: Optional[float] = None
        if len(weekly_highs) >= w3:
            highs_5y = weekly_highs[-w5:]
            lows_5y = weekly_lows[-w5:]
            low_5y_val = float(min(lows_5y))
            high_5y_val = float(max(highs_5y))
            if high_5y_val > low_5y_val:
                pos_5y = max(0.0, min(100.0, (current_close - low_5y_val) / (high_5y_val - low_5y_val) * 100.0))

        # 週足の山・谷から長期S/Rを抽出
        lt_support = self._find_weekly_cluster_level(
            weekly_lows[-w5:], is_low=True, current_close=current_close
        )
        lt_resistance = self._find_weekly_cluster_level(
            weekly_highs[-w5:], is_low=False, current_close=current_close
        )

        return WeeklyContext(
            range_position_3y=pos_3y,
            range_position_5y=pos_5y,
            long_term_support=lt_support,
            long_term_resistance=lt_resistance,
            low_3y=low_3y_val,
            high_3y=high_3y_val,
            low_5y=low_5y_val,
            high_5y=high_5y_val,
        )

    def _find_weekly_cluster_level(
        self,
        series: Sequence[float],
        is_low: bool,
        current_close: float,
    ) -> Optional[float]:
        """週足の谷（または山）が複数回集中する価格帯の代表価格を算出する"""
        w = self.config.weekly_pivot_window
        n = len(series)
        if n < 2 * w + 1:
            return None

        pivots: List[Tuple[int, float]] = []
        for i in range(w, n - w):
            val = series[i]
            neighbors = [series[j] for j in range(i - w, i + w + 1) if j != i]
            if is_low and val <= min(neighbors):
                pivots.append((i, float(val)))
            elif not is_low and val >= max(neighbors):
                pivots.append((i, float(val)))

        if len(pivots) < 2:
            return None

        tol = 0.05  # 週足長期帯は±5%で集約
        best_cluster: List[float] = []
        best_dist = float("inf")

        for _, seed_price in pivots:
            if seed_price <= 0:
                continue
            # 少なくとも4週以上離れたピボットのみ別接触としてカウント
            members: List[Tuple[int, float]] = []
            for idx, p_val in pivots:
                if abs(p_val - seed_price) / seed_price <= tol:
                    if not members or idx - members[-1][0] >= 4:
                        members.append((idx, p_val))
            if len(members) >= 2:
                med = float(statistics.median(m[1] for m in members))
                # 現在値に近い有力な長期S（現在値以下優先）または長期R（現在値以上優先）を選ぶ
                dist = abs(med - current_close)
                if (len(members) > len(best_cluster)) or (
                    len(members) == len(best_cluster) and dist < best_dist
                ):
                    best_cluster = [m[1] for m in members]
                    best_dist = dist

        if not best_cluster:
            return None
        return float(statistics.median(best_cluster))

    # ================================================================
    # 7. 単一銘柄の統合分析エントリポイント
    # ================================================================
    def analyze_stock(
        self,
        code: str,
        name: str,
        market: str,
        dates: Sequence[str],
        highs: Sequence[float],
        lows: Sequence[float],
        closes: Sequence[float],
        volumes: Sequence[float],
        weekly_highs: Optional[Sequence[float]] = None,
        weekly_lows: Optional[Sequence[float]] = None,
        previous_state: Optional[str] = None,
    ) -> Optional[UneriCandidate]:
        """
        1銘柄の日足・週足データから、うねり候補かどうかを判定し、
        S接近・R接近・下抜け警戒のいずれかに該当すれば UneriCandidate を返す。
        該当しない場合は None を返す。
        """
        # 1. データ量チェック（最低でも観測期間の半分＝約6か月＝120営業日以上必要）
        if len(closes) < 120:
            return None

        # 2. 20日平均出来高フィルター（100万株以上）
        liq_ok, avg_vol_20d, avg_val_20d = self.check_liquidity(closes, volumes)
        if not liq_ok:
            return None

        # 3. 日足観測期間（過去12か月＝250営業日）に切り出し
        lookback = self.config.daily_lookback_days
        obs_dates = dates[-lookback:]
        obs_highs = highs[-lookback:]
        obs_lows = lows[-lookback:]
        obs_closes = closes[-lookback:]
        total_bars = len(obs_closes)
        current_close = float(obs_closes[-1])
        as_of_date = str(obs_dates[-1])

        # 4. Stage A: 前後5営業日ピボット抽出 ＋ 8% ZigZag主要転換点抽出
        raw_pivots = self.extract_raw_pivots(obs_dates, obs_highs, obs_lows)
        major_pivots = self.filter_major_pivots(raw_pivots)
        if len(major_pivots) < 3:
            return None

        # 5. S帯・R帯の構築
        support_zones = self.build_price_zones(major_pivots, kind="support")
        resistance_zones = self.build_price_zones(major_pivots, kind="resistance")
        if not support_zones or not resistance_zones:
            return None

        # 6. 5.2章: 「採用するSは現在値以下にある最も近い有力なS（ただし下抜け警戒判定用に現在値の+5%未満にあるSも含める）」
        #         「採用するRは現在値以上にある最も近い有力なR」
        max_s_allowed = current_close / (1.0 - self.config.invalidation_drop_percent / 100.0)
        valid_supports = [
            s for s in support_zones
            if s.representative_price <= max_s_allowed
        ]
        # 現在値に近い順（Sは代表価格が高い順＝現在値に近い順）
        valid_supports.sort(
            key=lambda s: (
                s.representative_price <= current_close,  # 現在値以下を優先
                -abs(current_close - s.representative_price),
                s.touch_count,
            ),
            reverse=True,
        )

        valid_resistances = [
            r for r in resistance_zones
            if r.representative_price >= current_close * 0.97
        ]
        # 現在値に近い順（Rは代表価格が低い順＝現在値に近い順）
        valid_resistances.sort(
            key=lambda r: (
                r.representative_price >= current_close,  # 現在値以上を優先
                -abs(r.representative_price - current_close),
                r.touch_count,
            ),
            reverse=True,
        )

        # 7. 有効なS-Rペアでうねり判定を実行（最も現在値に近い有力ペアを採用）
        selected_pair: Optional[Tuple[PriceZone, PriceZone, WaveCycleMetrics]] = None
        for s_zone in valid_supports:
            for r_zone in valid_resistances:
                metrics = self.evaluate_wave_cycles(
                    support_zone=s_zone,
                    resistance_zone=r_zone,
                    major_pivots=major_pivots,
                    total_bars=total_bars,
                    closes=obs_closes,
                )
                if metrics is not None:
                    selected_pair = (s_zone, r_zone, metrics)
                    break
            if selected_pair is not None:
                break

        if selected_pair is None:
            return None

        s_zone, r_zone, wave_metrics = selected_pair

        # 8. Stage B: 現在値とS・Rの乖離計算および状態分類
        state, tab_category, s_dist_pct, r_upside_pct = self.classify_proximity_state(
            closes=obs_closes,
            support_zone=s_zone,
            resistance_zone=r_zone,
        )

        # どの接近状態（監視開始・買い検討・S到達・下抜け警戒・利確監視・利確検討）にも入っていない中間銘柄は一覧に出さない
        if state == STATE_NEUTRAL:
            return None

        # 9. 状態変化・新規買い接近通知の判定（8.2章 ＋ ユーザー要件1：買い接近時のみ通知）
        is_state_changed = (previous_state != state)
        is_new_buy_alert = (state in BUY_ALERT_STATES) and (previous_state != state)

        # 10. 週足参考情報の算出
        weekly_ctx = self.calculate_weekly_context(
            weekly_highs=weekly_highs or [],
            weekly_lows=weekly_lows or [],
            current_close=current_close,
        )

        return UneriCandidate(
            rank=0,
            code=str(code),
            name=name,
            market=market,
            close=current_close,
            as_of_date=as_of_date,
            avg_volume_20d=avg_vol_20d,
            avg_trading_value_20d=avg_val_20d,
            support_zone=s_zone,
            resistance_zone=r_zone,
            support_distance_pct=s_dist_pct,
            resistance_upside_pct=r_upside_pct,
            wave_metrics=wave_metrics,
            weekly_context=weekly_ctx,
            state=state,
            state_label=STATE_DISPLAY_LABELS.get(state, state),
            tab_category=tab_category,
            previous_state=previous_state,
            is_new_buy_alert=is_new_buy_alert,
            is_state_changed=is_state_changed,
        )
