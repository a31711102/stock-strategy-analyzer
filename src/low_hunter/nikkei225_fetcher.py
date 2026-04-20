"""
Project-low-hunter: 日経225構成銘柄の取得

責務:
- プロジェクトルート直下の手動配置CSV（日経平均225構成銘柄.csv）からの読み込み
- 読み込み成功時にキャッシュCSV（data/nikkei225_cache.csv）を更新
- 手動CSV不在時はキャッシュへフォールバック

やらないこと:
- 株価データの取得（StockDataFetcher が担当）

更新履歴:
- 2026-04-18: CSVは手動更新方針に変更。Web取得はデフォルト無効。
"""
import logging
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from src.low_hunter import config

logger = logging.getLogger(__name__)


class Nikkei225Fetcher:
    """日経225構成銘柄リストの取得"""

    # 手動CSVで想定するカラム名のバリエーション
    _CODE_COLUMN_CANDIDATES = ("銘柄コード", "コード", "code", "Code")
    _NAME_COLUMN_CANDIDATES = ("銘柄名", "銘柄", "name", "Name", "社名")

    def __init__(
        self,
        project_root: str = ".",
        cache_dir: str = "./data",
    ):
        self.project_root = Path(project_root)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.cache_dir / config.NIKKEI225_CACHE_FILENAME

    def fetch(self) -> List[Tuple[str, str]]:
        """
        日経225構成銘柄リストを取得する。
        手動CSV → キャッシュ の2段階フォールバック。

        Returns:
            [(銘柄コード, 銘柄名), ...] のリスト。

        Raises:
            RuntimeError: 全ての取得手段が失敗した場合。
        """
        manual_csv_path = self.project_root / config.NIKKEI225_MANUAL_CSV_FILENAME

        # 1. プライマリ: 手動配置CSV
        stocks = self._load_manual_csv(manual_csv_path)
        if stocks:
            self._save_cache(stocks)
            logger.info(
                f"日経225銘柄リスト取得成功（手動CSV）: {len(stocks)}銘柄"
            )
            return stocks

        # 2. フォールバック: キャッシュCSV
        logger.warning("手動CSVの読み込みに失敗。キャッシュを使用します")
        stocks = self._load_cache()
        if stocks:
            logger.info(
                f"キャッシュから日経225銘柄リスト読み込み: {len(stocks)}銘柄"
            )
            return stocks

        raise RuntimeError(
            "日経225銘柄リストを取得できません。"
            f"{manual_csv_path} にCSVを配置してください。"
        )

    def _load_manual_csv(self, csv_path: Path) -> List[Tuple[str, str]]:
        """
        手動配置CSVから銘柄リストを読み込む。

        エンコーディングは config.NIKKEI225_CSV_ENCODINGS の順で試行する。
        カラム名は _CODE_COLUMN_CANDIDATES / _NAME_COLUMN_CANDIDATES で
        柔軟にマッチする。

        Args:
            csv_path: CSVファイルのパス

        Returns:
            [(銘柄コード, 銘柄名), ...] のリスト。失敗時は空リスト。
        """
        if not csv_path.exists():
            logger.info(f"手動CSV不在: {csv_path}")
            return []

        df = self._read_csv_with_encoding(csv_path)
        if df is None:
            return []

        code_col = self._find_column(df, self._CODE_COLUMN_CANDIDATES)
        name_col = self._find_column(df, self._NAME_COLUMN_CANDIDATES)

        if code_col is None or name_col is None:
            logger.warning(
                f"手動CSV: 必要なカラムが見つかりません。"
                f"検出カラム: {list(df.columns)}, "
                f"コード候補: {self._CODE_COLUMN_CANDIDATES}, "
                f"名前候補: {self._NAME_COLUMN_CANDIDATES}"
            )
            return []

        stocks: List[Tuple[str, str]] = []
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            name = str(row[name_col]).strip()

            if not code or code == "nan":
                continue

            # 数字+末尾アルファベット（例: 123A）にも対応
            if code[0].isdigit():
                # float -> int変換対策（例: 1332.0 -> 1332）
                if code.endswith(".0"):
                    code = code[:-2]
                stocks.append((code, name))

        if len(stocks) < 100:
            logger.warning(
                f"手動CSV: 銘柄数が不足（{len(stocks)}銘柄）。"
                f"ファイルが破損している可能性があります: {csv_path}"
            )
            return []

        return stocks

    @staticmethod
    def _read_csv_with_encoding(csv_path: Path):
        """
        複数エンコーディングを試行してCSVを読み込む。

        Args:
            csv_path: CSVファイルのパス

        Returns:
            DataFrame。全エンコーディングで失敗した場合は None。
        """
        for encoding in config.NIKKEI225_CSV_ENCODINGS:
            try:
                df = pd.read_csv(csv_path, encoding=encoding, dtype=str)
                if not df.empty:
                    logger.debug(f"CSV読み込み成功（{encoding}）: {csv_path}")
                    return df
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                logger.warning(f"CSV読み込みエラー（{encoding}）: {e}")
                continue

        logger.warning(
            f"CSV読み込み失敗: 全エンコーディング試行済み "
            f"{config.NIKKEI225_CSV_ENCODINGS}"
        )
        return None

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: tuple):
        """
        DataFrameのカラム名から候補リストにマッチする最初のカラムを返す。

        Args:
            df: 検索対象のDataFrame
            candidates: カラム名の候補タプル

        Returns:
            マッチしたカラム名。見つからない場合は None。
        """
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
        return None

    def _save_cache(self, stocks: List[Tuple[str, str]]) -> None:
        """銘柄リストをキャッシュCSVに保存（UTF-8 BOM付き）"""
        try:
            df = pd.DataFrame(stocks, columns=["code", "name"])
            df.to_csv(self.cache_path, index=False, encoding="utf-8-sig")
        except Exception as e:
            logger.warning(f"キャッシュ保存エラー: {e}")

    def _load_cache(self) -> List[Tuple[str, str]]:
        """キャッシュCSVから銘柄リストを読み込み"""
        if not self.cache_path.exists():
            return []
        try:
            df = pd.read_csv(self.cache_path, dtype=str)
            return [(row["code"], row["name"]) for _, row in df.iterrows()]
        except Exception as e:
            logger.warning(f"キャッシュ読み込みエラー: {e}")
            return []
