"""
VolatilityAnalyzer のユニットテスト

テスト対象: src.analysis.volatility.VolatilityAnalyzer
テスト観点:
- ATR%正規化の正確性
- パーセンタイルベースのカテゴリ分類（境界値テスト含む）
- 9パターンの組み合わせ判定
- レシオ方式の傾向分析
- パーセンタイル閾値算出
- build_atr_info() 統合テスト
"""
import pytest
import pandas as pd
import numpy as np

from src.analysis.volatility import VolatilityAnalyzer


def _make_df_with_atr(atr_10_values, atr_20_values=None, close_values=None):
    """ATRカラムを含むテスト用DataFrame生成"""
    n = len(atr_10_values)
    if close_values is None:
        close_values = [1000.0] * n
    if atr_20_values is None:
        atr_20_values = atr_10_values
    
    df = pd.DataFrame({
        'Open': close_values,
        'High': [c + 10 for c in close_values],
        'Low': [c - 10 for c in close_values],
        'Close': close_values,
        'Volume': [100000] * n,
        'ATR_10': atr_10_values,
        'ATR_20': atr_20_values,
    }, index=pd.date_range('2026-01-01', periods=n, freq='B'))
    return df


class TestCalculateATRPct:
    """ATR%の計算テスト"""
    
    def test_normal_calculation(self):
        """正常系: ATR% = (ATR / Close) × 100"""
        df = _make_df_with_atr(
            atr_10_values=[20.0],
            close_values=[1000.0],
        )
        result = VolatilityAnalyzer.calculate_atr_pct(df, 10)
        
        assert result == pytest.approx(2.0)  # (20/1000)*100
    
    def test_high_price_stock(self):
        """高株価銘柄: ATRが大きくてもATR%は適切"""
        df = _make_df_with_atr(
            atr_10_values=[500.0],
            close_values=[50000.0],
        )
        result = VolatilityAnalyzer.calculate_atr_pct(df, 10)
        
        assert result == pytest.approx(1.0)  # (500/50000)*100
    
    def test_low_price_stock(self):
        """低株価銘柄: ATRが小さくてもATR%は適切"""
        df = _make_df_with_atr(
            atr_10_values=[10.0],
            close_values=[200.0],
        )
        result = VolatilityAnalyzer.calculate_atr_pct(df, 10)
        
        assert result == pytest.approx(5.0)  # (10/200)*100
    
    def test_zero_close(self):
        """終値がゼロの場合: Noneを返す"""
        df = _make_df_with_atr(
            atr_10_values=[10.0],
            close_values=[0.0],
        )
        result = VolatilityAnalyzer.calculate_atr_pct(df, 10)
        
        assert result is None
    
    def test_nan_atr(self):
        """ATRがNaNの場合: Noneを返す"""
        df = _make_df_with_atr(
            atr_10_values=[float('nan')],
        )
        result = VolatilityAnalyzer.calculate_atr_pct(df, 10)
        
        assert result is None
    
    def test_missing_atr_column(self):
        """ATRカラムが存在しない場合: Noneを返す"""
        df = pd.DataFrame({
            'Close': [1000.0],
        }, index=pd.date_range('2026-01-01', periods=1))
        
        result = VolatilityAnalyzer.calculate_atr_pct(df, 10)
        
        assert result is None


