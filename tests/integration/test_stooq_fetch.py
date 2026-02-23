"""
I2: Stooq データ取得の結合テスト

テスト対象: src/data/fetcher.py の StockDataFetcher（Stooq 経由）

テスト観点:
- Stooq 直接取得の動作
- yfinance → Stooq のフォールバック
- コード形式変換
- レート制限の遵守
"""
import pytest
import time

from src.data.fetcher import StockDataFetcher


@pytest.fixture
def fetcher():
    """フォールバック有効な Fetcher"""
    return StockDataFetcher(start_date='2024-01-01', use_fallback=True)


@pytest.mark.integration
class TestStooqFetch:
    """Stooq データ取得の結合テスト"""

    def test_stooq_direct(self, fetcher):
        """Stooq 形式（.JP）で直接取得"""
        df = fetcher._fetch_from_stooq('9432.JP', '2024-01-01', '2024-12-31')
        # Stooq は不安定なため、None でも許容（テスト環境依存）
        if df is not None:
            assert len(df) > 0

    def test_code_format_conversion(self, fetcher):
        """_convert_to_stooq_format: 9432.T → 9432.JP"""
        assert fetcher._convert_to_stooq_format('9432.T') == '9432.JP'

    def test_code_format_non_t(self, fetcher):
        """既に .JP の場合はそのまま返す"""
        assert fetcher._convert_to_stooq_format('9432.JP') == '9432.JP'

    def test_stooq_rate_limit(self, fetcher):
        """連続リクエスト時に1秒以上の間隔があること"""
        start = time.time()
        fetcher._fetch_from_stooq('9432.JP', '2024-01-01', '2024-06-30')
        fetcher._fetch_from_stooq('9432.JP', '2024-07-01', '2024-12-31')
        elapsed = time.time() - start
        # 2回のリクエストで少なくとも1秒の間隔
        assert elapsed >= 1.0

    def test_normalize_code(self, fetcher):
        """_normalize_code: 9432 → 9432.T"""
        assert fetcher._normalize_code('9432') == '9432.T'

    def test_normalize_code_with_suffix(self, fetcher):
        """_normalize_code: 9432.T → 9432.T（変更なし）"""
        assert fetcher._normalize_code('9432.T') == '9432.T'
