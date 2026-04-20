import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from src.frictionless.infrastructure.legacy_strategy_adapter import LegacyStrategyAdapter
from src.strategies.base import BaseStrategy

class MockStrategyEntry(BaseStrategy):
    def name(self): return "順張り空売り"
    def strategy_type(self): return "short"
    def get_description(self): return ""
    def get_parameters(self): return {}
    def check_conditions(self, df, index): return {}
    def generate_signals(self, df):
        # 最新日が1(エントリー)
        return pd.Series([0, 0, 1], index=[0, 1, 2])

class MockStrategyNoEntry(BaseStrategy):
    def name(self): return "無視される手法"
    def strategy_type(self): return "long"
    def get_description(self): return ""
    def get_parameters(self): return {}
    def check_conditions(self, df, index): return {}
    def generate_signals(self, df):
        # 最新日が0
        return pd.Series([0, 1, 0], index=[0, 1, 2])

class TestLegacyStrategyAdapter(unittest.TestCase):

    @patch('src.frictionless.infrastructure.legacy_strategy_adapter.get_all_strategies')
    def test_evaluate_returns_entries(self, mock_get_all):
        mock_get_all.return_value = [MockStrategyEntry(), MockStrategyNoEntry()]
        
        adapter = LegacyStrategyAdapter()
        df = pd.DataFrame({"dummy": [1, 2, 3]})
        
        results = adapter.evaluate(df)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].strategy_name, "順張り空売り")
        self.assertTrue(results[0].is_entry)
        self.assertEqual(results[0].take_profit_text, "短期MA > 中期MA")
        self.assertEqual(results[0].stop_loss_text, "短期MA > 中期MA")

    def test_evaluate_empty_df(self):
        adapter = LegacyStrategyAdapter()
        results = adapter.evaluate(pd.DataFrame())
        self.assertEqual(len(results), 0)

if __name__ == '__main__':
    unittest.main()
