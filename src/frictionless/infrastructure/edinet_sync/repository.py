import sqlite3
import datetime
from typing import Optional
from src.frictionless.domain.models import FundamentalData

class EdinetRepository:
    """
    ローカルSQLiteデータベースを用いて、全銘柄の最新のファンダメンタル指標と
    EDINETの最終同期日時をキャッシュ・永続化するRepository。
    """
    def __init__(self, db_path: str = "data/edinet_cache.db"):
        self.db_path = db_path
        self._conn = None
        self._init_db()

    def _get_connection(self):
        if self.db_path == ":memory:":
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path)
            return self._conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        if self.db_path != ":memory:":
            import os
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 銘柄ごとの最新ファンダメンタルデータ
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fundamentals (
                    stock_code TEXT PRIMARY KEY,
                    sales_yoy_pct REAL,
                    ordinary_profit_yoy_pct REAL,
                    operating_profit_yoy_pct REAL,
                    operating_profit_margin_pct REAL,
                    ordinary_profit_margin_pct REAL,
                    roic_pct REAL,
                    equity_ratio_pct REAL,
                    interest_bearing_debt_ratio_pct REAL,
                    last_updated TEXT
                )
            """)
            # 同期状態の管理テーブル（キーバリュー形式）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    def get_last_sync_date(self) -> Optional[datetime.date]:
        """前回どこまで同期したかを取得。未同期ならNoneを返す"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sync_state WHERE key = 'last_sync_date'")
            row = cursor.fetchone()
            if row and row[0]:
                return datetime.datetime.strptime(row[0], "%Y-%m-%d").date()
            return None

    def update_last_sync_date(self, sync_date: datetime.date):
        """同期完了日を更新（Upsert）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            date_str = sync_date.strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT INTO sync_state (key, value) VALUES ('last_sync_date', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (date_str,))
            conn.commit()

    def upsert_fundamental(self, stock_code: str, data: FundamentalData):
        """特定の銘柄のファンダメンタル指標を最新情報で上書き保存、または新規作成"""
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO fundamentals (
                    stock_code, sales_yoy_pct, ordinary_profit_yoy_pct,
                    operating_profit_yoy_pct, operating_profit_margin_pct,
                    ordinary_profit_margin_pct, roic_pct, equity_ratio_pct,
                    interest_bearing_debt_ratio_pct, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_code) DO UPDATE SET
                    sales_yoy_pct = excluded.sales_yoy_pct,
                    ordinary_profit_yoy_pct = excluded.ordinary_profit_yoy_pct,
                    operating_profit_yoy_pct = excluded.operating_profit_yoy_pct,
                    operating_profit_margin_pct = excluded.operating_profit_margin_pct,
                    ordinary_profit_margin_pct = excluded.ordinary_profit_margin_pct,
                    roic_pct = excluded.roic_pct,
                    equity_ratio_pct = excluded.equity_ratio_pct,
                    interest_bearing_debt_ratio_pct = excluded.interest_bearing_debt_ratio_pct,
                    last_updated = excluded.last_updated
            """, (
                stock_code,
                data.sales_yoy_pct, data.ordinary_profit_yoy_pct,
                data.operating_profit_yoy_pct, data.operating_profit_margin_pct,
                data.ordinary_profit_margin_pct, data.roic_pct, data.equity_ratio_pct,
                data.interest_bearing_debt_ratio_pct, now
            ))
            conn.commit()

    def get_fundamental(self, stock_code: str) -> Optional[FundamentalData]:
        """DBから銘柄の最新指標を取得"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM fundamentals WHERE stock_code = ?", (stock_code,))
            row = cursor.fetchone()
            if row:
                return FundamentalData(
                    sales_yoy_pct=row[1],
                    ordinary_profit_yoy_pct=row[2],
                    operating_profit_yoy_pct=row[3],
                    operating_profit_margin_pct=row[4],
                    ordinary_profit_margin_pct=row[5],
                    roic_pct=row[6],
                    equity_ratio_pct=row[7],
                    interest_bearing_debt_ratio_pct=row[8]
                )
            return None
