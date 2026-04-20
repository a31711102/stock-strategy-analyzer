"""
ATR計算のユニットテスト

テスト対象: TechnicalIndicators.calculate_atr()
テスト観点:
- True Range (TR) の正確性（3パターン: 通常、ギャップアップ、ギャップダウン）
- ATR（単純移動平均）の正確性
- データ不足時のNaN処理
- 複数period呼び出し時のTR重複防止
"""
import pytest
import pandas as pd
import numpy as np

from src.indicators.technical import TechnicalIndicators


def _make_ohlcv(highs, lows, closes, opens=None, volumes=None):
    """テスト用OHLCVデータフレームを生成"""
    n = len(closes)
    if opens is None:
        opens = closes  # 簡易的にCloseと同じ
    if volumes is None:
        volumes = [100000] * n
    
    df = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes,
    }, index=pd.date_range('2026-01-01', periods=n, freq='B'))
    return df


class TestTrueRangeCalculation:
    """True Range (TR) の計算テスト"""
    
    def test_normal_range(self):
        """通常のTR: High - Low が最大のケース"""
        # 前日終値=100, 当日High=110, Low=95
        # TR = max(110-95, |110-100|, |95-100|) = max(15, 10, 5) = 15
        df = _make_ohlcv(
            highs=[100, 110],
            lows=[95, 95],
            closes=[100, 105],
        )
        result = TechnicalIndicators.calculate_atr(df, period=1)
        
        # 2日目のTR
        assert result['TR'].iloc[1] == pytest.approx(15.0)
    
    def test_gap_up(self):
        """ギャップアップ: |High - 前日Close| が最大のケース"""
        # 前日終値=100, 当日High=120, Low=115
        # TR = max(120-115, |120-100|, |115-100|) = max(5, 20, 15) = 20
        df = _make_ohlcv(
            highs=[100, 120],
            lows=[95, 115],
            closes=[100, 118],
        )
        result = TechnicalIndicators.calculate_atr(df, period=1)
        
        assert result['TR'].iloc[1] == pytest.approx(20.0)
    
    def test_gap_down(self):
        """ギャップダウン: |Low - 前日Close| が最大のケース"""
        # 前日終値=100, 当日High=85, Low=75
        # TR = max(85-75, |85-100|, |75-100|) = max(10, 15, 25) = 25
        df = _make_ohlcv(
            highs=[100, 85],
            lows=[95, 75],
            closes=[100, 80],
        )
        result = TechnicalIndicators.calculate_atr(df, period=1)
        
        assert result['TR'].iloc[1] == pytest.approx(25.0)
    
    def test_first_day_tr(self):
        """初日のTR: 前日終値なしの場合 High - Low のみ"""
        df = _make_ohlcv(
            highs=[110],
            lows=[90],
            closes=[100],
        )
        result = TechnicalIndicators.calculate_atr(df, period=1)
        
        # 初日は前日終値がNaNなので、High - Low = 20
        assert result['TR'].iloc[0] == pytest.approx(20.0)


class TestATRCalculation:
    """ATR計算テスト"""
    
    def test_atr_period_1(self):
        """ATR(1) = TR そのもの"""
        df = _make_ohlcv(
            highs=[100, 110, 108],
            lows=[95, 95, 100],
            closes=[100, 105, 104],
        )
        result = TechnicalIndicators.calculate_atr(df, period=1)
        
        # ATR(1) = 最新のTR
        last_tr = result['TR'].iloc[-1]
        assert result['ATR_1'].iloc[-1] == pytest.approx(last_tr)
    
    def test_atr_period_2(self):
        """ATR(2) = 直近2日のTR平均"""
        df = _make_ohlcv(
            highs=[100, 110, 108],
            lows=[95, 95, 100],
            closes=[100, 105, 104],
        )
        result = TechnicalIndicators.calculate_atr(df, period=2)
        
        # 最後2つのTRの平均
        expected = (result['TR'].iloc[-2] + result['TR'].iloc[-1]) / 2
        assert result['ATR_2'].iloc[-1] == pytest.approx(expected)
    
    def test_atr_insufficient_data(self):
        """データ不足: period未満の場合NaN"""
        df = _make_ohlcv(
            highs=[100, 110],
            lows=[95, 95],
            closes=[100, 105],
        )
        result = TechnicalIndicators.calculate_atr(df, period=10)
        
        # 10日未満なのでATR_10は全てNaN
        assert result['ATR_10'].isna().all()
    
    def test_atr_column_naming(self):
        """ATRカラム名が正しいこと"""
        df = _make_ohlcv(
            highs=[100] * 15,
            lows=[90] * 15,
            closes=[95] * 15,
        )
        result = TechnicalIndicators.calculate_atr(df, period=10)
        
        assert 'ATR_10' in result.columns
        assert 'TR' in result.columns
    
    def test_multiple_periods_no_tr_duplication(self):
        """複数period呼び出し時にTRカラムが重複しないこと"""
        df = _make_ohlcv(
            highs=[100] * 25,
            lows=[90] * 25,
            closes=[95] * 25,
        )
        result = TechnicalIndicators.calculate_atr(df, period=10)
        result = TechnicalIndicators.calculate_atr(result, period=20)
        
        assert 'ATR_10' in result.columns
        assert 'ATR_20' in result.columns
        # TRカラムは1つだけ
        tr_cols = [c for c in result.columns if c == 'TR']
        assert len(tr_cols) == 1


class TestATRInAllIndicators:
    """calculate_all_indicators() で ATR が計算されることのテスト"""
    
    def test_atr_included_in_all_indicators(self):
        """全指標一括計算にATR(10)とATR(20)が含まれること"""
        # 十分なデータ数が必要
        n = 250
        np.random.seed(42)
        prices = 1000 + np.cumsum(np.random.randn(n) * 10)
        
        df = pd.DataFrame({
            'Open': prices - np.random.rand(n) * 5,
            'High': prices + np.abs(np.random.randn(n) * 10),
            'Low': prices - np.abs(np.random.randn(n) * 10),
            'Close': prices,
            'Volume': np.random.randint(100000, 1000000, n),
        }, index=pd.date_range('2025-01-01', periods=n, freq='B'))
        
        result = TechnicalIndicators.calculate_all_indicators(df)
        
        assert 'ATR_10' in result.columns
        assert 'ATR_20' in result.columns
        assert 'TR' in result.columns
        
        # 最後の行でATRが計算されていること
        assert pd.notna(result['ATR_10'].iloc[-1])
        assert pd.notna(result['ATR_20'].iloc[-1])
