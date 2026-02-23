"""
投資手法モジュール

8つの投資戦略を提供:
- 買い手法（Long）: 4つ
- 空売り手法（Short）: 4つ
"""
from typing import List

from .base import BaseStrategy
from .breakout_new_high_long import BreakoutNewHighLong
from .pullback_buy_long import PullbackBuyLong
from .retry_new_high_long import RetryNewHighLong
from .trend_reversal_up_long import TrendReversalUpLong
from .pullback_short import PullbackShort
from .breakout_new_low_short import BreakoutNewLowShort
from .trend_reversal_down_short import TrendReversalDownShort
from .momentum_short import MomentumShort


# 全戦略クラスのマッピング
STRATEGY_MAP = {
    'breakout_new_high_long': BreakoutNewHighLong,
    'pullback_buy_long': PullbackBuyLong,
    'retry_new_high_long': RetryNewHighLong,
    'trend_reversal_up_long': TrendReversalUpLong,
    'pullback_short': PullbackShort,
    'breakout_new_low_short': BreakoutNewLowShort,
    'trend_reversal_down_short': TrendReversalDownShort,
    'momentum_short': MomentumShort,
}


def get_all_strategies() -> List[BaseStrategy]:
    """
    全ての投資戦略インスタンスを取得
    
    Returns:
        全戦略のインスタンスリスト
    """
    return [cls() for cls in STRATEGY_MAP.values()]


def get_strategy_by_name(name: str) -> BaseStrategy:
    """
    戦略名からインスタンスを取得
    
    Args:
        name: 戦略名（例: 'breakout_new_high_long'）
        
    Returns:
        戦略インスタンス
        
    Raises:
        ValueError: 不明な戦略名の場合
    """
    if name not in STRATEGY_MAP:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_MAP.keys())}")
    return STRATEGY_MAP[name]()


def get_long_strategies() -> List[BaseStrategy]:
    """買い手法のみを取得"""
    return [
        BreakoutNewHighLong(),
        PullbackBuyLong(),
        RetryNewHighLong(),
        TrendReversalUpLong(),
    ]


def get_short_strategies() -> List[BaseStrategy]:
    """空売り手法のみを取得"""
    return [
        PullbackShort(),
        BreakoutNewLowShort(),
        TrendReversalDownShort(),
        MomentumShort(),
    ]


__all__ = [
    'BaseStrategy',
    'BreakoutNewHighLong',
    'PullbackBuyLong',
    'RetryNewHighLong',
    'TrendReversalUpLong',
    'PullbackShort',
    'BreakoutNewLowShort',
    'TrendReversalDownShort',
    'MomentumShort',
    'get_all_strategies',
    'get_strategy_by_name',
    'get_long_strategies',
    'get_short_strategies',
    'STRATEGY_MAP',
]
