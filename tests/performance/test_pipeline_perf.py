"""
P3: バッチ1銘柄パイプラインの性能テスト

テスト対象: 指標計算→8戦略バックテスト→スコア算出の合計

テスト観点:
- パイプライン全体 < 5.0秒
- キャッシュ保存・読込 < 0.1秒
- メモリ使用量 < 100MB
"""
import time
import pytest
import yaml
import tracemalloc

from src.indicators.technical import TechnicalIndicators
from src.backtest.engine import BacktestEngine
from src.analysis.compatibility import CompatibilityAnalyzer
from src.strategies import get_all_strategies
from src.batch.result_cache import ResultCache


@pytest.fixture
def config_path(tmp_path):
    """テスト用 config ファイル"""
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
    path = str(tmp_path / 'config.yaml')
    with open(path, 'w') as f:
        yaml.dump(config, f)
    return path


@pytest.fixture
def all_strategies():
    """全8戦略"""
    return get_all_strategies()


@pytest.mark.performance
class TestPipelinePerformance:
    """パイプライン全体の性能テスト"""

    def test_full_pipeline_300(self, df_300, config_path, all_strategies):
        """P3-1: 指標計算→8戦略バックテスト→スコア算出 < 5.0秒"""
        start = time.perf_counter()

        # 1. テクニカル指標計算
        df = TechnicalIndicators.calculate_all_indicators(df_300.copy())

        # 2. 8戦略のバックテスト + 適合度計算
        analyzer = CompatibilityAnalyzer(config_path)
        analyzer.calculate_compatibility(
            stock_code='9999',
            df=df,
            strategies=all_strategies,
        )

        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, (
            f"パイプライン全体: {elapsed:.3f}秒（閾値: 5.0秒）"
        )

    def test_cache_io_speed(self, tmp_path):
        """P3-2: キャッシュ保存・読込 < 0.1秒"""
        cache = ResultCache(cache_dir=str(tmp_path))

        # テスト用ランキングデータ（8戦略×100銘柄）
        strategy_names = [f'strategy_{i}' for i in range(8)]
        ranking_data = [
            {
                'code': str(1000 + j),
                'name': f'銘柄{j}',
                'score': 80.0 - j,
                'win_rate': 55.0,
                'total_return': 10.0,
                'num_trades': 20,
            }
            for j in range(100)
        ]

        # 保存（戦略ごとに保存）
        start = time.perf_counter()
        for name in strategy_names:
            cache.save_ranking(name, ranking_data)
        save_time = time.perf_counter() - start

        # 読込（戦略ごとに読込）
        start = time.perf_counter()
        for name in strategy_names:
            loaded = cache.load_ranking(name)
        load_time = time.perf_counter() - start

        total = save_time + load_time

        assert total < 0.5, (
            f"キャッシュI/O: 保存{save_time:.4f}秒 + 読込{load_time:.4f}秒 "
            f"= {total:.4f}秒（閾値: 0.5秒）"
        )
        assert loaded is not None

    def test_memory_usage(self, df_300, config_path, all_strategies):
        """P3-3: 1銘柄処理のメモリ使用量 < 100MB"""
        tracemalloc.start()

        # パイプライン実行
        df = TechnicalIndicators.calculate_all_indicators(df_300.copy())
        analyzer = CompatibilityAnalyzer(config_path)
        analyzer.calculate_compatibility(
            stock_code='9999',
            df=df,
            strategies=all_strategies,
        )

        _, peak_mb = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak_mb / (1024 * 1024)

        assert peak_mb < 100, (
            f"ピークメモリ使用量: {peak_mb:.1f}MB（閾値: 100MB）"
        )
