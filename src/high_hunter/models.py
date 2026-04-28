"""
Project-high-hunter: データクラス定義
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestResultShort:
    """1銘柄×1上昇率パターンのバックテスト結果（空売り）"""
    rise_pct: float        # 検証した上昇率（例: 3.2）
    trading_days: int      # 検証対象の全営業日数
    hit_count: int         # 指値にヒット（High >= target）した日数
    win_count: int         # 勝ちトレード数（Close < target_price）
    win_rate: float        # 勝率 = win_count / hit_count × 100（%）
    median_return: float   # 中央値リターン（%）


@dataclass
class TheOneShortResult:
    """最終出力: 1銘柄＝1レコードの「最強の空売り指値」"""
    rank: int
    ticker: str
    name: str
    best_rise_pct: float
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
            'best_rise_pct': round(self.best_rise_pct, 1),
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
