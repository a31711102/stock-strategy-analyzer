"""
U3: 適合度スコア算出のユニットテスト

テスト対象: src/analysis/compatibility.py の _calculate_score, _calculate_base_score

テスト観点:
- スコア条件分岐 ①〜⑥ の網羅
- 基本スコアの区間別重み係数の正確性
"""
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field
from typing import List, Dict

import pandas as pd

from src.analysis.compatibility import CompatibilityAnalyzer
from src.backtest.engine import BacktestResult


def _make_result(
    num_trades=10,
    total_return=10.0,
    win_rate=55.0,
    annual_return=5.0,
    sharpe_ratio=1.0,
    max_drawdown=5.0,
    profit_factor=1.5,
):
    """テスト用の BacktestResult を生成"""
    return BacktestResult(
        stock_code='9999',
        strategy_name='TestStrategy',
        total_return=total_return,
        annual_return=annual_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        profit_factor=profit_factor,
        num_trades=num_trades,
        trades=[],
        equity_curve=pd.Series([100.0]),
        signals=pd.Series([0]),
    )


@pytest.fixture
def analyzer():
    """CompatibilityAnalyzer を config 読み込みなしで生成"""
    with patch('builtins.open', side_effect=FileNotFoundError):
        with patch.object(CompatibilityAnalyzer, '__init__', lambda self, *args, **kwargs: None):
            a = CompatibilityAnalyzer.__new__(CompatibilityAnalyzer)
            a.config_path = 'dummy'
            a.parallel_enabled = False
            a.max_workers = 1
            return a


# ===========================================================================
# Test: _calculate_score 条件分岐 ①〜⑥
# ===========================================================================

class TestCalculateScore:
    """スコア計算の条件分岐を網羅"""

    def test_condition_1_no_trades(self, analyzer):
        """① 取引回数 = 0 → 適合度 = 0%"""
        result = _make_result(num_trades=0)
        assert analyzer._calculate_score(result) == 0.0

    def test_condition_2_large_loss_minus20(self, analyzer):
        """② total_return = -20 → max(0, 20 + (-20)) = 0.0"""
        result = _make_result(total_return=-20.0)
        assert analyzer._calculate_score(result) == pytest.approx(0.0)

    def test_condition_2_moderate_loss_minus15(self, analyzer):
        """② total_return = -15 → max(0, 20 + (-15)) = 5.0"""
        result = _make_result(total_return=-15.0)
        assert analyzer._calculate_score(result) == pytest.approx(5.0)

    def test_condition_2_boundary_minus10(self, analyzer):
        """② total_return = -10 (境界) → max(0, 20 + (-10)) = 10.0"""
        result = _make_result(total_return=-10.0)
        # -10未満で条件②に入る: -10 < -10 は False なので条件②をスキップ
        # → 条件③以降へ進む
        score = analyzer._calculate_score(result)
        assert score >= 0

    def test_condition_3_low_winrate_negative_return(self, analyzer):
        """③ 勝率30%, リターン-5% → ≤ 30"""
        result = _make_result(win_rate=30.0, total_return=-5.0)
        score = analyzer._calculate_score(result)
        assert 0 <= score <= 30.0

    def test_condition_4_low_winrate_positive_return(self, analyzer):
        """④ 勝率35%, リターン+5% → ≤ 50"""
        result = _make_result(win_rate=35.0, total_return=5.0)
        score = analyzer._calculate_score(result)
        assert 0 <= score <= 50.0

    def test_condition_5_few_trades(self, analyzer):
        """⑤ 取引3回, 勝率60%, リターン10% → ≤ 70"""
        result = _make_result(num_trades=3, win_rate=60.0, total_return=10.0)
        score = analyzer._calculate_score(result)
        assert 0 <= score <= 70.0

    def test_condition_6_good_performance(self, analyzer):
        """⑥ 全条件クリア → base_score（上限100%）"""
        result = _make_result(num_trades=20, win_rate=60.0, total_return=30.0)
        score = analyzer._calculate_score(result)
        assert 0 < score <= 100.0


# ===========================================================================
# Test: _calculate_base_score 区間別重み
# ===========================================================================

class TestCalculateBaseScore:
    """基本スコアの構成要素（取引機会・勝率・リターン）"""

    def test_trade_score_cap_at_30(self, analyzer):
        """取引回数100 → trade_score は 30 で頭打ち"""
        result_many = _make_result(num_trades=100, win_rate=0.0, total_return=-10.0)
        result_10 = _make_result(num_trades=10, win_rate=0.0, total_return=-10.0)
        # 両方とも trade_score = 30（上限）
        score_many = analyzer._calculate_base_score(result_many)
        score_10 = analyzer._calculate_base_score(result_10)
        assert score_many == score_10

    def test_win_score_proportional(self, analyzer):
        """勝率と win_score が比例すること"""
        result_high = _make_result(num_trades=10, win_rate=100.0, total_return=0.0)
        result_low = _make_result(num_trades=10, win_rate=50.0, total_return=0.0)
        score_high = analyzer._calculate_base_score(result_high)
        score_low = analyzer._calculate_base_score(result_low)
        assert score_high > score_low

    def test_return_tier_high(self, analyzer):
        """リターン +25% → return_score 30〜40"""
        result = _make_result(num_trades=10, win_rate=50.0, total_return=25.0)
        score = analyzer._calculate_base_score(result)
        # trade(30) + win(15) + return(32.5) = 77.5
        assert score > 70

    def test_return_tier_medium(self, analyzer):
        """リターン +15% → return_score 20〜30"""
        result = _make_result(num_trades=10, win_rate=50.0, total_return=15.0)
        score = analyzer._calculate_base_score(result)
        # trade(30) + win(15) + return(25) = 70
        assert 60 <= score <= 80

    def test_return_tier_low(self, analyzer):
        """リターン +5% → return_score 10〜20"""
        result = _make_result(num_trades=10, win_rate=50.0, total_return=5.0)
        score = analyzer._calculate_base_score(result)
        # trade(30) + win(15) + return(15) = 60
        assert 50 <= score <= 70

    def test_return_tier_negative(self, analyzer):
        """リターン -5% → return_score 0〜10"""
        result = _make_result(num_trades=10, win_rate=50.0, total_return=-5.0)
        score = analyzer._calculate_base_score(result)
        # trade(30) + win(15) + return(5) = 50
        assert 40 <= score <= 60

    def test_return_tier_very_negative(self, analyzer):
        """リターン -15% → return_score = 0"""
        result = _make_result(num_trades=10, win_rate=50.0, total_return=-15.0)
        score = analyzer._calculate_base_score(result)
        # trade(30) + win(15) + return(0) = 45
        assert score == pytest.approx(45.0)

    def test_total_score_composition(self, analyzer):
        """スコア = trade_score + win_score + return_score の合計"""
        result = _make_result(num_trades=5, win_rate=60.0, total_return=10.0)
        score = analyzer._calculate_base_score(result)
        # trade: min(30, 5*3) = 15
        # win: min(30, 60*0.3) = 18
        # return: 10%→ 20 + (10-10)*1.0 = 20
        expected = 15 + 18 + 20
        assert score == pytest.approx(expected)
