"""
テスト共通フィクスチャ

全テストで再利用するデータ生成ヘルパーとフィクスチャを定義
"""
import sys
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def sample_ohlcv_10d():
    """10日間の固定OHLCVデータ（手計算可能なテスト用）"""
    dates = pd.date_range('2024-01-01', periods=10, freq='B')
    data = {
        'Open':   [100, 102, 104, 106, 108, 110, 112, 114, 116, 118],
        'High':   [101, 103, 105, 107, 109, 111, 113, 115, 117, 119],
        'Low':    [ 99, 101, 103, 105, 107, 109, 111, 113, 115, 117],
        'Close':  [100, 102, 104, 106, 108, 110, 112, 114, 116, 118],
        'Volume': [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900],
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def sample_ohlcv_300d():
    """300日間のOHLCVデータ（全指標計算に十分な長さ）"""
    np.random.seed(42)
    n = 300
    dates = pd.date_range('2023-01-01', periods=n, freq='B')

    # 緩やかな上昇トレンド + ノイズ
    close = 1000 + np.cumsum(np.random.randn(n) * 2)
    high = close + np.abs(np.random.randn(n)) * 3
    low = close - np.abs(np.random.randn(n)) * 3
    open_ = close + np.random.randn(n) * 1.5

    data = {
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': np.random.randint(50000, 200000, n).astype(float),
    }
    return pd.DataFrame(data, index=dates)
