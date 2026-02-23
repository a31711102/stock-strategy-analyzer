"""
U1: テクニカル指標のユニットテスト

テスト対象: src/indicators/technical.py の TechnicalIndicators クラス

テスト観点:
- 各指標の計算精度（手計算の期待値と照合）
- 境界値（データ不足、空データ）
- calculate_all_indicators の統合動作
"""
import pytest
import pandas as pd
import numpy as np

from src.indicators.technical import TechnicalIndicators


# ---------------------------------------------------------------------------
# ヘルパー: テストデータ生成
# ---------------------------------------------------------------------------

def _make_ohlcv(close_values, volume=None):
    """Close配列からOHLCVデータフレームを生成する"""
    n = len(close_values)
    dates = pd.date_range('2024-01-01', periods=n, freq='B')
    close = np.array(close_values, dtype=float)
    data = {
        'Open': close - 0.5,
        'High': close + 1.0,
        'Low': close - 1.0,
        'Close': close,
        'Volume': volume if volume is not None else np.full(n, 1000.0),
    }
    return pd.DataFrame(data, index=dates)


# ===========================================================================
# Test: SMA (Simple Moving Average)
# ===========================================================================

class TestSMA:
    """SMA計算の正確性"""

    def test_sma_5_known_values(self, sample_ohlcv_10d):
        """SMA_5 が手計算値と一致すること"""
        df = TechnicalIndicators.calculate_ma(sample_ohlcv_10d.copy())

        # Close=[100,102,104,106,108,110,112,114,116,118]
        # SMA_5[4] = (100+102+104+106+108)/5 = 104.0
        assert df['SMA_5'].iloc[4] == pytest.approx(104.0)

        # SMA_5[9] = (110+112+114+116+118)/5 = 114.0
        assert df['SMA_5'].iloc[9] == pytest.approx(114.0)

    def test_sma_initial_nan(self, sample_ohlcv_10d):
        """SMA は期間未満の行で NaN であること"""
        df = TechnicalIndicators.calculate_ma(sample_ohlcv_10d.copy())
        # SMA_5 の先頭4行は NaN
        assert df['SMA_5'].iloc[:4].isna().all()
        # 5行目以降は非NaN
        assert df['SMA_5'].iloc[4:].notna().all()

    def test_sma_25_with_short_data(self, sample_ohlcv_10d):
        """データ不足時に SMA_25 が全て NaN であること"""
        df = TechnicalIndicators.calculate_ma(sample_ohlcv_10d.copy())
        assert df['SMA_25'].isna().all()


# ===========================================================================
# Test: EMA (Exponential Moving Average)
# ===========================================================================

class TestEMA:
    """EMA計算の正確性"""

    def test_ema_5_exists(self, sample_ohlcv_10d):
        """EMA_5 カラムが生成されること"""
        df = TechnicalIndicators.calculate_ma(sample_ohlcv_10d.copy())
        assert 'EMA_5' in df.columns

    def test_ema_5_first_value(self, sample_ohlcv_10d):
        """EMA_5 の初期値が Close[0] と一致すること（adjust=False の場合）"""
        df = TechnicalIndicators.calculate_ma(sample_ohlcv_10d.copy())
        # adjust=False の EMA は初期値 = Close[0]
        assert df['EMA_5'].iloc[0] == pytest.approx(100.0)

    def test_ema_converges_to_trend(self, sample_ohlcv_10d):
        """上昇トレンドで EMA_5 < Close（EMA は遅行する）"""
        df = TechnicalIndicators.calculate_ma(sample_ohlcv_10d.copy())
        # 終盤は EMA_5 < Close（EMAs lag behind in uptrend）
        assert df['EMA_5'].iloc[-1] < df['Close'].iloc[-1]


# ===========================================================================
# Test: MACD
# ===========================================================================

