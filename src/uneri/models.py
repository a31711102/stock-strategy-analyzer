"""
うねりチャート S/R接近通知システム: ドメインモデル定義

外部ライブラリ・フレームワークに依存しない純粋なデータクラス群。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple


# 状態識別子（定数）
STATE_SUPPORT_REACHED = "support_reached"         # S到達（S乖離 <= 1%）
STATE_BUY_CONSIDER = "buy_consider"               # 買い検討（S乖離 <= 3%）
STATE_WATCH_START = "watch_start"                 # 監視開始（S乖離 <= 5%）
STATE_BREAKDOWN_WARNING = "breakdown_warning"     # S下抜け（S乖離 <= -2% または S下限2日連続割れ）
STATE_PROFIT_CONSIDER = "profit_consider"         # 利確検討（R距離 <= 3%）
STATE_PROFIT_WATCH = "profit_watch"               # 利確監視（R距離 <= 5%）
STATE_NEUTRAL = "neutral"                         # 通常（上記いずれにも該当しない）

# 買い接近通知の対象となる状態集合（投資思想に基づき、サポート接近による買い時のみを通知対象とする）
BUY_ALERT_STATES = frozenset({
    STATE_SUPPORT_REACHED,
    STATE_BUY_CONSIDER,
    STATE_WATCH_START,
})

# 画面上の4つのタブ分類
TAB_BUY_ACTIVE = "buy_active"       # タブ1: 買い検討・S到達（S乖離 <= 3%）
TAB_BUY_WATCH = "buy_watch"         # タブ2: 監視開始（3% < S乖離 <= 5%）
TAB_PROFIT_TAKE = "profit_take"     # タブ3: 利確目安（R距離 <= 5%）
TAB_BREAKDOWN = "breakdown"         # タブ4: 下抜け警戒（S下抜け）

STATE_DISPLAY_LABELS = {
    STATE_SUPPORT_REACHED: "サポート到達",
    STATE_BUY_CONSIDER: "買い検討圏",
    STATE_WATCH_START: "サポート接近",
    STATE_BREAKDOWN_WARNING: "下抜け警戒",
    STATE_PROFIT_CONSIDER: "利確検討圏",
    STATE_PROFIT_WATCH: "レジスタンス接近",
    STATE_NEUTRAL: "レンジ中間",
}


@dataclass(frozen=True)
class PivotPoint:
    """日足の主要転換点（山または谷）"""
    kind: str          # 'low' (谷) または 'high' (山)
    date: str          # YYYY-MM-DD
    bar_index: int     # 観測対象時系列内の営業日インデックス（0始まり）
    price: float       # 谷なら安値(Low)、山なら高値(High)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "date": self.date,
            "bar_index": self.bar_index,
            "price": round(self.price, 1),
        }


@dataclass(frozen=True)
class PriceZone:
    """サポート帯（S帯）またはレジスタンス帯（R帯）"""
    kind: str                      # 'support' または 'resistance'
    representative_price: float    # 代表価格（中央値）
    lower_bound: float             # 帯の下限（代表価格 - 3%）
    upper_bound: float             # 帯の上限（代表価格 + 3%）
    touches: Tuple[PivotPoint, ...]  # 10営業日以上の間隔を満たした接触転換点

    @property
    def touch_count(self) -> int:
        return len(self.touches)

    def contains(self, price: float) -> bool:
        """指定価格がこの価格帯（下限〜上限）に含まれるか"""
        return self.lower_bound <= price <= self.upper_bound

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "representative_price": round(self.representative_price, 1),
            "lower_bound": round(self.lower_bound, 1),
            "upper_bound": round(self.upper_bound, 1),
            "touch_count": self.touch_count,
            "touches": [t.to_dict() for t in self.touches],
        }


# PriceZone内でTupleを使うためのインポート補完
from typing import Tuple


@dataclass(frozen=True)
class WaveCycleMetrics:
    """S-R間のうねり（往復）評価指標"""
    cycles: float                        # 往復数（例: 1.5, 2.0, 2.5）
    latest_round_trip_days: int          # 直近の一往復営業日数（40〜90）
    average_round_trip_days: float       # 平均一往復営業日数
    sr_range_percent: float              # S-R間の値幅（%）：(R - S) / S * 100
    is_priority: bool                    # 2往復以上の優先候補か
    wave_pivots: Tuple[PivotPoint, ...]  # 判定に採用したS/R交互の転換点系列
    days_since_last_pivot: int           # 直近の転換点からの経過営業日数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycles": self.cycles,
            "latest_round_trip_days": self.latest_round_trip_days,
            "average_round_trip_days": round(self.average_round_trip_days, 1),
            "sr_range_percent": round(self.sr_range_percent, 2),
            "is_priority": self.is_priority,
            "wave_pivots": [p.to_dict() for p in self.wave_pivots],
            "days_since_last_pivot": self.days_since_last_pivot,
        }


@dataclass(frozen=True)
class WeeklyContext:
    """週足による長期ボックス参考情報（7章）"""
    range_position_3y: Optional[float]   # 3年安値を0、高値を100とした現在位置(%)
    range_position_5y: Optional[float]   # 5年安値を0、高値を100とした現在位置(%)
    long_term_support: Optional[float]   # 週足の谷が複数回集中する長期サポート代表価格
    long_term_resistance: Optional[float]  # 週足の山が複数回集中する長期レジスタンス代表価格
    low_3y: Optional[float] = None
    high_3y: Optional[float] = None
    low_5y: Optional[float] = None
    high_5y: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "range_position_3y": round(self.range_position_3y, 1) if self.range_position_3y is not None else None,
            "range_position_5y": round(self.range_position_5y, 1) if self.range_position_5y is not None else None,
            "long_term_support": round(self.long_term_support, 1) if self.long_term_support is not None else None,
            "long_term_resistance": round(self.long_term_resistance, 1) if self.long_term_resistance is not None else None,
            "low_3y": round(self.low_3y, 1) if self.low_3y is not None else None,
            "high_3y": round(self.high_3y, 1) if self.high_3y is not None else None,
            "low_5y": round(self.low_5y, 1) if self.low_5y is not None else None,
            "high_5y": round(self.high_5y, 1) if self.high_5y is not None else None,
        }


@dataclass
class UneriCandidate:
    """日次候補一覧の1銘柄分の出力モデル（10.1章）"""
    rank: int
    code: str
    name: str
    market: str
    close: float
    as_of_date: str

    # 流動性
    avg_volume_20d: float
    avg_trading_value_20d: float

    # サポート・レジスタンス
    support_zone: PriceZone
    resistance_zone: PriceZone
    support_distance_pct: float      # (現在値 - S) / S * 100
    resistance_upside_pct: float     # (R - 現在値) / 現在値 * 100

    # うねり指標
    wave_metrics: WaveCycleMetrics

    # 週足参考
    weekly_context: WeeklyContext

    # 状態・タブ・通知
    state: str                       # STATE_* 定数
    state_label: str                 # 表示名（サポート到達、買い検討圏 など）
    tab_category: str                # TAB_* 定数（画面タブ振り分け用）
    previous_state: Optional[str] = None
    is_new_buy_alert: bool = False   # 新たに買い接近状態（監視開始・買い検討・S到達）へ遷移したか
    is_state_changed: bool = False   # 前回から状態が変化したか

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "code": self.code,
            "name": self.name,
            "market": self.market,
            "close": round(self.close, 1),
            "as_of_date": self.as_of_date,
            "avg_volume_20d": round(self.avg_volume_20d, 0),
            "avg_trading_value_20d": round(self.avg_trading_value_20d, 0),
            "support": {
                "price": round(self.support_zone.representative_price, 1),
                "lower": round(self.support_zone.lower_bound, 1),
                "upper": round(self.support_zone.upper_bound, 1),
                "touch_count": self.support_zone.touch_count,
                "distance_pct": round(self.support_distance_pct, 2),
                "touches": [t.to_dict() for t in self.support_zone.touches],
            },
            "resistance": {
                "price": round(self.resistance_zone.representative_price, 1),
                "lower": round(self.resistance_zone.lower_bound, 1),
                "upper": round(self.resistance_zone.upper_bound, 1),
                "touch_count": self.resistance_zone.touch_count,
                "upside_pct": round(self.resistance_upside_pct, 2),
                "touches": [t.to_dict() for t in self.resistance_zone.touches],
            },
            "wave": self.wave_metrics.to_dict(),
            "weekly": self.weekly_context.to_dict(),
            "state": self.state,
            "state_label": self.state_label,
            "tab_category": self.tab_category,
            "previous_state": self.previous_state,
            "is_new_buy_alert": self.is_new_buy_alert,
            "is_state_changed": self.is_state_changed,
        }
