"""
性能テスト用フィクスチャ

ローカル生成データでネットワーク不要・再現可能
"""
import pytest
import numpy as np
import pandas as pd

from src.indicators.technical import TechnicalIndicators


def _generate_ohlcv(rows: int, seed: int = 42) -> pd.DataFrame:
    """テスト用 OHLCV データをローカル生成（再現可能）"""
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range('2005-01-01', periods=rows)

    close = 1000 + np.cumsum(rng.randn(rows) * 10)
    high = close + rng.rand(rows) * 20
    low = close - rng.rand(rows) * 20
    open_ = close + rng.randn(rows) * 5
    volume = rng.randint(100_000, 1_000_000, rows)

    return pd.DataFrame({
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume,
    }, index=dates)


@pytest.fixture
def df_300():
    """300行の OHLCV データ（約1年分）"""
    return _generate_ohlcv(300)


@pytest.fixture
def df_4800():
    """4800行の OHLCV データ（約20年分・実運用相当）"""
    return _generate_ohlcv(4800)


@pytest.fixture
def df_100():
    """100行の OHLCV データ（従来版比較用・安全なデータ量）"""
    return _generate_ohlcv(100)


@pytest.fixture
def df_300_with_indicators(df_300):
    """300行 + テクニカル指標付き"""
    return TechnicalIndicators.calculate_all_indicators(df_300.copy())


@pytest.fixture
def df_4800_with_indicators(df_4800):
    """4800行 + テクニカル指標付き"""
    return TechnicalIndicators.calculate_all_indicators(df_4800.copy())


@pytest.fixture
def df_100_with_indicators(df_100):
    """100行 + テクニカル指標付き（従来版比較用）"""
    return TechnicalIndicators.calculate_all_indicators(df_100.copy())
