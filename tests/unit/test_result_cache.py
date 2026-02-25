"""
U6: 結果キャッシュのユニットテスト

テスト対象: src/batch/result_cache.py の ResultCache

テスト観点:
- ランキングの保存・読込・件数制限
- 進捗の保存・読込・クリア
- 接近シグナルの保存・読込
- 戦略一覧の取得
- メタデータの更新
"""
import pytest
import json
import os
import tempfile
import shutil

from src.batch.result_cache import ResultCache


@pytest.fixture
def cache(tmp_path):
    """一時ディレクトリで ResultCache を生成"""
    return ResultCache(cache_dir=str(tmp_path))


# ===========================================================================
# Test: ランキング保存・読込
# ===========================================================================

class TestRanking:

    def test_save_and_load(self, cache):
        """保存したランキングデータが読み込めること"""
        rankings = [
            {'code': '9432', 'score': 85.0, 'reason': '良好'},
            {'code': '7203', 'score': 72.0, 'reason': '普通'},
            {'code': '1332', 'score': 60.0, 'reason': '可'},
        ]
        assert cache.save_ranking('breakout_new_high_long', rankings)

        loaded = cache.load_ranking('breakout_new_high_long')
        assert len(loaded) == 3
        assert loaded[0]['code'] == '9432'
        assert loaded[0]['score'] == 85.0

    def test_load_with_limit(self, cache):
        """limit 指定で件数を制限できること"""
        rankings = [{'code': str(i), 'score': float(100 - i)} for i in range(10)]
        cache.save_ranking('test_strategy', rankings)

        loaded = cache.load_ranking('test_strategy', limit=3)
        assert len(loaded) == 3

    def test_load_with_offset(self, cache):
        """offset 指定でスキップできること"""
        rankings = [{'code': str(i), 'score': float(100 - i)} for i in range(10)]
        cache.save_ranking('test_strategy', rankings)

        loaded = cache.load_ranking('test_strategy', limit=3, offset=2)
        assert len(loaded) == 3
        assert loaded[0]['code'] == '2'

    def test_load_nonexistent_strategy(self, cache):
        """存在しない戦略名は空リスト"""
        loaded = cache.load_ranking('nonexistent')
        assert loaded == []


# ===========================================================================
# Test: 進捗保存・読込
# ===========================================================================

class TestProgress:

    def test_save_and_load(self, cache):
        """進捗データの保存と読込が一致すること"""
        processed = ['9432', '7203', '1332']
        failed = ['0000']
        cache.save_progress(processed, failed)

        progress = cache.load_progress()
        assert progress is not None
        assert set(progress['processed_codes']) == set(processed)
        assert set(progress['failed_codes']) == set(failed)

    def test_load_no_progress(self, cache):
        """進捗未保存時は None"""
        assert cache.load_progress() is None

    def test_clear_progress(self, cache):
        """クリア後は None"""
        cache.save_progress(['9432'], [])
        cache.clear_progress()
        assert cache.load_progress() is None


# ===========================================================================
# Test: 接近シグナル
# ===========================================================================

class TestApproachingSignals:

    def test_save_and_load(self, cache):
        """接近シグナルの保存・読込"""
        signals = [
            {'code': '9432', 'estimated_days': 2, 'conditions': ['条件A']},
            {'code': '7203', 'estimated_days': 5, 'conditions': ['条件B']},
        ]
        assert cache.save_approaching_signals('breakout', signals)

        loaded = cache.load_approaching_signals('breakout')
        assert len(loaded) == 2
        assert loaded[0]['code'] == '9432'

    def test_load_nonexistent(self, cache):
        """存在しない戦略名は空リスト"""
        loaded = cache.load_approaching_signals('nonexistent')
        assert loaded == []

    def test_save_and_load_with_avg_volume(self, cache):
        """avg_volume を含むデータが保存・読込で保持されること"""
        signals = [
            {
                'code': '9432', 'name': 'NTT',
                'estimated_days': 2, 'score': 80.0,
                'conditions_met': ['条件A'], 'conditions_pending': [],
                'current_price': 150.0, 'last_updated': '2026-02-24',
                'avg_volume': 1_200_000.0,
            },
            {
                'code': '7203', 'name': 'トヨタ',
                'estimated_days': 5, 'score': 60.0,
                'conditions_met': [], 'conditions_pending': ['条件B'],
                'current_price': 2500.0, 'last_updated': '2026-02-24',
                'avg_volume': 750_000.0,
            },
        ]
        assert cache.save_approaching_signals('breakout', signals)

        loaded = cache.load_approaching_signals('breakout')
        assert len(loaded) == 2
        assert loaded[0]['avg_volume'] == 1_200_000.0
        assert loaded[1]['avg_volume'] == 750_000.0

    def test_load_with_limit_50(self, cache):
        """limit=50 で件数が正しく制限されること"""
        signals = [
            {'code': str(i), 'score': float(100 - i), 'avg_volume': float(500_000 + i * 1000)}
            for i in range(60)
        ]
        cache.save_approaching_signals('test_strategy', signals)

        loaded = cache.load_approaching_signals('test_strategy', limit=50)
        assert len(loaded) == 50


# ===========================================================================
# Test: 戦略一覧
# ===========================================================================

class TestAvailableStrategies:

    def test_get_available_strategies(self, cache):
        """保存済み戦略名のリストが取得できること"""
        cache.save_ranking('strategy_a', [{'code': '1', 'score': 50}])
        cache.save_ranking('strategy_b', [{'code': '2', 'score': 40}])

        strategies = cache.get_available_strategies()
        assert 'strategy_a' in strategies
        assert 'strategy_b' in strategies

    def test_get_available_approaching_strategies(self, cache):
        """接近シグナル保存済み戦略名のリスト"""
        cache.save_approaching_signals('sig_a', [{'code': '1'}])
        strategies = cache.get_available_approaching_strategies()
        assert 'sig_a' in strategies


# ===========================================================================
# Test: メタデータ
# ===========================================================================

class TestMetadata:

    def test_update_and_get(self, cache):
        """メタデータ更新→取得"""
        stats = {'total_processed': 100, 'total_failed': 5}
        cache.update_metadata(stats)

        meta = cache.get_metadata()
        assert meta['total_processed'] == 100
        assert meta['total_failed'] == 5

    def test_get_empty_metadata(self, cache):
        """メタデータ未保存時は空辞書"""
        meta = cache.get_metadata()
        assert meta == {}