class TestClassifyVolatility:
    """カテゴリ分類テスト"""
    
    def test_high_volatility(self):
        """高ボラ: p75以上"""
        result = VolatilityAnalyzer.classify_volatility(4.0, p25=1.0, p75=3.0)
        assert result == "high"
    
    def test_mid_volatility(self):
        """中ボラ: p25とp75の間"""
        result = VolatilityAnalyzer.classify_volatility(2.0, p25=1.0, p75=3.0)
        assert result == "mid"
    
    def test_low_volatility(self):
        """低ボラ: p25以下"""
        result = VolatilityAnalyzer.classify_volatility(0.5, p25=1.0, p75=3.0)
        assert result == "low"
    
    def test_boundary_p75(self):
        """境界値: ちょうどp75は高ボラ"""
        result = VolatilityAnalyzer.classify_volatility(3.0, p25=1.0, p75=3.0)
        assert result == "high"
    
    def test_boundary_p25(self):
        """境界値: ちょうどp25は低ボラ"""
        result = VolatilityAnalyzer.classify_volatility(1.0, p25=1.0, p75=3.0)
        assert result == "low"
    
    def test_none_input(self):
        """None入力: 空文字"""
        result = VolatilityAnalyzer.classify_volatility(None, p25=1.0, p75=3.0)
        assert result == ""


class TestGetVolatilityPattern:
    """9パターン組み合わせ判定テスト"""
    
    @pytest.mark.parametrize("cat_10, cat_20, expected", [
        ("high", "high", "恒常高ボラ"),
        ("high", "mid", "短期急変"),
        ("high", "low", "異常変動"),
        ("mid", "high", "ボラ沈静化"),
        ("mid", "mid", "標準"),
        ("mid", "low", "やや活発化"),
        ("low", "high", "急収束型"),
        ("low", "mid", "直近静穏"),
        ("low", "low", "恒常低ボラ"),
    ])
    def test_all_patterns(self, cat_10, cat_20, expected):
        """全9パターンが正しく判定されること"""
        result = VolatilityAnalyzer.get_volatility_pattern(cat_10, cat_20)
        assert result == expected
    
    def test_empty_category_10(self):
        """category_10が空: 空文字"""
        result = VolatilityAnalyzer.get_volatility_pattern("", "high")
        assert result == ""
    
    def test_empty_category_20(self):
        """category_20が空: 空文字"""
        result = VolatilityAnalyzer.get_volatility_pattern("high", "")
        assert result == ""


class TestDetectTrend:
    """傾向分析（レシオ方式）テスト"""
    
    def test_expanding(self):
        """拡大傾向: ratio > 1.10"""
        # ベースラインが低く、直近が高い
        atr_values = [10.0] * 13 + [15.0]  # 14期間: 13個の10と1個の15
        df = _make_df_with_atr(atr_10_values=atr_values)
        
        trend, ratio = VolatilityAnalyzer.detect_trend(df, short_period=10)
        
        # ratio = 15.0 / mean([10]*13 + [15]) = 15.0 / 10.357... ≈ 1.448
        assert trend == "expanding"
        assert ratio > 1.10
    
    def test_contracting(self):
        """縮小傾向: ratio < 0.90"""
        # ベースラインが高く、直近が低い
        atr_values = [20.0] * 13 + [10.0]  # 14期間: 13個の20と1個の10
        df = _make_df_with_atr(atr_10_values=atr_values)
        
        trend, ratio = VolatilityAnalyzer.detect_trend(df, short_period=10)
        
        # ratio = 10.0 / mean([20]*13 + [10]) = 10.0 / 19.28... ≈ 0.518
        assert trend == "contracting"
        assert ratio < 0.90
    
    def test_stable(self):
        """横ばい: 0.90 <= ratio <= 1.10"""
        # 全て同じ値
        atr_values = [10.0] * 14
        df = _make_df_with_atr(atr_10_values=atr_values)
        
        trend, ratio = VolatilityAnalyzer.detect_trend(df, short_period=10)
        
        assert trend == "stable"
        assert ratio == pytest.approx(1.0)
    
    def test_insufficient_data(self):
        """データ不足: 空文字と0.0"""
        atr_values = [10.0] * 5  # 14期間未満
        df = _make_df_with_atr(atr_10_values=atr_values)
        
        trend, ratio = VolatilityAnalyzer.detect_trend(df, short_period=10)
        
        assert trend == ""
        assert ratio == 0.0
    
    def test_zero_baseline(self):
        """ベースラインがゼロ: stable, ratio=1.0"""
        atr_values = [0.0] * 14
        df = _make_df_with_atr(atr_10_values=atr_values)
        
        trend, ratio = VolatilityAnalyzer.detect_trend(df, short_period=10)
        
        assert trend == "stable"
        assert ratio == 1.0


