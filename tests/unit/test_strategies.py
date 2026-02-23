"""
U5: 各戦略シグナル生成のユニットテスト

テスト対象: src/strategies/ 配下の8戦略クラス

テスト観点:
- name() / strategy_type() が正しい文字列を返すこと
- generate_signals() が pd.Series を返すこと
- シグナルが {-1, 0, 1} のみであること
- 指標付きOHLCVデータで例外なく実行可能であること
"""
import pytest
import pandas as pd
import numpy as np

from src.indicators.technical import TechnicalIndicators
from src.strategies.breakout_new_high_long import BreakoutNewHighLong
from src.strategies.pullback_buy_long import PullbackBuyLong
from src.strategies.retry_new_high_long import RetryNewHighLong
from src.strategies.trend_reversal_up_long import TrendReversalUpLong
from src.strategies.pullback_short import PullbackShort
from src.strategies.breakout_new_low_short import BreakoutNewLowShort
from src.strategies.trend_reversal_down_short import TrendReversalDownShort
from src.strategies.momentum_short import MomentumShort


# ---------------------------------------------------------------------------
# Fixture: 指標付きOHLCVデータ
# ---------------------------------------------------------------------------

@pytest.fixture
def indicator_df():
    """300日分の指標付きOHLCVデータ"""
    np.random.seed(42)
    n = 300
    dates = pd.date_range('2023-01-01', periods=n, freq='B')
    close = 1000 + np.cumsum(np.random.randn(n) * 5)
    high = close + np.abs(np.random.randn(n)) * 5
    low = close - np.abs(np.random.randn(n)) * 5
    open_ = close + np.random.randn(n) * 2

    df = pd.DataFrame({
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': np.random.randint(50000, 200000, n).astype(float),
    }, index=dates)

    return TechnicalIndicators.calculate_all_indicators(df)


# ---------------------------------------------------------------------------
# 戦略リスト: パラメタライズ用
# ---------------------------------------------------------------------------

STRATEGIES = [
    (BreakoutNewHighLong, 'BreakoutNewHighLong', 'long'),
    (PullbackBuyLong, 'PullbackBuyLong', 'long'),
    (RetryNewHighLong, 'RetryNewHighLong', 'long'),
    (TrendReversalUpLong, 'TrendReversalUpLong', 'long'),
    (PullbackShort, 'PullbackShort', 'short'),
    (BreakoutNewLowShort, 'BreakoutNewLowShort', 'short'),
    (TrendReversalDownShort, 'TrendReversalDownShort', 'short'),
    (MomentumShort, 'MomentumShort', 'short'),
]


@pytest.fixture(params=STRATEGIES, ids=[s[1] for s in STRATEGIES])
def strategy_info(request):
    """(strategy_class, expected_name, expected_type)"""
    return request.param


# ===========================================================================
# Test: 共通インタフェース
# ===========================================================================

class TestStrategyInterface:
    """全戦略共通のインタフェーステスト"""

    def test_name_is_string(self, strategy_info):
        """name() が非空文字列を返すこと"""
        cls, expected_name, _ = strategy_info
        strategy = cls()
        name = strategy.name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_strategy_type_valid(self, strategy_info):
        """strategy_type() が 'long' or 'short' であること"""
        cls, _, expected_type = strategy_info
        strategy = cls()
        assert strategy.strategy_type() == expected_type

    def test_generate_signals_returns_series(self, strategy_info, indicator_df):
        """generate_signals() が pd.Series を返すこと"""
        cls, _, _ = strategy_info
        strategy = cls()
        signals = strategy.generate_signals(indicator_df.copy())
        assert isinstance(signals, pd.Series)

    def test_generate_signals_length(self, strategy_info, indicator_df):
        """シグナルのの長さがデータ行数と一致すること"""
        cls, _, _ = strategy_info
        strategy = cls()
        signals = strategy.generate_signals(indicator_df.copy())
        assert len(signals) == len(indicator_df)

    def test_signals_valid_values(self, strategy_info, indicator_df):
        """シグナルが {-1, 0, 1} のみであること"""
        cls, _, _ = strategy_info
        strategy = cls()
        signals = strategy.generate_signals(indicator_df.copy())
        unique_values = set(signals.unique())
        assert unique_values.issubset({-1, 0, 1})

    def test_get_description(self, strategy_info):
        """get_description() が非空文字列を返すこと"""
        cls, _, _ = strategy_info
        strategy = cls()
        desc = strategy.get_description()
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_get_parameters(self, strategy_info):
        """get_parameters() が辞書を返すこと"""
        cls, _, _ = strategy_info
        strategy = cls()
        params = strategy.get_parameters()
        assert isinstance(params, dict)
