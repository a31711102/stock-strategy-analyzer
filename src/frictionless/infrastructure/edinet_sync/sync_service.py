import datetime
import logging
from typing import Optional
from .repository import EdinetRepository
from src.frictionless.domain.models import FundamentalData

logger = logging.getLogger(__name__)

class EdinetSyncService:
    """
    「差分キャッチアップ・アルゴリズム」
    前回同期日から現在日までの未処理日数をループし、
    EDINET API経由で書類のダウンロード＆XBRLパース、SQLiteへのUpsertを処理する。
    """
    def __init__(self, repository: EdinetRepository, client=None, parser=None):
        self.repo = repository
        self.client = client
        self.parser = parser

    def sync_up_to_today(self, max_lookback_days: int = 30, is_initial_sync: bool = False):
        """
        最新日までの差分を埋める。
        is_initial_sync=True の場合はより深い遡りと長めの遅延（API制限回避）を採用する。
        """
        import time
        today = datetime.date.today()
        last_sync = self.repo.get_last_sync_date()
        
        if last_sync is None or is_initial_sync:
            # 初回起動時または強制初期化時は指定日数（例えば過去1年分など長めに）遡る
            lookback = 365 if is_initial_sync else max_lookback_days
            current_date = today - datetime.timedelta(days=lookback)
            logger.info(f"First time / Initial sync mode. Starting from {current_date}")
        else:
            current_date = last_sync + datetime.timedelta(days=1)
            logger.info(f"Resuming sync from {current_date}")

        # API制限を防ぐための遅延秒数。初回起動時の大量取得時は長めに待つ
        api_delay = 3.0 if is_initial_sync else 1.0

        # 今日までの日数をループ
        while current_date <= today:
            logger.info(f"Syncing EDINET data for: {current_date}")
            
            # APIClient等を通じて有価証券報告書の一覧を取得
            if self.client and self.parser:
                try:
                    document_list = self.client.get_document_list(current_date)
                    for doc in document_list:
                        # 有報・四半期などのフィルタリング後、ZIPを取得
                        raw_xbrl = self.client.download_document(doc['docID'])
                        if raw_xbrl:
                            fundamental_data = self.parser.parse(raw_xbrl)
                            if fundamental_data and doc['stock_code']:
                                self.repo.upsert_fundamental(doc['stock_code'], fundamental_data)
                except Exception as e:
                    logger.error(f"Error fetching/parsing on {current_date}: {e}")
                    # API制限や一時ネットワークエラーの場合は、ここで落とすかスキップするか。
                    # 以降の日付の更新がズレると困るため、深刻なエラーなら例外を投げる
                    raise e
                    
            # 完了したら DB の Last Sync Date をその日付で更新
            # これに成功すれば、次にバッチが落ちてもこの日から再開される
            self.repo.update_last_sync_date(current_date)
            
            # 次の日へ
            current_date += datetime.timedelta(days=1)
            
            # API制限回避のためのインターバル
            logger.debug(f"Sleeping for {api_delay} seconds to avoid API limit...")
            time.sleep(api_delay)
            
        logger.info(f"EDINET Full Sync completed. Up to date: {today}")
