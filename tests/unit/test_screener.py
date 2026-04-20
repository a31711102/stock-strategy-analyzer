"""
ボラティリティ乖離スクリーナー Unit Test

テスト対象:
- LiquidityFilter: 流動性フィルタの境界値テスト
- VolatilityEvaluator: Norm_ATR閾値、RVRソート、Top-N
- TargetCalculator: ケルトナー計算精度、ポジションサイジング、未満株判定
- TrendJudge: Up/Down/Range/Sideways の4パターン判定
- ScreenerPipeline: 三段階フィルタの統合テスト
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.screener.liquidity_filter import LiquidityFilter, LiquidityFilterParams
from src.screener.volatility_evaluator import (
    VolatilityEvaluator, VolatilityEvalParams, VolatilityScore,
)
from src.screener.target_calculator import TargetCalculator, ScreenerResult
from src.screener.trend_judge import (
    TrendJudge, STATUS_UP, STATUS_DOWN, STATUS_RANGE, STATUS_SIDEWAYS,
)
from src.screener.pipeline import ScreenerPipeline


# ============================================================
# ヘルパー: モックDataFrame生成
# ============================================================


def _make_df(
    close: float = 1000.0,
    sma_5: float = 1010.0,
    sma_25: float = 1000.0,
    sma_75: float = 990.0,
    atr_10: float = 30.0,
    atr_100: float = 15.0,
    volume_ma_5: float = 600_000,
    volume_ma_10: float = 550_000,
    volume_ma_100: float = 500_000,
    volume_ma_25: float = 500_000,
    rows: int = 1,
) -> pd.DataFrame:
    """テスト用に直近1行（or複数行）の指標付きDataFrameを生成"""
    idx = pd.date_range(end=datetime.now(), periods=rows, freq='B')
    data = {
        'Open': [close] * rows,
        'High': [close * 1.02] * rows,
        'Low': [close * 0.98] * rows,
        'Close': [close] * rows,
        'Volume': [600_000] * rows,
        'SMA_5': [sma_5] * rows,
        'SMA_25': [sma_25] * rows,
        'SMA_75': [sma_75] * rows,
        'ATR_10': [atr_10] * rows,
        'ATR_20': [atr_10 * 0.9] * rows,
        'ATR_100': [atr_100] * rows,
        'Volume_MA_5': [volume_ma_5] * rows,
        'Volume_MA_10': [volume_ma_10] * rows,
        'Volume_MA_25': [volume_ma_25] * rows,
        'Volume_MA_100': [volume_ma_100] * rows,
    }
    return pd.DataFrame(data, index=idx)


# ============================================================
# LiquidityFilter テスト
# ============================================================


class TestLiquidityFilter:
    """第一段階フィルタのテスト"""

    def test_passes_all_conditions(self):
        """全条件を満たす銘柄は通過する"""
        f = LiquidityFilter()
        df = _make_df(volume_ma_5=600_000, volume_ma_10=500_000, volume_ma_100=400_000)
        result = f.apply({"9984": df})
        assert "9984" in result

    def test_rejects_low_volume(self):
        """出来高不足の銘柄は除外される"""
        f = LiquidityFilter()
        df = _make_df(volume_ma_5=100_000)
        result = f.apply({"1234": df})
        assert "1234" not in result

    def test_rejects_volume_spike(self):
        """仕手化銘柄（出来高急増比 ≧ 5.0）は除外される"""
        f = LiquidityFilter()
        # Volume_MA_10 / Volume_MA_100 = 600_000 / 100_000 = 6.0 ≧ 5.0
        df = _make_df(volume_ma_5=600_000, volume_ma_10=600_000, volume_ma_100=100_000)
        result = f.apply({"5678": df})
        assert "5678" not in result

    def test_boundary_volume_exactly_500k(self):
        """境界値: 出来高ちょうど500,000は通過する"""
        f = LiquidityFilter()
        df = _make_df(volume_ma_5=500_000)
        result = f.apply({"9999": df})
        assert "9999" in result

    def test_boundary_volume_ratio_exactly_5(self):
        """境界値: 出来高急増比ちょうど5.0は除外される"""
        f = LiquidityFilter()
        df = _make_df(volume_ma_5=600_000, volume_ma_10=500_000, volume_ma_100=100_000)
        result = f.apply({"1111": df})
        assert "1111" not in result

    def test_credit_ratio_disabled_by_default(self):
        """信用倍率フィルタはデフォルトで無効"""
        f = LiquidityFilter()
        assert not f.params.credit_ratio_enabled

    def test_empty_dataframe_rejected(self):
        """空のDataFrameは除外される"""
        f = LiquidityFilter()
        result = f.apply({"1234": pd.DataFrame()})
        assert result == []

    def test_none_dataframe_rejected(self):
        """NoneのDataFrameは除外される"""
        f = LiquidityFilter()
        result = f.apply({"1234": None})
        assert result == []


# ============================================================
# VolatilityEvaluator テスト
# ============================================================


class TestVolatilityEvaluator:
    """第二段階: ボラティリティ評価のテスト"""

    def test_norm_atr_passes(self):
        """Norm_ATR ≧ 2.0% の銘柄は通過する"""
        ev = VolatilityEvaluator()
        # ATR_10=30, Close=1000 → Norm_ATR = 3.0%
        df = _make_df(close=1000, atr_10=30, atr_100=15)
        result = ev.evaluate(["9984"], {"9984": df})
        assert len(result) == 1
        assert result[0].norm_atr == 3.0

    def test_norm_atr_rejects_low(self):
        """Norm_ATR < 2.0% の銘柄は除外される"""
        ev = VolatilityEvaluator()
        # ATR_10=10, Close=1000 → Norm_ATR = 1.0%
        df = _make_df(close=1000, atr_10=10, atr_100=8)
        result = ev.evaluate(["1111"], {"1111": df})
        assert len(result) == 0

    def test_norm_atr_boundary_exactly_2pct(self):
        """境界値: Norm_ATR = 2.0% ちょうどは通過する"""
        ev = VolatilityEvaluator()
        # ATR_10=20, Close=1000 → Norm_ATR = 2.0%
        df = _make_df(close=1000, atr_10=20, atr_100=10)
        result = ev.evaluate(["2222"], {"2222": df})
        assert len(result) == 1

    def test_rvr_ranking(self):
        """RVR降順でソートされる"""
        ev = VolatilityEvaluator(params=VolatilityEvalParams(top_n=10))
        stocks = {
            "A": _make_df(close=1000, atr_10=30, atr_100=15),   # RVR=2.0
            "B": _make_df(close=1000, atr_10=30, atr_100=10),   # RVR=3.0
            "C": _make_df(close=1000, atr_10=30, atr_100=20),   # RVR=1.5
        }
        result = ev.evaluate(["A", "B", "C"], stocks)
        assert [s.code for s in result] == ["B", "A", "C"]

    def test_top_n_limit(self):
        """上位N銘柄のみ返される"""
        ev = VolatilityEvaluator(params=VolatilityEvalParams(top_n=2))
        stocks = {}
        for i in range(5):
            stocks[str(i)] = _make_df(close=1000, atr_10=30, atr_100=10 + i)
        result = ev.evaluate(list(stocks.keys()), stocks)
        assert len(result) == 2

    def test_zero_close_rejected(self):
        """終値が0の銘柄は除外される"""
        ev = VolatilityEvaluator()
        df = _make_df(close=0, atr_10=30, atr_100=15)
        result = ev.evaluate(["X"], {"X": df})
        assert len(result) == 0

    def test_configurable_min_norm_atr(self):
        """MIN_NORM_ATRパラメータの変更が反映される"""
        ev = VolatilityEvaluator(params=VolatilityEvalParams(min_norm_atr=1.5))
        # ATR_10=15, Close=1000 → Norm_ATR = 1.5%
        df = _make_df(close=1000, atr_10=15, atr_100=10)
        result = ev.evaluate(["AAA"], {"AAA": df})
        assert len(result) == 1


# ============================================================
# TargetCalculator テスト
# ============================================================


class TestTargetCalculator:
    """第三段階: ターゲット計算のテスト"""

    def _make_vol_score(
        self, code="9984", atr_10=265.0, atr_100=112.8, close=8572.0
    ):
        return VolatilityScore(
            code=code,
            norm_atr=round(atr_10 / close * 100, 3),
            rvr=round(atr_10 / atr_100, 3),
            atr_10=atr_10,
            atr_100=atr_100,
            close=close,
        )

    def test_keltner_calculation(self):
        """ケルトナーロジックの計算精度"""
        tc = TargetCalculator(risk_jpy=30_000)
        vs = self._make_vol_score(atr_10=100.0, close=1000.0)
        df = _make_df(close=1000.0, sma_25=1000.0, atr_10=100.0, atr_100=50.0)

        result = tc.calculate(vs, df, name="テスト銘柄", rank=1)
        assert result is not None
        # target_buy = 1000 - (100 × 2.0) = 800
        assert result.target_buy == 800.0
        # stop_loss = 800 - (100 × 2.0) = 600
        assert result.stop_loss == 600.0

    def test_position_sizing_normal(self):
        """正常なポジションサイジング"""
        tc = TargetCalculator(risk_jpy=30_000)
        # R_unit = 100 × 2.0 = 200
        # Qty = floor(30000 / (200 × 100)) × 100 = floor(1.5) × 100 = 100
        vs = self._make_vol_score(atr_10=100.0, close=1000.0)
        df = _make_df(close=1000.0, sma_25=1000.0, atr_10=100.0, atr_100=50.0)

        result = tc.calculate(vs, df, name="テスト銘柄", rank=1)
        assert result.quantity == 100
        assert not result.is_sub_unit

    def test_position_sizing_sub_unit(self):
        """ATRが大きすぎて100株未満になるケース → 未満株"""
        tc = TargetCalculator(risk_jpy=30_000)
        # R_unit = 500 × 2.0 = 1000
        # Qty = floor(30000 / (1000 × 100)) × 100 = floor(0.3) × 100 = 0
        vs = self._make_vol_score(atr_10=500.0, close=5000.0)
        df = _make_df(close=5000.0, sma_25=5000.0, atr_10=500.0, atr_100=200.0)

        result = tc.calculate(vs, df, name="テスト銘柄", rank=1)
        assert result.quantity == 0
        assert result.is_sub_unit

    def test_position_sizing_fractional_risk(self):
        """端数リスク額: 1.25万円 = 12500円"""
        tc = TargetCalculator(risk_jpy=12_500)
        # R_unit = 50 × 2.0 = 100
        # Qty = floor(12500 / (100 × 100)) × 100 = floor(1.25) × 100 = 100
        vs = self._make_vol_score(atr_10=50.0, close=1000.0)
        df = _make_df(close=1000.0, sma_25=1000.0, atr_10=50.0, atr_100=25.0)

        result = tc.calculate(vs, df, name="テスト銘柄", rank=1)
        assert result.quantity == 100

    def test_proximity_alert(self):
        """Proximity 1%以内でアラート"""
        tc = TargetCalculator(risk_jpy=30_000)
        # target_buy = 1000 - 200 = 800
        # close = 805 → proximity = |805-800|/805 = 0.62%
        vs = self._make_vol_score(atr_10=100.0, close=805.0)
        df = _make_df(close=805.0, sma_25=1000.0, atr_10=100.0, atr_100=50.0)

        result = tc.calculate(vs, df, name="テスト銘柄", rank=1)
        assert result.is_proximity_alert

    def test_negative_target_buy_rejected(self):
        """ATRが非常に大きくP_buyが負になる場合はNone"""
        tc = TargetCalculator(risk_jpy=30_000)
        vs = self._make_vol_score(atr_10=600.0, close=500.0)
        df = _make_df(close=500.0, sma_25=500.0, atr_10=600.0, atr_100=300.0)

        result = tc.calculate(vs, df, name="テスト銘柄", rank=1)
        assert result is None

    def test_capital_calculation(self):
        """必要概算資金の計算"""
        tc = TargetCalculator(risk_jpy=50_000)
        # R_unit = 50 × 2.0 = 100
        # Qty = floor(50000 / 10000) × 100 = 500
        # Capital = 800 × 500 = 400000
        vs = self._make_vol_score(atr_10=50.0, close=1000.0)
        df = _make_df(close=1000.0, sma_25=900.0, atr_10=50.0, atr_100=25.0)

        result = tc.calculate(vs, df, name="テスト銘柄", rank=1)
        # target_buy = 900 - 100 = 800
        assert result.target_buy == 800.0
        assert result.quantity == 500
        assert result.capital == 400_000.0


# ============================================================
# TrendJudge テスト
# ============================================================


class TestTrendJudge:
    """トレンド判定のテスト"""

    def test_range_status(self):
        """5日MAと25日MAの乖離が3%以内 → Range"""
        tj = TrendJudge()
        # 乖離 = |1020 - 1000| / 1000 = 2.0%
        df = _make_df(sma_5=1020, sma_25=1000, sma_75=980)
        assert tj.judge(df) == STATUS_RANGE

    def test_up_status(self):
        """パーフェクトオーダー → Up"""
        tj = TrendJudge()
        # SMA_5=1100 > SMA_25=1000 > SMA_75=900、乖離=10% > 3%
        df = _make_df(sma_5=1100, sma_25=1000, sma_75=900)
        assert tj.judge(df) == STATUS_UP

    def test_down_status(self):
        """逆パーフェクトオーダー → Down"""
        tj = TrendJudge()
        # SMA_5=900 < SMA_25=1000 < SMA_75=1100、乖離=10% > 3%
        df = _make_df(sma_5=900, sma_25=1000, sma_75=1100)
        assert tj.judge(df) == STATUS_DOWN

    def test_sideways_status(self):
        """いずれにも該当しない → Sideways"""
        tj = TrendJudge()
        # SMA_5=900 < SMA_25=1000 > SMA_75=950（パーフェクトオーダーでない）
        # 乖離 = |900-1000|/1000 = 10% > 3%（Rangeでもない）
        df = _make_df(sma_5=900, sma_25=1000, sma_75=950)
        assert tj.judge(df) == STATUS_SIDEWAYS

    def test_range_boundary_exactly_3pct(self):
        """境界値: 乖離ちょうど3.0% → Range"""
        tj = TrendJudge()
        # 乖離 = |1030 - 1000| / 1000 = 3.0%
        df = _make_df(sma_5=1030, sma_25=1000, sma_75=980)
        assert tj.judge(df) == STATUS_RANGE

    def test_range_priority_over_up(self):
        """Range判定はUp/Downより優先される"""
        tj = TrendJudge()
        # パーフェクトオーダーだが乖離2%→Rangeが優先
        df = _make_df(sma_5=1020, sma_25=1000, sma_75=980)
        assert tj.judge(df) == STATUS_RANGE

    def test_missing_sma_returns_sideways(self):
        """SMAが欠損している場合はSideways"""
        tj = TrendJudge()
        df = _make_df(sma_5=float('nan'), sma_25=1000, sma_75=980)
        assert tj.judge(df) == STATUS_SIDEWAYS

    def test_empty_dataframe_returns_sideways(self):
        """空のDataFrame → Sideways"""
        tj = TrendJudge()
        assert tj.judge(pd.DataFrame()) == STATUS_SIDEWAYS


# ============================================================
# ScreenerPipeline 統合テスト
# ============================================================


class TestScreenerPipeline:
    """三段階フィルタの統合テスト"""

    def test_full_pipeline_happy_path(self):
        """正常系: 全フィルタを通過する銘柄"""
        pipeline = ScreenerPipeline(risk_jpy=30_000)
        stocks = {
            "9984": _make_df(
                close=1000, sma_25=1000, sma_5=1010, sma_75=990,
                atr_10=30, atr_100=15,
                volume_ma_5=600_000, volume_ma_10=550_000, volume_ma_100=500_000,
            ),
        }
        names = {"9984": "テスト銘柄"}

        results = pipeline.run(stocks, names)
        assert len(results) == 1
        assert results[0].ticker == "9984"
        assert results[0].name == "テスト銘柄"

    def test_no_stocks_pass_filters(self):
        """全銘柄がフィルタで除外される場合"""
        pipeline = ScreenerPipeline()
        stocks = {
            "1234": _make_df(volume_ma_5=100_000),  # 出来高不足
        }
        names = {"1234": "低出来高"}

        results = pipeline.run(stocks, names)
        assert results == []

    def test_to_json_dict(self):
        """JSON変換の動作確認"""
        pipeline = ScreenerPipeline(risk_jpy=30_000)
        stocks = {
            "9984": _make_df(
                close=1000, sma_25=1000, sma_5=1010, sma_75=990,
                atr_10=30, atr_100=15,
                volume_ma_5=600_000, volume_ma_10=550_000, volume_ma_100=500_000,
            ),
        }
        names = {"9984": "テスト銘柄"}

        results = pipeline.run(stocks, names)
        json_dict = pipeline.to_json_dict(results)

        assert 'generated_at' in json_dict
        assert 'parameters' in json_dict
        assert json_dict['parameters']['default_risk_jpy'] == 30_000
        assert len(json_dict['stocks']) == 1
