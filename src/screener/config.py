"""
ボラティリティ乖離スクリーナー: パラメータ定義

運用中に柔軟に変更する可能性のあるパラメータを集中管理する。
固定値（ケルトナー倍率等）もここで明示し、変更影響範囲を限定する。
"""

# === 第一段階: 流動性・需給フィルタ ===
# 5日平均出来高の下限（株数）
MIN_AVG_VOLUME_5D: int = 500_000

# 出来高急増比の上限（仕手化銘柄排除）
# Volume_MA_10 / Volume_MA_100 がこの値以上なら除外
MAX_VOLUME_RATIO: float = 5.0

# 信用倍率フィルタ（将来実装用）
# 現状は J-Quants Free Tier では取得不可のため無効
CREDIT_RATIO_MIN: float = 0.5   # 下限（空売り残が極端に少ない＝過熱）
CREDIT_RATIO_MAX: float = 10.0  # 上限（買い残が極端に多い＝需給悪化）
CREDIT_RATIO_ENABLED: bool = False  # 信用倍率フィルタの有効/無効

# === 第二段階: ボラティリティ評価 ===
# 正規化ATR（ATR_10 / Close × 100）の下限（%）
# 相場全体のボラが低下した場合、1.5 等に引き下げ可能
MIN_NORM_ATR: float = 2.0

# ランキング上位銘柄数
TOP_N: int = 20

# === 第三段階: ターゲット計算 ===
# ケルトナーチャネル乗数（固定値）
# P_buy = MA_25 - (ATR_10 × KELTNER_MULTIPLIER)
# P_stop = P_buy - (ATR_10 × KELTNER_MULTIPLIER)
KELTNER_MULTIPLIER: float = 1.5

# === ポジションサイジング ===
# デフォルト許容損失額（円）
DEFAULT_RISK_JPY: int = 30_000

# 単元株数（日本株は全て100株単位）
UNIT_SHARES: int = 100

# === トレンド判定 ===
# Range判定: 5日MAと25日MAの乖離率（%）がこの値以内
RANGE_THRESHOLD_PCT: float = 3.0

# === Proximity（近接度）===
# 赤字強調の閾値（%）: 現在値が Target_Buy にこの距離以内
PROXIMITY_ALERT_PCT: float = 1.0
