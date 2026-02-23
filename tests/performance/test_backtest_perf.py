"""
P2: バックテストエンジンの性能テスト

テスト対象: BacktestEngine.run_backtest()

テスト観点:
- 1銘柄×1戦略 < 0.5秒
- 1銘柄×8戦略 < 3.0秒
- ベクトル化 vs 従来版（8戦略、100行）: ベクトル化 ≥ 1.0x
- 4800行×1戦略 < 2.0秒
"""
import time
import pytest
import yaml
import os
import tempfile

from src.backtest.engine import BacktestEngine
from src.strategies import get_all_strategies


@pytest.fixture
def engine(tmp_path):
    """テスト用バックテストエンジン（一時config使用）"""
    config = {
        'backtest': {
            'initial_capital': 1_000_000,
            'cash_commission_rate': 0.001,
            'cash_slippage': 0.001,
            'margin_commission_rate': 0.001,
            'margin_lending_rate': 0.01,
            'margin_slippage': 0.001,
            'max_years': None,
            'use_vectorized': True,
            'holding_period': {
                'target_days': 14,
                'max_days': 30,
            },
            'trailing_stop': {
                'enabled': True,
                'long_threshold': 0.10,
                'short_threshold': 0.10,
            },
        }
    }
    config_path = str(tmp_path / 'config.yaml')
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return BacktestEngine(config_path)


@pytest.fixture
def engine_legacy(tmp_path):
    """従来版バックテストエンジン"""
    config = {
        'backtest': {
            'initial_capital': 1_000_000,
            'cash_commission_rate': 0.001,
            'cash_slippage': 0.001,
            'margin_commission_rate': 0.001,
            'margin_lending_rate': 0.01,
            'margin_slippage': 0.001,
            'max_years': None,
            'use_vectorized': False,
            'holding_period': {
                'target_days': 14,
                'max_days': 30,
            },
            'trailing_stop': {
                'enabled': True,
                'long_threshold': 0.10,
                'short_threshold': 0.10,
            },
        }
    }
    config_path = str(tmp_path / 'config_legacy.yaml')
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return BacktestEngine(config_path)


@pytest.fixture
def all_strategies():
    """全8戦略"""
    return get_all_strategies()


@pytest.mark.performance
class TestBacktestPerformance:
    """バックテストエンジンの性能テスト"""

    def test_single_strategy_300(self, engine, df_300_with_indicators, all_strategies):
        """P2-1: 1銘柄×1戦略（300行）< 0.5秒"""
        strategy = all_strategies[0]
        start = time.perf_counter()
        engine.run_backtest(df_300_with_indicators.copy(), strategy, '9999')
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"1戦略の処理時間: {elapsed:.3f}秒（閾値: 0.5秒）"

    def test_all_strategies_300(self, engine, df_300_with_indicators, all_strategies):
        """P2-2: 1銘柄×8戦略（300行）< 3.0秒"""
        start = time.perf_counter()
        for strategy in all_strategies:
            engine.run_backtest(df_300_with_indicators.copy(), strategy, '9999')
        elapsed = time.perf_counter() - start

        assert elapsed < 3.0, (
            f"8戦略の合計処理時間: {elapsed:.3f}秒（閾値: 3.0秒）"
        )

    def test_vectorized_vs_legacy(
        self, engine, engine_legacy,
        df_100_with_indicators, all_strategies
    ):
        """P2-3: ベクトル化 vs 従来版（8戦略、100行）: ベクトル化 ≥ 1.0x"""
        df = df_100_with_indicators

        # ベクトル化版
        start = time.perf_counter()
        for strategy in all_strategies:
            engine.run_backtest(df.copy(), strategy, '9999')
        vectorized_time = time.perf_counter() - start

        # 従来版
        start = time.perf_counter()
        for strategy in all_strategies:
            engine_legacy.run_backtest(df.copy(), strategy, '9999')
        legacy_time = time.perf_counter() - start

        # ベクトル化版が従来版以上であること
        if legacy_time > 0.001:
            speedup = legacy_time / vectorized_time if vectorized_time > 0 else float('inf')
            assert speedup >= 1.0, (
                f"ベクトル化: {vectorized_time:.3f}秒, "
                f"従来版: {legacy_time:.3f}秒, "
                f"速度比: {speedup:.2f}x（期待: ≥ 1.0x）"
            )

    def test_single_strategy_4800(self, engine, df_4800_with_indicators, all_strategies):
        """P2-4: 4800行×1戦略 < 2.0秒"""
        strategy = all_strategies[0]
        start = time.perf_counter()
        engine.run_backtest(df_4800_with_indicators.copy(), strategy, '9999')
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"4800行×1戦略の処理時間: {elapsed:.3f}秒（閾値: 2.0秒）"
