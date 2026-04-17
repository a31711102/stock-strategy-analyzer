"""
Project-low-hunter: パラメータ定義

運用中に調整する可能性のあるパラメータを集中管理する。
"""

# === バックテスト設定 ===
LOOKBACK_DAYS: int = 250          # 約1年分の営業日
DROP_RANGE_MIN: float = -1.0      # 検証する最小下落率（%）
DROP_RANGE_MAX: float = -7.0      # 検証する最大下落率（%）
DROP_STEP: float = 0.1            # 刻み幅（%）

# === フィルタ閾値 ===
MIN_WIN_RATE: float = 60.0        # 最低勝率（%）
MIN_WIN_COUNT: int = 10           # 最低勝ち回数
MIN_BETA: float = 1.2             # 最低β値
MIN_NORM_ATR: float = 2.0         # 最低Norm_ATR（%）
MIN_AVG_VOLUME: int = 1_000_000   # 最低5日平均出来高（株）

# === 有効データ ===
MIN_VALID_DAYS: int = 100         # β算出・BT実行に必要な最低営業日数

# === ポジションサイジング ===
DEFAULT_RISK_JPY: int = 30_000    # デフォルト許容損失額（円）
DEFAULT_UNIT_SHARES: int = 1      # デフォルト株数単位（デイトレ向け: 1株）

# === 日経平均 ===
NIKKEI225_INDEX_CODE: str = "^N225"

# === 日経225銘柄リスト取得 ===
NIKKEI225_URL: str = "https://indexes.nikkei.co.jp/nkave/index/component?idx=nk225"
NIKKEI225_CACHE_FILENAME: str = "nikkei225_cache.csv"
