"""
I4: データキャッシュの結合テスト

テスト対象: src/data/cache.py の DataCache

テスト観点:
- ファイルI/Oによるキャッシュ保存・読込
- 有効期限（TTL）の動作
- クリア操作
"""
import pytest
import pandas as pd
import numpy as np
import time

from src.data.cache import DataCache


@pytest.fixture
def cache(tmp_path):
    """一時ディレクトリで DataCache を生成"""
    return DataCache(cache_dir=str(tmp_path), ttl_hours=24)


@pytest.fixture
def sample_df():
    """テスト用 OHLCV データ"""
    dates = pd.date_range('2024-01-01', periods=10, freq='B')
    return pd.DataFrame({
        'Open': np.random.rand(10) * 100,
        'High': np.random.rand(10) * 100,
        'Low': np.random.rand(10) * 100,
        'Close': np.random.rand(10) * 100,
        'Volume': np.random.randint(1000, 10000, 10),
    }, index=dates)


class TestDataCache:
    """データキャッシュの結合テスト"""

    def test_save_and_load(self, cache, sample_df):
        """保存したデータがロードできること"""
        cache.set('9432', sample_df)
        loaded = cache.get('9432')
        assert loaded is not None
        assert len(loaded) == len(sample_df)

    def test_cache_miss(self, cache):
        """未保存コードで None"""
        assert cache.get('0000') is None

    def test_cache_expiry(self, tmp_path, sample_df):
        """TTL=0 で即座に期限切れ"""
        expired_cache = DataCache(cache_dir=str(tmp_path), ttl_hours=0)
        expired_cache.set('9432', sample_df)
        # TTL=0 なので即座に期限切れ
        time.sleep(0.1)
        assert expired_cache.get('9432') is None

    def test_clear_single(self, cache, sample_df):
        """単一銘柄のキャッシュクリア"""
        cache.set('9432', sample_df)
        cache.set('7203', sample_df)
        cache.clear('9432')
        assert cache.get('9432') is None
        assert cache.get('7203') is not None

    def test_clear_all(self, cache, sample_df):
        """全キャッシュクリア"""
        cache.set('9432', sample_df)
        cache.set('7203', sample_df)
        cache.clear()
        assert cache.get('9432') is None
        assert cache.get('7203') is None
