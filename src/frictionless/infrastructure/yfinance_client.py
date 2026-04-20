import yfinance as yf
import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class YFinanceClient:
    """株価やテクニカル情報を取得するインフラ層クライアント"""
    
    def fetch_ohlcv(self, stock_code: str, period: str = "1y") -> Optional[pd.DataFrame]:
        """
        指定された日本の銘柄コードの株価データを取得する。
        """
        # 日本株の場合は末尾に '.T' を付与
        ticker = f"{stock_code}.T" if not stock_code.endswith(".T") else stock_code
        
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if df is None or len(df) == 0:
                logger.warning(f"No price data found for {ticker}")
                return None
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data from yfinance for {ticker}: {e}")
            return None
