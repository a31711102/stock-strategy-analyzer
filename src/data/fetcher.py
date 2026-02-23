"""
株価データ取得モジュール

Stooq（プライマリ）とyfinance（フォールバック）から日本株データを取得
レート制限対策として、Stooqへのリクエスト間隔を設定
"""
import pandas as pd
import pandas_datareader as pdr
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, List
import logging
import time

logger = logging.getLogger(__name__)

# Stooqレート制限対策
_last_stooq_request_time = 0
STOOQ_REQUEST_INTERVAL = 1.0  # 秒


class StockDataFetcher:
    """株価データ取得クラス"""
    
    def __init__(self, start_date: str = "2007-01-01", use_fallback: bool = True):
        """
        Args:
            start_date: データ取得開始日（YYYY-MM-DD形式）
            use_fallback: yfinanceフォールバックを使用するか
        """
        self.start_date = start_date
        self.use_fallback = use_fallback
    
    def fetch_stock_data(
        self, 
        code: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """
        株価データを取得
        
        Args:
            code: 銘柄コード（4桁数字 or 3桁数字+A）
            start_date: 開始日（省略時はインスタンス設定値）
            end_date: 終了日（省略時は本日）
        
        Returns:
            OHLCV データフレーム、取得失敗時はNone
        """
        start = start_date or self.start_date
        end = end_date or datetime.now().strftime("%Y-%m-%d")
        
        # 銘柄コードを正規化（.JP付与）
        ticker = self._normalize_code(code)
        
        logger.info(f"Fetching data for {ticker} from {start} to {end}")
        
        # yfinanceから取得を試行（プライマリデータソース、.T形式）
        df = self._fetch_from_yfinance(ticker, start, end)
        
        # 失敗した場合、Stooqにフォールバック（.JP形式）
        if df is None and self.use_fallback:
            logger.warning(f"yfinance failed for {ticker}, trying Stooq")
            stooq_ticker = self._convert_to_stooq_format(ticker)
            df = self._fetch_from_stooq(stooq_ticker, start, end)
        
        if df is not None:
            # カラム名を統一
            df = self._standardize_columns(df)
            logger.info(f"Successfully fetched {len(df)} rows for {ticker}")
        else:
            logger.error(f"Failed to fetch data for {ticker}")
        
        return df
    
    def _normalize_code(self, code: str) -> str:
        """
        銘柄コードを正規化（yfinance用: .T形式）
        
        Args:
            code: 銘柄コード（例: 9432, 123A）
        
        Returns:
            正規化された銘柄コード（例: 9432.T, 123A.T）
        """
        code = code.strip().upper()
        # yfinance用: 東証は.T形式
        if not code.endswith(".T") and not code.endswith(".JP"):
            code += ".T"
        return code
    
    def _convert_to_stooq_format(self, ticker: str) -> str:
        """
        yfinanceのティッカー形式(.T)をStooq形式(.JP)に変換
        
        Args:
            ticker: yfinance形式のティッカー（例: 9432.T）
        
        Returns:
            Stooq形式のティッカー（例: 9432.JP）
        """
        if ticker.endswith(".T"):
            return ticker[:-2] + ".JP"
        return ticker
    
    def _fetch_from_stooq(
        self, 
        ticker: str, 
        start: str, 
        end: str
    ) -> Optional[pd.DataFrame]:
        """Stooqからデータ取得（レート制限対策付き）"""
        global _last_stooq_request_time
        
        # リクエスト間隔を確保
        elapsed = time.time() - _last_stooq_request_time
        if elapsed < STOOQ_REQUEST_INTERVAL:
            time.sleep(STOOQ_REQUEST_INTERVAL - elapsed)
        
        try:
            _last_stooq_request_time = time.time()
            df = pdr.DataReader(ticker, 'stooq', start, end)
            
            # 空のDataFrameは日次制限の可能性
            if df is None or df.empty:
                logger.warning(f"Stooq returned empty data for {ticker} (possibly rate limited)")
                return None
            
            return df
        except Exception as e:
            error_msg = str(e)
            if "Exceeded" in error_msg or "limit" in error_msg.lower():
                logger.error(f"Stooq daily limit reached: {error_msg}")
            else:
                logger.debug(f"Stooq fetch error for {ticker}: {e}")
        return None
    
    def _fetch_from_yfinance(
        self, 
        ticker: str, 
        start: str, 
        end: str
    ) -> Optional[pd.DataFrame]:
        """yfinanceからデータ取得"""
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start, end=end)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.debug(f"yfinance fetch error for {ticker}: {e}")
        return None
    
    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        カラム名を統一（Open, High, Low, Close, Volume）
        """
        # yfinanceの場合、既に標準形式
        # Stooqの場合も同様だが、念のため確認
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        # カラム名のマッピング（必要に応じて）
        column_mapping = {
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        
        df = df.rename(columns=column_mapping)
        
        # 必要なカラムのみ抽出
        available_cols = [col for col in required_cols if col in df.columns]
        df = df[available_cols].copy()
        
        # 日付でソート（古い順）
        df = df.sort_index()
        
        return df
    
    def load_stock_list(self, file_path: str) -> List[str]:
        """
        銘柄リストをExcelファイルから読み込み
        
        Args:
            file_path: Excelファイルのパス
        
        Returns:
            銘柄コードのリスト
        """
        try:
            df = pd.read_excel(file_path)
            
            # 銘柄コードのカラムを探す（一般的な名前を試行）
            code_column = None
            for col in ['コード', 'code', 'Code', '銘柄コード', 'ticker']:
                if col in df.columns:
                    code_column = col
                    break
            
            if code_column is None:
                # 最初のカラムを使用
                code_column = df.columns[0]
                logger.warning(f"Code column not found, using first column: {code_column}")
            
            codes = df[code_column].astype(str).str.strip().tolist()
            logger.info(f"Loaded {len(codes)} stock codes from {file_path}")
            
            return codes
        
        except Exception as e:
            logger.error(f"Failed to load stock list from {file_path}: {e}")
            return []
