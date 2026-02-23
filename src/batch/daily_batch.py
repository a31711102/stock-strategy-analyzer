"""
夜間バッチ処理モジュール

全銘柄のバックテストを実行し、結果をキャッシュに保存
低負荷設計（CPU 25%制限、プロセス優先度: 低）
"""
import os
import sys
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import psutil
from tqdm import tqdm

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.data.fetcher import StockDataFetcher
from src.data.cache import DataCache
from src.indicators.technical import TechnicalIndicators
from src.strategies import get_all_strategies
from src.analysis.compatibility import CompatibilityAnalyzer
from src.analysis.signal_detector import SignalDetector
from src.batch.result_cache import ResultCache

# ログ設定
def setup_logging(log_dir: str = "./logs"):
    """ログ設定"""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    log_file = Path(log_dir) / f"batch_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stderr)
        ]
    )
    return logging.getLogger(__name__)


class LowPriorityExecutor:
    """
    低負荷実行管理
    
    - プロセス優先度を「低」に設定
    - CPU使用率が閾値を超えたらスリープ
    """
    
    def __init__(self, max_cpu_percent: int = 25, max_memory_mb: int = 1024):
        """
        Args:
            max_cpu_percent: 最大CPU使用率（%）
            max_memory_mb: 最大メモリ使用量（MB）
        """
        self.max_cpu = max_cpu_percent
        self.max_memory = max_memory_mb
        self._set_low_priority()
    
    def _set_low_priority(self):
        """プロセス優先度を低に設定"""
        try:
            p = psutil.Process()
            if sys.platform == 'win32':
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            else:
                p.nice(10)  # Unix系
            logging.getLogger(__name__).info("プロセス優先度を「低」に設定しました")
        except Exception as e:
            logging.getLogger(__name__).warning(f"優先度設定失敗: {e}")
    
    def throttle_if_needed(self, check_interval: float = 0.5):
        """
        CPU/メモリ使用率が高い場合はスリープ
        
        Args:
            check_interval: チェック間隔（秒）
        """
        while True:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            
            if cpu_percent < self.max_cpu and memory_mb < self.max_memory:
                break
            
            time.sleep(check_interval)


