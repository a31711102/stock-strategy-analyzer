"""
データキャッシュモジュール

取得した株価データをローカルにキャッシュして再利用
"""
import pandas as pd
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DataCache:
    """データキャッシュ管理クラス"""
    
    def __init__(self, cache_dir: str = "./cache/stock_data", ttl_hours: int = 24):
        """
        Args:
            cache_dir: キャッシュディレクトリ
            ttl_hours: キャッシュの有効期限（時間）
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_hours = ttl_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, code: str) -> Optional[pd.DataFrame]:
        """
        キャッシュからデータを取得
        
        Args:
            code: 銘柄コード
        
        Returns:
            キャッシュされたデータ、存在しないか期限切れの場合はNone
        """
        cache_file = self._get_cache_path(code)
        
        if not cache_file.exists():
            logger.debug(f"Cache miss for {code}")
            return None
        
        # 有効期限チェック
        if not self._is_valid(cache_file):
            logger.debug(f"Cache expired for {code}")
            return None
        
        try:
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            logger.debug(f"Cache hit for {code}")
            return df
        except Exception as e:
            logger.error(f"Failed to read cache for {code}: {e}")
            return None
    
    def set(self, code: str, df: pd.DataFrame) -> bool:
        """
        データをキャッシュに保存
        
        Args:
            code: 銘柄コード
            df: 保存するデータフレーム
        
        Returns:
            保存成功時True
        """
        cache_file = self._get_cache_path(code)
        
        try:
            df.to_csv(cache_file)
            logger.debug(f"Cached data for {code}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache data for {code}: {e}")
            return False
    
    def clear(self, code: Optional[str] = None):
        """
        キャッシュをクリア
        
        Args:
            code: 銘柄コード（省略時は全キャッシュをクリア）
        """
        if code:
            cache_file = self._get_cache_path(code)
            if cache_file.exists():
                cache_file.unlink()
                logger.info(f"Cleared cache for {code}")
        else:
            for cache_file in self.cache_dir.glob("*.csv"):
                cache_file.unlink()
            logger.info("Cleared all cache")
    
    def _get_cache_path(self, code: str) -> Path:
        """キャッシュファイルのパスを取得"""
        # .JPを除去してファイル名に使用
        clean_code = code.replace(".JP", "").replace(".", "_")
        return self.cache_dir / f"{clean_code}.csv"
    
    def _is_valid(self, cache_file: Path) -> bool:
        """キャッシュの有効期限をチェック"""
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        age = datetime.now() - mtime
        return age < timedelta(hours=self.ttl_hours)