class TestMACD:
    """MACD, Signal, Histogram の計算"""

    def test_macd_columns_created(self, sample_ohlcv_300d):
        """MACD 関連の3カラムが生成されること"""
        df = TechnicalIndicators.calculate_macd(sample_ohlcv_300d.copy())
        assert 'MACD_12_26_9' in df.columns
        assert 'MACDs_12_26_9' in df.columns
        assert 'MACDh_12_26_9' in df.columns

    def test_macd_histogram_is_diff(self, sample_ohlcv_300d):
        """Histogram = MACD - Signal であること"""
        df = TechnicalIndicators.calculate_macd(sample_ohlcv_300d.copy())
        hist = df['MACDh_12_26_9']
        expected = df['MACD_12_26_9'] - df['MACDs_12_26_9']
        pd.testing.assert_series_equal(hist, expected, check_names=False)

    def test_macd_with_constant_price(self):
        """一定価格では MACD=0 となること"""
        df = _make_ohlcv([100.0] * 50)
        df = TechnicalIndicators.calculate_macd(df)
        # 十分なウォームアップ後、MACD ≈ 0
        assert df['MACD_12_26_9'].iloc[-1] == pytest.approx(0.0, abs=0.01)


# ===========================================================================
# Test: RSI
# ===========================================================================

class TestRSI:
    """RSI 計算の正確性"""

    def test_rsi_all_up(self):
        """全日上昇 → RSI = 100"""
        # 毎日+2ずつ上昇する15日間
        close = [100 + i * 2 for i in range(16)]
        df = _make_ohlcv(close)
        df = TechnicalIndicators.calculate_rsi(df, period=14)
        # loss=0 → RS=inf → RSI=100
        assert df['RSI_14'].iloc[-1] == pytest.approx(100.0)

    def test_rsi_all_down(self):
        """全日下落 → RSI = 0"""
        close = [200 - i * 2 for i in range(16)]
        df = _make_ohlcv(close)
        df = TechnicalIndicators.calculate_rsi(df, period=14)
        # gain=0 → RS=0 → RSI=0
        assert df['RSI_14'].iloc[-1] == pytest.approx(0.0)

    def test_rsi_range(self, sample_ohlcv_300d):
        """RSI は 0〜100 の範囲であること"""
        df = TechnicalIndicators.calculate_rsi(sample_ohlcv_300d.copy(), period=14)
        valid_rsi = df['RSI_14'].dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_rsi_initial_nan(self, sample_ohlcv_10d):
        """期間未満の行は NaN であること"""
        df = TechnicalIndicators.calculate_rsi(sample_ohlcv_10d.copy(), period=14)
        # 10日データで period=14 → 全て NaN（14日分の diff + rolling が必要）
        assert df['RSI_14'].isna().all()


# ===========================================================================
# Test: RCI
# ===========================================================================

class TestRCI:
    """RCI 計算の正確性"""

    def test_rci_perfect_uptrend(self):
        """完全上昇トレンド → RCI = 100"""
        close = list(range(1, 11))  # [1,2,3,...,10]
        df = _make_ohlcv(close)
        df = TechnicalIndicators.calculate_rci(df, period=9)
        # 日付順位と価格順位が完全一致 → RCI = 100
        assert df['RCI_9'].iloc[-1] == pytest.approx(100.0)

    def test_rci_perfect_downtrend(self):
        """完全下降トレンド → RCI = -100"""
        close = list(range(10, 0, -1))  # [10,9,8,...,1]
        df = _make_ohlcv(close)
        df = TechnicalIndicators.calculate_rci(df, period=9)
        # 日付順位と価格順位が完全逆 → RCI = -100
        assert df['RCI_9'].iloc[-1] == pytest.approx(-100.0)

    def test_rci_range(self, sample_ohlcv_300d):
        """RCI は -100〜+100 の範囲であること"""
        df = TechnicalIndicators.calculate_rci(sample_ohlcv_300d.copy(), period=9)
        valid_rci = df['RCI_9'].dropna()
        assert (valid_rci >= -100).all()
        assert (valid_rci <= 100).all()

    def test_rci_initial_nan(self, sample_ohlcv_10d):
        """期間未満の行は NaN であること"""
        df = TechnicalIndicators.calculate_rci(sample_ohlcv_10d.copy(), period=9)
        assert df['RCI_9'].iloc[:8].isna().all()


# ===========================================================================
# Test: Bollinger Bands
# ===========================================================================