class DailyBatchProcessor:
    """
    日次バッチ処理
    
    1. 銘柄リスト読み込み（data_j.xls）
    2. 各銘柄の株価データ取得
    3. テクニカル指標計算
    4. 8戦略のバックテスト実行
    5. 結果をキャッシュに保存
    """
    
    def __init__(
        self,
        config_path: str = "config.yaml",
        max_cpu_percent: int = 25,
        chunk_size: int = 100
    ):
        """
        Args:
            config_path: 設定ファイルパス
            max_cpu_percent: 最大CPU使用率
            chunk_size: チャンクサイズ（銘柄数）
        """
        self.config_path = config_path
        self.chunk_size = chunk_size
        self.executor = LowPriorityExecutor(max_cpu_percent=max_cpu_percent)
        
        # コンポーネント初期化
        self.fetcher = StockDataFetcher()
        self.data_cache = DataCache()
        self.indicator_calc = TechnicalIndicators
        self.analyzer = CompatibilityAnalyzer(config_path)
        self.signal_detector = SignalDetector(lookback_days=60)
        self.result_cache = ResultCache()
        
        self.logger = logging.getLogger(__name__)
        
        # 設定読み込み
        self._load_config()
    
    def _load_config(self):
        """設定ファイル読み込み"""
        import yaml
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.stock_list_path = config.get('data', {}).get('stock_list_path', '')
            self.strategies = get_all_strategies()
            self.logger.info(f"設定読み込み完了: {len(self.strategies)}戦略")
        except Exception as e:
            self.logger.error(f"設定読み込みエラー: {e}")
            raise
    
    def load_stock_list(self) -> pd.DataFrame:
        """
        銘柄リストを読み込み（ETF/ETN除外）
        
        Returns:
            銘柄情報のDataFrame（コード、銘柄名、市場区分等）
        """
        self.logger.info(f"銘柄リスト読み込み: {self.stock_list_path}")
        
        df = pd.read_excel(self.stock_list_path)
        
        # カラム名を正規化
        df.columns = ['日付', 'コード', '銘柄名', '市場区分', 
                      '33業種コード', '33業種区分', 
                      '17業種コード', '17業種区分',
                      '規模コード', '規模区分']
        
        # ETF/ETNを除外
        initial_count = len(df)
        df = df[~df['市場区分'].str.contains('ETF|ETN', na=False)]
        
        # PRO Marketを除外（個人投資家向けでないため）
        df = df[~df['市場区分'].str.contains('PRO Market', na=False)]
        
        filtered_count = len(df)
        self.logger.info(f"銘柄数: {initial_count} -> {filtered_count} (除外: {initial_count - filtered_count})")
        
        return df
    
    def process_single_stock(
        self, 
        code: str, 
        name: str
    ) -> Tuple[str, Optional[Dict], Optional[Dict]]:
        """
        単一銘柄を処理
        
        Args:
            code: 銘柄コード
            name: 銘柄名
            
        Returns:
            (銘柄コード, 結果dict or None, 接近シグナルdict or None)
        """
        try:
            # 低負荷制御
            self.executor.throttle_if_needed()
            
            # 株価データ取得（キャッシュ優先）
            df = self.data_cache.get(code)
            if df is None:
                df = self.fetcher.fetch_stock_data(str(code))
                if df is not None:
                    self.data_cache.set(code, df)
            
            if df is None or len(df) < 200:
                return (code, None, None)
            
            # テクニカル指標計算
            df = self.indicator_calc.calculate_all_indicators(df)
            
            # 全戦略で適合度計算
            compatibility = self.analyzer.calculate_compatibility(
                stock_code=str(code),
                df=df,
                strategies=self.strategies
            )
            
            # 接近シグナル検出
            approaching_signals = self.signal_detector.detect_all_strategies(
                df=df,
                code=str(code),
                name=name
            )
            
            # 結果整形
            result = {
                'code': str(code),
                'name': name,
                'strategies': {}
            }
            
            for strategy_name, data in compatibility.items():
                result['strategies'][strategy_name] = {
                    'score': data.get('score', 0),
                    'win_rate': data.get('win_rate', 0),
                    'total_return': data.get('total_return', 0),
                    'annual_return': data.get('annual_return', 0),
                    'num_trades': data.get('num_trades', 0),
                    'max_drawdown': data.get('max_drawdown', 0),
                    'sharpe_ratio': data.get('sharpe_ratio', 0),
                    'profit_factor': data.get('profit_factor', 0),
                    'reason': data.get('reason', ''),
                    'valid_trades': data.get('valid_trades', 0),
                    'forced_trades': data.get('forced_trades', 0),
                    'excluded_trades': data.get('excluded_trades', 0)
                }
            
            # 銘柄別詳細を保存
            self.result_cache.save_detail(code, result)
            
            # 接近シグナル情報を整形
            approaching_dict = None
            if approaching_signals:
                approaching_dict = {}
                for strategy_name, signal in approaching_signals.items():
                    approaching_dict[strategy_name] = {
                        'code': signal.code,
                        'name': signal.name,
                        'estimated_days': signal.estimated_days,
                        'conditions_met': signal.conditions_met,
                        'conditions_pending': signal.conditions_pending,
                        'score': signal.score,
                        'current_price': signal.current_price,
                        'last_updated': signal.last_updated
                    }
            
            return (code, result, approaching_dict)
            
        except Exception as e:
            self.logger.error(f"銘柄処理エラー ({code}): {e}")
            return (code, None, None)
    
    def run(
        self, 
        resume: bool = False, 
        limit: Optional[int] = None,
        test_mode: bool = False
    ) -> Dict:
        """
        バッチ処理を実行
        
        Args:
            resume: 中断再開モード
            limit: 処理銘柄数上限（テスト用）
            test_mode: テストモード（進捗保存しない）
            
        Returns:
            処理結果の統計
        """
        start_time = time.time()
        
        # 銘柄リスト読み込み
        stock_df = self.load_stock_list()
        
        if limit:
            stock_df = stock_df.head(limit)
            self.logger.info(f"処理銘柄数を制限: {limit}")
        
        # 中断再開対応
        processed_codes = []
        failed_codes = []
        
        if resume:
            progress = self.result_cache.load_progress()
            if progress:
                processed_codes = progress.get('processed_codes', [])
                failed_codes = progress.get('failed_codes', [])
                self.logger.info(f"前回の進捗を読み込み: 処理済み {len(processed_codes)}, 失敗 {len(failed_codes)}")
        
        # 未処理銘柄を抽出
        all_codes = stock_df['コード'].astype(str).tolist()
        remaining_codes = [c for c in all_codes if c not in processed_codes]
        
        self.logger.info(f"処理対象: {len(remaining_codes)}銘柄")
        
        # 戦略別の結果を集計
        strategy_results: Dict[str, List[Dict]] = {s.name(): [] for s in self.strategies}
        # 接近シグナルの集計
        approaching_results: Dict[str, List[Dict]] = {}
        
        # tqdmの安全な設定（非ターミナル環境でのOSError回避）
        tqdm_kwargs = {
            'file': sys.stderr,
            'disable': not sys.stderr.isatty(),
        }
        
        # チャンク単位で処理
        for i in tqdm(range(0, len(remaining_codes), self.chunk_size), desc="チャンク", **tqdm_kwargs):
            chunk_codes = remaining_codes[i:i + self.chunk_size]
            
            for code in tqdm(chunk_codes, desc="銘柄", leave=False, **tqdm_kwargs):
                # 銘柄情報取得
                row = stock_df[stock_df['コード'].astype(str) == code]
                if row.empty:
                    continue
                
                name = row['銘柄名'].values[0]
                
                # 処理実行
                code_result = self.process_single_stock(code, name)
                result_code, result_data, approaching_data = code_result
                
                if result_data:
                    processed_codes.append(result_code)
                    
                    # 戦略別に集計
                    for strategy_name, strategy_data in result_data.get('strategies', {}).items():
                        strategy_results[strategy_name].append({
                            'code': result_code,
                            'name': name,
                            'score': strategy_data.get('score', 0),
                            'win_rate': strategy_data.get('win_rate', 0),
                            'return': strategy_data.get('total_return', 0),
                            'trades': strategy_data.get('num_trades', 0),
                            'reason': strategy_data.get('reason', '')
                        })
                    
                    # 接近シグナルを集計
                    if approaching_data:
                        for strategy_name, signal_data in approaching_data.items():
                            if strategy_name not in approaching_results:
                                approaching_results[strategy_name] = []
                            approaching_results[strategy_name].append(signal_data)
                else:
                    failed_codes.append(result_code)
            
            # チャンクごとに進捗保存
            if not test_mode:
                self.result_cache.save_progress(processed_codes, failed_codes)
        
        # 戦略別ランキング保存
        for strategy_name, results in strategy_results.items():
            # スコア降順でソート
            sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
            self.result_cache.save_ranking(strategy_name, sorted_results)
        
        # 接近シグナル保存（スコア降順、Top30）
        for strategy_name, signals in approaching_results.items():
            sorted_signals = sorted(signals, key=lambda x: x['score'], reverse=True)[:30]
            self.result_cache.save_approaching_signals(strategy_name, sorted_signals)
        
        self.logger.info(f"接近シグナル保存完了: {len(approaching_results)}戦略")
        
        # メタデータ更新
        elapsed_time = time.time() - start_time
        stats = {
            'total_stocks': len(all_codes),
            'processed_stocks': len(processed_codes),
            'failed_stocks': len(failed_codes),
            'strategies': [s.name() for s in self.strategies],
            'approaching_strategies': list(approaching_results.keys()),
            'processing_time_seconds': int(elapsed_time)
        }
        self.result_cache.update_metadata(stats)
        
        # 進捗ファイル削除（正常完了時）
        if not test_mode:
            self.result_cache.clear_progress()
        
        self.logger.info(f"バッチ処理完了: {len(processed_codes)}銘柄, {elapsed_time:.1f}秒")
        
        return stats


