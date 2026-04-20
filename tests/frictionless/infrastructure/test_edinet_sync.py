import unittest
from unittest.mock import MagicMock
import datetime
import os
import sqlite3

from src.frictionless.infrastructure.edinet_sync.repository import EdinetRepository
from src.frictionless.infrastructure.edinet_sync.sync_service import EdinetSyncService
from src.frictionless.domain.models import FundamentalData

class TestEdinetSync(unittest.TestCase):
    def setUp(self):
        self.repo = EdinetRepository(db_path=":memory:")
        
    def test_repository_upsert_and_retrieve(self):
        data1 = FundamentalData(
            sales_yoy_pct=10.0,
            ordinary_profit_yoy_pct=20.0,
            operating_profit_yoy_pct=15.0,
            operating_profit_margin_pct=12.0,
            ordinary_profit_margin_pct=13.0,
            roic_pct=8.0,
            equity_ratio_pct=50.0,
            interest_bearing_debt_ratio_pct=100.0
        )
        self.repo.upsert_fundamental("7203", data1)
        
        saved = self.repo.get_fundamental("7203")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.sales_yoy_pct, 10.0)
        
        # データの更新 (Upsert)
        data2 = FundamentalData(
            sales_yoy_pct=5.0,
            ordinary_profit_yoy_pct=None,
            operating_profit_yoy_pct=0.0,
            operating_profit_margin_pct=10.0,
            ordinary_profit_margin_pct=10.0,
            roic_pct=5.0,
            equity_ratio_pct=30.0,
            interest_bearing_debt_ratio_pct=200.0
        )
        self.repo.upsert_fundamental("7203", data2)
        saved2 = self.repo.get_fundamental("7203")
        self.assertEqual(saved2.sales_yoy_pct, 5.0)

    def test_last_sync_date(self):
        self.assertIsNone(self.repo.get_last_sync_date())
        
        test_date = datetime.date(2025, 1, 1)
        self.repo.update_last_sync_date(test_date)
        
        self.assertEqual(self.repo.get_last_sync_date(), test_date)

    def test_sync_service_catch_up(self):
        """差分キャッチアップアルゴリズムの稼働テスト（冪等性）"""
        # 前回の同期が3日前だったとする
        today = datetime.date.today()
        last_sync = today - datetime.timedelta(days=3)
        self.repo.update_last_sync_date(last_sync)
        
        mock_client = MagicMock()
        # 1日に2件のドキュメントを返すと仮定
        mock_client.get_document_list.return_value = [
            {'docID': 'doc1', 'stock_code': '9999'}, 
            {'docID': 'doc2', 'stock_code': '8888'}
        ]
        mock_client.download_document.return_value = b"dummy_xbrl"
        
        mock_parser = MagicMock()
        mock_parser.parse.return_value = FundamentalData(1,1,1,1,1,1,1,1)

        service = EdinetSyncService(repository=self.repo, client=mock_client, parser=mock_parser)
        
        # 実行 (last_syncの翌日分から今日までの 3日分ループが回るはず)
        service.sync_up_to_today()
        
        # APIが3日分（今日-2, 今日-1, 今日）呼ばれたか
        self.assertEqual(mock_client.get_document_list.call_count, 3)
        # 3日 * 2件 = 6件分のダウンロードとパースが発生したか
        self.assertEqual(mock_client.download_document.call_count, 6)
        
        # 同期完了日が今日に更新されたか
        self.assertEqual(self.repo.get_last_sync_date(), today)

if __name__ == '__main__':
    unittest.main()
