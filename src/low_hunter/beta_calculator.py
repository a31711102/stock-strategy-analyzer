"""
Project-low-hunter: ベータ値（β）算出

責務:
- 日経平均と個別銘柄の日次収益率から β = Cov(r_i, r_m) / Var(r_m) を算出

やらないこと:
- データ取得（呼び出し元が DataFrame を渡す）
- フィルタ判定（universe.py が担当）
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class BetaCalculator:
    """市場ベータ値の算出"""

    @staticmethod
    def calculate(
        stock_df: pd.DataFrame,
        market_df: pd.DataFrame,
    ) -> float:
        """
        個別銘柄と日経平均のβ値を算出する。

        Args:
            stock_df: 個別銘柄のOHLCVデータ（DatetimeIndex）
            market_df: 日経平均のOHLCVデータ（DatetimeIndex）

        Returns:
            β値（float）。算出不可の場合は 0.0。
        """
        try:
            # 日次収益率を計算
            stock_returns = stock_df['Close'].pct_change().dropna()
            market_returns = market_df['Close'].pct_change().dropna()

            # 共通日でアラインメント（inner join）
            aligned = pd.DataFrame({
                'stock': stock_returns,
                'market': market_returns,
            }).dropna()

            if len(aligned) < 30:
                # 共通日が30日未満では統計的に不十分
                return 0.0

            stock_r = aligned['stock'].values
            market_r = aligned['market'].values

            # β = Cov(r_i, r_m) / Var(r_m)
            covariance = np.cov(stock_r, market_r, ddof=1)[0][1]
            market_variance = np.var(market_r, ddof=1)

            if market_variance == 0:
                return 0.0

            beta = covariance / market_variance
            return float(beta)

        except Exception as e:
            logger.debug(f"β値計算エラー: {e}")
            return 0.0
