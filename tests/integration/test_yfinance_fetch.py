"""
I1: yfinance データ取得の結合テスト

テスト対象: src/data/fetcher.py の StockDataFetcher（yfinance経由）

テスト観点:
- 有効な銘柄コードでデータ取得できること
- 無効な銘柄コードで None が返ること
- カラム標準化・日付ソートが正しいこと
- .T サフィックスの重複付与がないこと
"""
import pytest
import pandas as pd

from src.data.fetcher import StockDataFetcher


@pytest.fixture
def fetcher():
    """yfinance のみ使用する Fetcher（Stooq フォールバック無効）"""
    return StockDataFetcher(start_date='2024-01-01', use_fallback=False)


@pytest.mark.integration
class TestYfinanceFetch:
    """yfinance データ取得の結合テスト"""

    def test_valid_code(self, fetcher):
        """有効な銘柄コード（9432: NTT）でデータ取得可能"""
        df = fetcher.fetch_stock_data('9432')
        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_ohlcv_columns(self, fetcher):
        """OHLCV 全カラムが存在すること"""
        df = fetcher.fetch_stock_data('9432')
        assert df is not None
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            assert col in df.columns, f"カラム '{col}' が不足"

    def test_invalid_code(self, fetcher):
        """存在しない銘柄コード → None"""
        df = fetcher.fetch_stock_data('0000')
        assert df is None

    def test_with_t_suffix(self, fetcher):
        """既に .T が付いたコードでも正常取得（重複付与しない）"""
        df = fetcher.fetch_stock_data('9432.T')
        assert df is not None
        assert len(df) > 0

    def test_date_sorted_ascending(self, fetcher):
        """日付が古い順にソートされていること"""
        df = fetcher.fetch_stock_data('9432')
        assert df is not None
        assert df.index[0] < df.index[-1]

    def test_date_range(self, fetcher):
        """start_date=2024-01-01 のデータのみ"""
        df = fetcher.fetch_stock_data('9432')
        assert df is not None
        assert df.index.min().year >= 2024
