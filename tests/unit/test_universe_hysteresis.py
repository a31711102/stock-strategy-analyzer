"""
ユニバース選定ヒステリシスのユニットテスト

テスト対象: src/low_hunter/universe.py - UniverseFilter

テスト方針:
- ヒステリシスによる閾値分岐が正しく動作するか
- 前回ユニバース=Noneの場合に全銘柄に厳格閾値が適用されるか
- ログ出力に新規/継続の内訳が含まれるか
- β値はヒステリシス対象外であることの確認
"""
import logging
from unittest.mock import patch

import pandas as pd
import numpy as np
import pytest

from src.low_hunter.universe import UniverseFilter


# === テストヘルパー ===

def _make_stock_df(
    close: float,
    volume_ma_5: float,
    atr_10: float,
    n_rows: int = 120,
) -> pd.DataFrame:
    """
    UniverseFilter が参照するカラムを含むテスト用 DataFrame を生成する。

    最終行に指定値を設定し、それ以外の行はダミーで埋める。
    β値計算用に Close 列は全行を設定する。
    """
    dates = pd.bdate_range(end="2026-05-12", periods=n_rows)
    df = pd.DataFrame(index=dates)
    df["Close"] = close
    df["High"] = close * 1.01
    df["Low"] = close * 0.99
    df["Open"] = close
    df["Volume"] = 2_000_000
    df["Volume_MA_5"] = volume_ma_5
    df["ATR_10"] = atr_10
    return df


def _make_market_df(n_rows: int = 120) -> pd.DataFrame:
    """β値計算用の市場（日経平均）ダミーデータ"""
    dates = pd.bdate_range(end="2026-05-12", periods=n_rows)
    np.random.seed(42)
    base_price = 38000.0
    returns = np.random.normal(0, 0.01, n_rows)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame(index=dates)
    df["Close"] = prices
    df["High"] = prices * 1.005
    df["Low"] = prices * 0.995
    df["Open"] = prices
    df["Volume"] = 1_000_000_000
    return df


# === テストケース ===

