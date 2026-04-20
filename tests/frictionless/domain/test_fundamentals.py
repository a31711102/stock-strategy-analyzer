import unittest
from src.frictionless.domain.models import FundamentalData, TrendStatus
from src.frictionless.domain.fundamentals import evaluate_fundamentals

class TestFundamentals(unittest.TestCase):

    def test_evaluate_up_trend(self):
        # 🟩上昇: すべての閾値をクリアしている場合
        data = FundamentalData(
            sales_yoy_pct=5.0,           # >= 3
            ordinary_profit_yoy_pct=6.0, # >= 5
            operating_profit_yoy_pct=None, # ordinary優先
            operating_profit_margin_pct=11.0, # >= 10
            ordinary_profit_margin_pct=11.0,  # >= 10
            roic_pct=8.0,                # > 7
            equity_ratio_pct=50.0,       # >= 40
            interest_bearing_debt_ratio_pct=150.0 # <= 200
        )
        result = evaluate_fundamentals(data)
        self.assertEqual(result, TrendStatus.UP)

    def test_evaluate_flat_trend(self):
        # 🟨横ばい: 上昇には届かないが横ばいの閾値はクリアしている場合
        data = FundamentalData(
            sales_yoy_pct=0.0,           # >= -3 (上昇の3には届かない)
            ordinary_profit_yoy_pct=-2.0,# >= -5
            operating_profit_yoy_pct=None,
            operating_profit_margin_pct=5.0,  # 上昇条件(<10)未達
            ordinary_profit_margin_pct=5.0,
            roic_pct=6.0,                # >= 5
            equity_ratio_pct=45.0,       # >= 40
            interest_bearing_debt_ratio_pct=220.0 # <= 250
        )
        result = evaluate_fundamentals(data)
        self.assertEqual(result, TrendStatus.FLAT)

    def test_evaluate_down_trend(self):
        # 🟥低下: いずれの条件も満たさない場合
        data = FundamentalData(
            sales_yoy_pct=-5.0,          # < -3
            ordinary_profit_yoy_pct=-10.0,
            operating_profit_yoy_pct=None,
            operating_profit_margin_pct=1.0,
            ordinary_profit_margin_pct=1.0,
            roic_pct=2.0,
            equity_ratio_pct=30.0,
            interest_bearing_debt_ratio_pct=300.0
        )
        result = evaluate_fundamentals(data)
        self.assertEqual(result, TrendStatus.DOWN)

    def test_missing_data_fallback(self):
        # ⚠️判定不能: 必須データがNoneの場合
        data = FundamentalData(
            sales_yoy_pct=5.0,
            ordinary_profit_yoy_pct=6.0,
            operating_profit_yoy_pct=6.0,
            operating_profit_margin_pct=None, # 欠落
            ordinary_profit_margin_pct=11.0,
            roic_pct=8.0,
            equity_ratio_pct=50.0,
            interest_bearing_debt_ratio_pct=150.0
        )
        result = evaluate_fundamentals(data)
        self.assertEqual(result, TrendStatus.ERROR)

if __name__ == '__main__':
    unittest.main()