class TestCalculateThresholds:
    """パーセンタイル閾値算出テスト"""
    
    def test_normal(self):
        """正常系: p25とp75が正しく算出されること"""
        values = list(range(1, 101))  # 1~100
        result = VolatilityAnalyzer.calculate_thresholds(values)
        
        assert result["p25"] == pytest.approx(25.75)  # numpy percentile
        assert result["p75"] == pytest.approx(75.25)
    
    def test_small_dataset(self):
        """小データ: 最低4件で計算可能"""
        values = [1.0, 2.0, 3.0, 4.0]
        result = VolatilityAnalyzer.calculate_thresholds(values)
        
        assert result["p25"] > 0
        assert result["p75"] > 0
    
    def test_too_few_data(self):
        """データ不足: 3件以下はフォールバック"""
        values = [1.0, 2.0, 3.0]
        result = VolatilityAnalyzer.calculate_thresholds(values)
        
        assert result["p25"] == 0.0
        assert result["p75"] == 0.0
    
    def test_empty_list(self):
        """空リスト"""
        result = VolatilityAnalyzer.calculate_thresholds([])
        
        assert result["p25"] == 0.0
        assert result["p75"] == 0.0
    
    def test_uniform_values(self):
        """全同値: p25 == p75（全銘柄がmidになる）"""
        values = [5.0] * 100
        result = VolatilityAnalyzer.calculate_thresholds(values)
        
        assert result["p25"] == result["p75"]


class TestBuildATRInfo:
    """build_atr_info() 統合テスト"""
    
    def test_full_info(self):
        """全情報が正しく生成されること"""
        atr_values = [20.0] * 14
        df = _make_df_with_atr(
            atr_10_values=atr_values,
            atr_20_values=atr_values,
            close_values=[1000.0] * 14,
        )
        
        thresholds_10 = {"p25": 1.0, "p75": 3.0}
        thresholds_20 = {"p25": 0.8, "p75": 2.5}
        
        result = VolatilityAnalyzer.build_atr_info(df, thresholds_10, thresholds_20)
        
        assert result["atr_10"] == 20.0
        assert result["atr_20"] == 20.0
        assert result["atr_pct_10"] == pytest.approx(2.0)
        assert result["atr_pct_20"] == pytest.approx(2.0)
        assert result["volatility_category_10"] == "mid"
        assert result["volatility_category_20"] == "mid"
        assert result["volatility_pattern"] == "標準"
        assert result["volatility_trend"] == "stable"
        assert result["atr_ratio"] == pytest.approx(1.0)
    
    def test_no_thresholds(self):
        """閾値なし: カテゴリ・パターンは空文字"""
        atr_values = [20.0] * 14
        df = _make_df_with_atr(atr_10_values=atr_values)
        
        result = VolatilityAnalyzer.build_atr_info(df)  # 閾値なし
        
        assert result["atr_10"] == 20.0
        assert result["atr_pct_10"] > 0
        assert result["volatility_category_10"] == ""
        assert result["volatility_category_20"] == ""
        assert result["volatility_pattern"] == ""
        # 傾向はATR時系列から計算可能
        assert result["volatility_trend"] in ("expanding", "contracting", "stable")
    
    def test_empty_df(self):
        """空DataFrame: 全デフォルト値"""
        df = pd.DataFrame()
        
        result = VolatilityAnalyzer.build_atr_info(df)
        
        assert result["atr_10"] == 0.0
        assert result["atr_20"] == 0.0
        assert result["volatility_trend"] == ""
    
    def test_none_df(self):
        """None DataFrame: 全デフォルト値"""
        result = VolatilityAnalyzer.build_atr_info(None)
        
        assert result["atr_10"] == 0.0
        assert result["atr_ratio"] == 0.0
