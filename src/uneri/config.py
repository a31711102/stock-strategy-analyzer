"""
うねりチャート S/R接近通知システム: 設定定義

要件定義書 第12章の設定項目および内部閾値を保持する。
外部フレームワークに依存しない不変データクラスとして定義。
"""
from dataclasses import dataclass
from typing import Tuple, Dict, Any


@dataclass(frozen=True)
class UneriConfig:
    """うねり検出・接近判定の設定パラメータ"""

    # 流動性フィルター（3.1章・12章）
    average_volume_days: int = 20
    minimum_average_volume: int = 1_000_000

    # 山と谷の抽出（5.1章・12章）
    pivot_window_days: int = 5
    minimum_swing_percent: float = 8.0

    # 価格帯への集約（5.2章・12章）
    price_zone_percent: float = 3.0
    minimum_touch_count_s: int = 2
    minimum_touch_count_r: int = 2
    minimum_touch_gap_days: int = 10

    # 無効化条件（5.3章）
    breakdown_consecutive_days: int = 2
    invalidation_drop_percent: float = 5.0
    breakout_clear_percent: float = 3.0  # R帯上限またはR代表価格を明確に上抜けた判定用

    # うねり判定（6章・12章）
    half_trip_min_days: int = 15
    half_trip_max_days: int = 50
    round_trip_min_days: int = 40
    round_trip_max_days: int = 90
    standard_cycle_days: int = 60
    min_sr_range_percent: float = 8.0
    minimum_cycles: float = 1.5
    priority_cycles: float = 2.0
    daily_lookback_days: int = 250  # 過去約12か月（営業日換算）

    # 週足参考表示（7章）
    weekly_3y_weeks: int = 156  # 3年 = 52週 × 3
    weekly_5y_weeks: int = 260  # 5年 = 52週 × 5
    weekly_pivot_window: int = 3  # 週足の谷・山抽出ウィンドウ

    # 接近判定と通知（8章・12章）
    support_alert_levels: Tuple[float, float, float] = (5.0, 3.0, 1.0)
    support_breakdown_percent: float = -2.0
    resistance_alert_levels: Tuple[float, float] = (5.0, 3.0)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UneriConfig":
        """辞書（config.yaml の uneri セクション等）から UneriConfig を生成する"""
        if not data:
            return cls()

        kwargs: Dict[str, Any] = {}
        int_fields = (
            "average_volume_days",
            "minimum_average_volume",
            "pivot_window_days",
            "minimum_touch_count_s",
            "minimum_touch_count_r",
            "minimum_touch_gap_days",
            "breakdown_consecutive_days",
            "half_trip_min_days",
            "half_trip_max_days",
            "round_trip_min_days",
            "round_trip_max_days",
            "standard_cycle_days",
            "daily_lookback_days",
            "weekly_3y_weeks",
            "weekly_5y_weeks",
            "weekly_pivot_window",
        )
        float_fields = (
            "minimum_swing_percent",
            "price_zone_percent",
            "invalidation_drop_percent",
            "breakout_clear_percent",
            "min_sr_range_percent",
            "minimum_cycles",
            "priority_cycles",
            "support_breakdown_percent",
        )

        for f in int_fields:
            if f in data and data[f] is not None:
                kwargs[f] = int(data[f])

        for f in float_fields:
            if f in data and data[f] is not None:
                kwargs[f] = float(data[f])

        if "support_alert_levels" in data and data["support_alert_levels"]:
            vals = data["support_alert_levels"]
            if isinstance(vals, str):
                vals = [float(x) for x in vals.replace(",", " ").split()]
            else:
                vals = [float(x) for x in vals]
            if len(vals) >= 3:
                kwargs["support_alert_levels"] = (vals[0], vals[1], vals[2])

        if "resistance_alert_levels" in data and data["resistance_alert_levels"]:
            vals = data["resistance_alert_levels"]
            if isinstance(vals, str):
                vals = [float(x) for x in vals.replace(",", " ").split()]
            else:
                vals = [float(x) for x in vals]
            if len(vals) >= 2:
                kwargs["resistance_alert_levels"] = (vals[0], vals[1])

        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """設定内容をJSON出力用辞書へ変換する"""
        return {
            "average_volume_days": self.average_volume_days,
            "minimum_average_volume": self.minimum_average_volume,
            "pivot_window_days": self.pivot_window_days,
            "minimum_swing_percent": self.minimum_swing_percent,
            "price_zone_percent": self.price_zone_percent,
            "minimum_touch_gap_days": self.minimum_touch_gap_days,
            "half_trip_min_days": self.half_trip_min_days,
            "half_trip_max_days": self.half_trip_max_days,
            "round_trip_min_days": self.round_trip_min_days,
            "round_trip_max_days": self.round_trip_max_days,
            "min_sr_range_percent": self.min_sr_range_percent,
            "minimum_cycles": self.minimum_cycles,
            "support_alert_levels": list(self.support_alert_levels),
            "resistance_alert_levels": list(self.resistance_alert_levels),
        }
