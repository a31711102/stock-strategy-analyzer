"""
Project-low-hunter: 日経225構成銘柄の自動取得

責務:
- 日経平均プロフィル公式サイトから構成銘柄リストを取得
- 取得成功時にローカルCSVキャッシュを更新
- 取得失敗時はローカルキャッシュへフォールバック

やらないこと:
- 株価データの取得（StockDataFetcher が担当）
"""
import logging
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import requests

from src.low_hunter import config

logger = logging.getLogger(__name__)


class Nikkei225Fetcher:
    """日経225構成銘柄リストの取得"""

    def __init__(self, cache_dir: str = "./data"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.cache_dir / config.NIKKEI225_CACHE_FILENAME

    def fetch(self) -> List[Tuple[str, str]]:
        """
        日経225構成銘柄リストを取得する。

        Returns:
            [(銘柄コード, 銘柄名), ...] のリスト。

        Raises:
            RuntimeError: プライマリ取得もキャッシュも利用不可の場合。
        """
        # 1. プライマリ: 公式サイトから取得
        stocks = self._fetch_from_web()
        if stocks:
            self._save_cache(stocks)
            logger.info(f"日経225銘柄リスト取得成功: {len(stocks)}銘柄（キャッシュ更新済み）")
            return stocks

        # 2. フォールバック: ローカルキャッシュ
        logger.warning("公式サイトからの取得に失敗。ローカルキャッシュを使用します")
        stocks = self._load_cache()
        if stocks:
            logger.info(f"キャッシュから日経225銘柄リスト読み込み: {len(stocks)}銘柄")
            return stocks

        raise RuntimeError(
            "日経225銘柄リストを取得できません。"
            "ネットワーク接続を確認するか、"
            f"{self.cache_path} にCSVを手動配置してください。"
        )

    def _fetch_from_web(self) -> List[Tuple[str, str]]:
        """公式サイトからHTMLをパースして銘柄リストを取得"""
        try:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            }
            response = requests.get(
                config.NIKKEI225_URL,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            tables = pd.read_html(response.text)
            if not tables:
                logger.warning("HTMLからテーブルが見つかりません")
                return []

            # テーブル構造に応じてパース
            # 日経平均プロフィルの構成銘柄テーブルを探す
            for table_df in tables:
                stocks = self._parse_table(table_df)
                if stocks:
                    return stocks

            logger.warning("構成銘柄テーブルの特定に失敗しました")
            return []

        except requests.RequestException as e:
            logger.warning(f"HTTP取得エラー: {e}")
            return []
        except Exception as e:
            logger.warning(f"パースエラー: {e}")
            return []

    def _parse_table(self, df: pd.DataFrame) -> List[Tuple[str, str]]:
        """
        DataFrameから銘柄コードと銘柄名を抽出する。
        テーブル構造が変わっても柔軟に対応できるよう、
        カラム名のパターンマッチングで特定する。
        """
        code_col = None
        name_col = None

        for col in df.columns:
            col_str = str(col).strip()
            if col_str in ('コード', 'Code', '銘柄コード', 'code'):
                code_col = col
            elif col_str in ('銘柄名', 'Name', '銘柄', 'name', '社名'):
                name_col = col

        if code_col is None or name_col is None:
            return []

        stocks = []
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            name = str(row[name_col]).strip()
            # コードが数字4桁 or 3桁+英字のパターン
            if code and name and len(code) >= 3:
                # .0 を除去（Excel由来の浮動小数点数対策）
                if code.endswith('.0'):
                    code = code[:-2]
                stocks.append((code, name))

        # 日経225は225銘柄のはず。150以上取れていれば成功とみなす
        if len(stocks) >= 150:
            return stocks

        return []

    def _save_cache(self, stocks: List[Tuple[str, str]]) -> None:
        """銘柄リストをCSVキャッシュに保存"""
        try:
            df = pd.DataFrame(stocks, columns=['code', 'name'])
            df.to_csv(self.cache_path, index=False, encoding='utf-8-sig')
        except Exception as e:
            logger.warning(f"キャッシュ保存エラー: {e}")

    def _load_cache(self) -> List[Tuple[str, str]]:
        """CSVキャッシュから銘柄リストを読み込み"""
        if not self.cache_path.exists():
            return []
        try:
            df = pd.read_csv(self.cache_path, dtype=str)
            return [(row['code'], row['name']) for _, row in df.iterrows()]
        except Exception as e:
            logger.warning(f"キャッシュ読み込みエラー: {e}")
            return []