class TestBollingerBands:
    """ボリンジャーバンドの計算"""

    def test_bb_constant_price(self):
        """一定価格 → 上限=下限=中心線（σ=0）"""
        df = _make_ohlcv([100.0] * 25)
        df = TechnicalIndicators.calculate_bollinger_bands(df, period=20, std=2.0)
        last = df.iloc[-1]
        assert last['BBM_20_2.0'] == pytest.approx(100.0)
        assert last['BBU_20_2.0'] == pytest.approx(100.0)
        assert last['BBL_20_2.0'] == pytest.approx(100.0)

    def test_bb_band_order(self, sample_ohlcv_300d):
        """BBL < BBM < BBU であること"""
        df = TechnicalIndicators.calculate_bollinger_bands(
            sample_ohlcv_300d.copy(), period=20, std=2.0
        )
        valid = df.dropna(subset=['BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0'])
        assert (valid['BBL_20_2.0'] <= valid['BBM_20_2.0']).all()
        assert (valid['BBM_20_2.0'] <= valid['BBU_20_2.0']).all()

    def test_bb_columns_with_std3(self, sample_ohlcv_300d):
        """std=3.0 のカラム名が正しいこと"""
        df = TechnicalIndicators.calculate_bollinger_bands(
            sample_ohlcv_300d.copy(), period=20, std=3.0
        )
        assert 'BBL_20_3.0' in df.columns
        assert 'BBM_20_3.0' in df.columns
        assert 'BBU_20_3.0' in df.columns


# ===========================================================================
# Test: Volume MA
# ===========================================================================

class TestVolumeMA:
    """出来高移動平均の計算"""

    def test_volume_ma_constant(self):
        """一定出来高 → MA = その値"""
        df = _make_ohlcv([100] * 30, volume=np.full(30, 5000.0))
        df = TechnicalIndicators.calculate_volume_ma(df, period=25)
        assert df['Volume_MA_25'].iloc[-1] == pytest.approx(5000.0)

    def test_volume_ma_known_values(self, sample_ohlcv_10d):
        """Volume=[1000..1900], period=5 → MA_5[4] = (1000+1100+1200+1300+1400)/5 = 1200"""
        df = TechnicalIndicators.calculate_volume_ma(sample_ohlcv_10d.copy(), period=5)
        assert df['Volume_MA_5'].iloc[4] == pytest.approx(1200.0)


# ===========================================================================
# Test: calculate_all_indicators (統合)
# ===========================================================================

class TestCalculateAllIndicators:
    """全指標一括計算の統合テスト"""

    def test_all_columns_exist(self, sample_ohlcv_300d):
        """必要な全カラムが生成されること"""
        df = TechnicalIndicators.calculate_all_indicators(sample_ohlcv_300d.copy())
        expected_columns = [
            'SMA_5', 'SMA_25', 'SMA_75', 'SMA_200',
            'EMA_5', 'EMA_25', 'EMA_75', 'EMA_200',
            'MACD_12_26_9', 'MACDs_12_26_9', 'MACDh_12_26_9',
            'RSI_14',
            'RCI_9', 'RCI_26',
            'BBL_20_3.0', 'BBM_20_3.0', 'BBU_20_3.0',
            'Volume_MA_25',
        ]
        for col in expected_columns:
            assert col in df.columns, f"カラム '{col}' が存在しません"

    def test_row_count_preserved(self, sample_ohlcv_300d):
        """行数が変わらないこと"""
        original_rows = len(sample_ohlcv_300d)
        df = TechnicalIndicators.calculate_all_indicators(sample_ohlcv_300d.copy())
        assert len(df) == original_rows

    def test_no_exception_with_short_data(self):
        """5日分のデータでも例外なく完了すること"""
        df = _make_ohlcv([100, 101, 102, 103, 104])
        result = TechnicalIndicators.calculate_all_indicators(df)
        assert len(result) == 5

    def test_empty_dataframe(self):
        """空DataFrameでも例外なく処理されること"""
        df = pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        result = TechnicalIndicators.calculate_all_indicators(df)
        assert len(result) == 0
