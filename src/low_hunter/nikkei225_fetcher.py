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

    WIKIPEDIA_URL = "https://ja.wikipedia.org/wiki/%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%E6%A0%AA%E4%BE%A1"

    def __init__(self, cache_dir: str = "./data"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.cache_dir / config.NIKKEI225_CACHE_FILENAME

    def fetch(self) -> List[Tuple[str, str]]:
        """
        日経225構成銘柄リストを取得する。
        プライマリ → セカンダリ → キャッシュ の3段階フォールバック。

        Returns:
            [(銘柄コード, 銘柄名), ...] のリスト。

        Raises:
            RuntimeError: 全ての取得手段が失敗した場合。
        """
        # 1. プライマリ: 日経平均プロフィル公式サイト
        stocks = self._fetch_from_nikkei_profile()
        if stocks:
            self._save_cache(stocks)
            logger.info(f"日経225銘柄リスト取得成功（公式サイト）: {len(stocks)}銘柄")
            return stocks

        # 2. セカンダリ: Wikipedia日本語版
        logger.warning("公式サイトからの取得に失敗。Wikipediaを試行します")
        stocks = self._fetch_from_wikipedia()
        if stocks:
            self._save_cache(stocks)
            logger.info(f"日経225銘柄リスト取得成功（Wikipedia）: {len(stocks)}銘柄")
            return stocks

        # 3. フォールバック: ローカルキャッシュ
        logger.warning("Web取得に全て失敗。ローカルキャッシュを使用します")
        stocks = self._load_cache()
        if stocks:
            logger.info(f"キャッシュから日経225銘柄リスト読み込み: {len(stocks)}銘柄")
            return stocks

        raise RuntimeError(
            "日経225銘柄リストを取得できません。"
            "ネットワーク接続を確認するか、"
            f"{self.cache_path} にCSVを手動配置してください。"
        )

    def _get_headers(self) -> dict:
        """User-Agent付きヘッダーを返す"""
        return {
            'User-Agent': (
                'StockStrategyAnalyzer/1.0 '
                '(https://github.com/a31711102/stock-strategy-analyzer)'
            )
        }

    def _fetch_from_nikkei_profile(self) -> List[Tuple[str, str]]:
        """日経平均プロフィル公式サイトからHTMLをパースして銘柄リストを取得"""
        try:
            response = requests.get(
                config.NIKKEI225_URL,
                headers=self._get_headers(),
                timeout=30,
            )
            response.raise_for_status()

            tables = pd.read_html(response.text)
            if not tables:
                return []

            for table_df in tables:
                stocks = self._parse_table(table_df)
                if stocks:
                    return stocks

            logger.warning("公式サイト: 構成銘柄テーブルの特定に失敗")
            return []

        except requests.RequestException as e:
            logger.warning(f"公式サイトHTTP取得エラー: {e}")
            return []
        except Exception as e:
            logger.warning(f"公式サイトパースエラー: {e}")
            return []

    def _fetch_from_wikipedia(self) -> List[Tuple[str, str]]:
        """Wikipedia日本語版から日経225構成銘柄リストを取得"""
        try:
            response = requests.get(
                self.WIKIPEDIA_URL,
                headers=self._get_headers(),
                timeout=30,
            )
            response.raise_for_status()

            tables = pd.read_html(response.text)
            if not tables:
                return []

            # Wikipediaの日経平均株価ページには複数テーブルがある。
            # 構成銘柄テーブルを探す（コード列と銘柄名列を持つテーブル）
            for table_df in tables:
                stocks = self._parse_table(table_df)
                if stocks:
                    return stocks

            logger.warning("Wikipedia: 構成銘柄テーブルの特定に失敗")
            return []

        except requests.RequestException as e:
            logger.warning(f"Wikipedia HTTP取得エラー: {e}")
            return []
        except Exception as e:
            logger.warning(f"Wikipedia パースエラー: {e}")
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