def main():
    """メインエントリーポイント"""
    parser = argparse.ArgumentParser(description='日次バッチ処理')
    parser.add_argument('--resume', action='store_true', help='中断再開モード')
    parser.add_argument('--limit', type=int, default=None, help='処理銘柄数上限')
    parser.add_argument('--test-mode', action='store_true', help='テストモード')
    parser.add_argument('--cpu-limit', type=int, default=25, help='最大CPU使用率(%)')
    parser.add_argument('--chunk-size', type=int, default=100, help='チャンクサイズ')
    
    args = parser.parse_args()
    
    # ログ設定
    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("日次バッチ処理を開始します")
    logger.info(f"設定: resume={args.resume}, limit={args.limit}, cpu_limit={args.cpu_limit}%")
    
    try:
        processor = DailyBatchProcessor(
            max_cpu_percent=args.cpu_limit,
            chunk_size=args.chunk_size
        )
        
        stats = processor.run(
            resume=args.resume,
            limit=args.limit,
            test_mode=args.test_mode
        )
        
        logger.info(f"処理結果: {stats}")
        logger.info("=" * 50)
        
    except KeyboardInterrupt:
        logger.warning("ユーザーにより中断されました")
        sys.exit(1)
    except Exception as e:
        logger.error(f"バッチ処理エラー: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
