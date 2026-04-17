"""
Project-low-hunter: データクラス定義

Domain層で使用するデータ構造を定義する。
外部ライブラリに依存しない純粋なデータクラス。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UniverseStock:
    """ユニバース（フィルタ通過後）の1銘柄の情報"""
    code: str
    name: str
    beta: float
    norm_atr: float
    avg_volume_5d: float
    prev_close: float
    atr_10: float


@dataclass(frozen=True)
class BacktestResult:
    """1銘柄×1下落率パターンのバックテスト結果"""
    drop_pct: float        # 検証した下落率（例: -3.2）
    trading_days: int      # 検証対象の全営業日数
    hit_count: int         # 指値にヒット（Low ≤ target）した日数
    win_count: int         # 勝ちトレード数（Close > target_price）
    win_rate: float        # 勝率 = win_count / hit_count × 100（%）
    median_return: float   # 中央値リターン（%）


@dataclass
class TheOneResult:
    """最終出力: 1銘柄＝1レコードの「最強の指値」"""
    rank: int
    ticker: str
    name: str
    best_drop_pct: float
    target_price: float
    win_rate: float
    win_count: int
    median_return: float
    hit_count: int
    beta: float
    norm_atr: float
    prev_close: float
    atr_10: float

    def to_dict(self) -> dict:
        """JSON シリアライズ用辞書"""
        return {
            'rank': self.rank,
            'ticker': self.ticker,
            'name': self.name,
            'best_drop_pct': round(self.best_drop_pct, 1),
            'target_price': round(self.target_price, 1),
            'win_rate': round(self.win_rate, 1),
            'win_count': self.win_count,
            'median_return': round(self.median_return, 2),
            'hit_count': self.hit_count,
            'beta': round(self.beta, 2),
            'norm_atr': round(self.norm_atr, 2),
            'prev_close': round(self.prev_close, 1),
            'atr_10': round(self.atr_10, 1),
        }