class TestUniverseFilterHysteresis:
    """ユニバース選定ヒステリシスのテスト"""

    def setup_method(self):
        """各テスト前のセットアップ"""
        self.universe_filter = UniverseFilter(
            min_avg_volume=1_000_000,
            min_norm_atr=2.0,
            min_beta=1.2,
            hysteresis_min_avg_volume=800_000,
            hysteresis_min_norm_atr=1.8,
        )
        self.market_df = _make_market_df()

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_new_stock_passes_strict_threshold(self, mock_beta):
        """新規銘柄: 厳格閾値（出来高100万・ATR2.0%）を通過"""
        # Close=1000, ATR_10=20 → Norm_ATR=2.0%
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=1_000_000, atr_10=20)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes=None,
        )

        assert len(result) == 1
        assert result[0].code == "1234"

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_new_stock_rejected_below_strict_volume(self, mock_beta):
        """新規銘柄: 出来高90万で厳格閾値未達 → 除外"""
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=900_000, atr_10=20)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes=None,
        )

        assert len(result) == 0

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_new_stock_rejected_below_strict_atr(self, mock_beta):
        """新規銘柄: Norm_ATR 1.9%で厳格閾値未達 → 除外"""
        # Close=1000, ATR_10=19 → Norm_ATR=1.9%
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=1_200_000, atr_10=19)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes=None,
        )

        assert len(result) == 0

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_continuation_stock_passes_with_relaxed_volume(self, mock_beta):
        """継続銘柄: 出来高85万で厳格閾値未達だが緩和閾値（80万）を通過"""
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=850_000, atr_10=20)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes={"1234"},
        )

        assert len(result) == 1
        assert result[0].code == "1234"

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_continuation_stock_passes_with_relaxed_atr(self, mock_beta):
        """継続銘柄: Norm_ATR 1.9%で厳格閾値未達だが緩和閾値（1.8%）を通過"""
        # Close=1000, ATR_10=19 → Norm_ATR=1.9%
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=1_200_000, atr_10=19)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes={"1234"},
        )

        assert len(result) == 1

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_continuation_stock_rejected_below_relaxed_threshold(self, mock_beta):
        """継続銘柄: 緩和閾値も割れた場合は除外"""
        # Close=1000, ATR_10=15 → Norm_ATR=1.5% (< 1.8%)
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=700_000, atr_10=15)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes={"1234"},
        )

        assert len(result) == 0

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_none_previous_universe_uses_strict_thresholds(self, mock_beta):
        """previous_universe_codes=None: 全銘柄に厳格閾値を適用（初回実行）"""
        # 出来高90万: 厳格閾値(100万)未達、緩和閾値(80万)通過
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=900_000, atr_10=20)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes=None,  # 初回
        )

        # 厳格閾値適用 → 除外
        assert len(result) == 0

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_empty_previous_universe_uses_strict_thresholds(self, mock_beta):
        """previous_universe_codes=空Set: 全銘柄に厳格閾値を適用"""
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=900_000, atr_10=20)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes=set(),  # 空
        )

        assert len(result) == 0

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.0)
    def test_beta_not_affected_by_hysteresis(self, mock_beta):
        """β値はヒステリシス対象外: 継続銘柄でもβ<1.2なら除外"""
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=1_200_000, atr_10=25)}
        stock_list = [("1234", "テスト銘柄A")]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes={"1234"},  # 継続
        )

        # β=1.0 < 1.2 → ヒステリシスに関係なく除外
        assert len(result) == 0

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_mixed_new_and_continuation_stocks(self, mock_beta):
        """新規と継続が混在する場合、それぞれに適切な閾値を適用"""
        stock_data = {
            # 新規: 出来高100万、Norm_ATR 2.0% → 通過
            "1111": _make_stock_df(close=1000, volume_ma_5=1_000_000, atr_10=20),
            # 継続: 出来高85万（厳格未達、緩和通過）、Norm_ATR 2.5% → 通過
            "2222": _make_stock_df(close=1000, volume_ma_5=850_000, atr_10=25),
            # 新規: 出来高90万（厳格未達）→ 除外
            "3333": _make_stock_df(close=1000, volume_ma_5=900_000, atr_10=20),
        }
        stock_list = [
            ("1111", "新規通過"),
            ("2222", "継続通過"),
            ("3333", "新規除外"),
        ]

        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
            previous_universe_codes={"2222", "9999"},  # 2222は継続、9999は存在しない
        )

        codes = [s.code for s in result]
        assert "1111" in codes  # 新規: 厳格閾値通過
        assert "2222" in codes  # 継続: 緩和閾値通過
        assert "3333" not in codes  # 新規: 厳格閾値未達
        assert len(result) == 2

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_log_output_with_hysteresis(self, mock_beta, caplog):
        """ログに新規/継続の内訳が出力されること"""
        stock_data = {
            "1111": _make_stock_df(close=1000, volume_ma_5=1_200_000, atr_10=25),
            "2222": _make_stock_df(close=1000, volume_ma_5=850_000, atr_10=25),
        }
        stock_list = [("1111", "新規"), ("2222", "継続")]

        with caplog.at_level(logging.INFO):
            self.universe_filter.apply(
                stock_list, stock_data, self.market_df,
                previous_universe_codes={"2222"},
            )

        log_text = caplog.text
        assert "新規: 1" in log_text
        assert "継続: 1" in log_text

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_log_output_without_hysteresis(self, mock_beta, caplog):
        """初回実行時のログに「ヒステリシスなし」が出力されること"""
        stock_data = {
            "1111": _make_stock_df(close=1000, volume_ma_5=1_200_000, atr_10=25),
        }
        stock_list = [("1111", "新規")]

        with caplog.at_level(logging.INFO):
            self.universe_filter.apply(
                stock_list, stock_data, self.market_df,
                previous_universe_codes=None,
            )

        assert "ヒステリシスなし（初回実行）" in caplog.text

    @patch("src.low_hunter.universe.BetaCalculator.calculate", return_value=1.5)
    def test_backward_compatibility_no_previous_universe_arg(self, mock_beta):
        """previous_universe_codes 引数なしでも動作する（後方互換性）"""
        stock_data = {"1234": _make_stock_df(close=1000, volume_ma_5=1_200_000, atr_10=25)}
        stock_list = [("1234", "テスト銘柄A")]

        # 引数を省略 → デフォルト None → 厳格閾値
        result = self.universe_filter.apply(
            stock_list, stock_data, self.market_df,
        )

        assert len(result) == 1
