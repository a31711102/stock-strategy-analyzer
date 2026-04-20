import unittest
from src.frictionless.domain.models import TechnicalData
from src.frictionless.domain.technicals import calculate_lines

class TestTechnicals(unittest.TestCase):

    def test_new_high_breakout(self):
        # 新高値ブレイク
        data = TechnicalData(
            strategy_name="新高値ブレイク",
            is_entry=True
        )
        tp, sl = calculate_lines(data)
        self.assertEqual(tp, "株価 < 短期MA")
        self.assertEqual(sl, "株価 < 短期MA")

    def test_dip_buying(self):
        # 押し目買い
        data = TechnicalData(
            strategy_name="押し目買い",
            is_entry=True,
            entry_price=1000.0,
            atr_10=50.0
        )
        tp, sl = calculate_lines(data)
        self.assertEqual(tp, "1100.0") # 1000 + 50*2
        self.assertEqual(sl, "900.0")  # 1000 - 50*2

    def test_dip_buying_missing_data(self):
        # 押し目買いだが価格データなし
        data = TechnicalData(
            strategy_name="押し目買い",
            is_entry=True,
            entry_price=None,
            atr_10=50.0
        )
        tp, sl = calculate_lines(data)
        self.assertEqual(tp, "判定不能")
        self.assertEqual(sl, "判定不能")

    def test_legacy_strategy(self):
        # 既存手法流用（設定あり）
        data = TechnicalData(
            strategy_name="MACDクロス",
            is_entry=True,
            take_profit_text="条件到達",
            stop_loss_text="条件到達"
        )
        tp, sl = calculate_lines(data)
        self.assertEqual(tp, "条件到達")
        self.assertEqual(sl, "条件到達")

if __name__ == '__main__':
    unittest.main()
