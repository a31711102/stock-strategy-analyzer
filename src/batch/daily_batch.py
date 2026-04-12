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
from src.analysis.volatility import VolatilityAnalyzer
from src.batch.result_cache import ResultCache
from src.screener.pipeline import ScreenerPipeline

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
    
    def __init__(self, max_cpu_percent: int = 50, max_memory_mb: int = 2048):
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
        max_cpu_percent: int = 50,
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
        self.volatility_analyzer = VolatilityAnalyzer()
        self.result_cache = ResultCache()
        
        # ボラティリティ乖離スクリーナー
        self.screener_pipeline = ScreenerPipeline()
        
        # スクリーナー用: 指標計算済みDataFrameの一時保持
        self._stock_indicators: dict[str, pd.DataFrame] = {}
        self._stock_names: dict[str, str] = {}
        
        # ATR閾値（バッチ開始時に前回値を読み込み、なければ初回2パス処理）
        self.atr_thresholds = None
        
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
                return (code, None, None, None)
            
            # テクニカル指標計算
            df = self.indicator_calc.calculate_all_indicators(df)
            
            # スクリーナー用にDataFrameを保持（バッチ完了後に一括処理）
            self._stock_indicators[str(code)] = df
            self._stock_names[str(code)] = name
            
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
            
            # ATR情報を計算
            atr_info = self.volatility_analyzer.build_atr_info(
                df,
                thresholds_10=self.atr_thresholds.get('atr_pct_10') if self.atr_thresholds else None,
                thresholds_20=self.atr_thresholds.get('atr_pct_20') if self.atr_thresholds else None,
            )
            
            # 銘柄別詳細を保存
            self.result_cache.save_detail(code, result)
            
            # 接近シグナル情報を整形
            approaching_dict = None
            if approaching_signals:
                approaching_dict = {}
                for strategy_name, signal in approaching_signals.items():
                    signal_data = {
                        'code': signal.code,
                        'name': signal.name,
                        'estimated_days': signal.estimated_days,
                        'conditions_met': signal.conditions_met,
                        'conditions_pending': signal.conditions_pending,
                        'score': signal.score,
                        'current_price': signal.current_price,
                        'last_updated': signal.last_updated,
                        'avg_volume': signal.avg_volume,
                    }
                    # ATR情報を付加
                    signal_data.update(atr_info)
                    approaching_dict[strategy_name] = signal_data
            
            return (code, result, approaching_dict, atr_info)
            
        except Exception as e:
            self.logger.error(f"銘柄処理エラー ({code}): {e}")
            return (code, None, None, None)
    
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
        
        # ATR閾値の読み込み（前回値があれば使い回し、なければ初回2パス処理）
        self.atr_thresholds = self.result_cache.load_atr_thresholds()
        is_first_run = self.atr_thresholds is None
        if is_first_run:
            self.logger.info("ATR閾値なし: 初回2パス処理を実行します")
        else:
            self.logger.info("ATR閾値あり: 前回閾値を使用します")
        
        # 未処理銘柄を抽出
        all_codes = stock_df['コード'].astype(str).tolist()
        remaining_codes = [c for c in all_codes if c not in processed_codes]
        
        self.logger.info(f"処理対象: {len(remaining_codes)}銘柄")
        
        # 戦略別の結果を集計
        strategy_results: Dict[str, List[Dict]] = {s.name(): [] for s in self.strategies}
        # 接近シグナルの集計
        approaching_results: Dict[str, List[Dict]] = {}
        # ATR%の収集（閾値計算用）
        all_atr_pcts_10: List[float] = []
        all_atr_pcts_20: List[float] = []
        
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
                result_code, result_data, approaching_data, atr_info = code_result
                
                if result_data:
                    processed_codes.append(result_code)
                    
                    # ATR%を収集（閾値再計算用）
                    if atr_info:
                        if atr_info.get('atr_pct_10', 0) > 0:
                            all_atr_pcts_10.append(atr_info['atr_pct_10'])
                        if atr_info.get('atr_pct_20', 0) > 0:
                            all_atr_pcts_20.append(atr_info['atr_pct_20'])
                    
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
        
        # ATR閾値を再計算（最新データで更新し、次回用に保存）
        new_thresholds = self._recalculate_atr_thresholds(all_atr_pcts_10, all_atr_pcts_20)
        
        # 初回2パス処理: 閾値なしで処理した接近シグナルにカテゴリを付与し直す
        if is_first_run and new_thresholds:
            self.logger.info("初回2パス処理: 接近シグナルのATRカテゴリを再分類します")
            approaching_results = self._reclassify_approaching_signals(
                approaching_results, new_thresholds
            )
        
        # 戦略別ランキング保存
        for strategy_name, results in strategy_results.items():
            # スコア降順でソート
            sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
            self.result_cache.save_ranking(strategy_name, sorted_results)
        
        # 接近シグナル保存（出来高50万以上、スコア降順、Top50）
        MIN_AVG_VOLUME = 500_000
        for strategy_name, signals in approaching_results.items():
            filtered_signals = [s for s in signals if s.get('avg_volume', 0) >= MIN_AVG_VOLUME]
            sorted_signals = sorted(filtered_signals, key=lambda x: x['score'], reverse=True)[:50]
            self.result_cache.save_approaching_signals(strategy_name, sorted_signals)
        
        self.logger.info(f"接近シグナル保存完了: {len(approaching_results)}戦略")
        
        # ========== ボラティリティ乖離スクリーナー ==========
        self._run_volatility_screener()
        
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
    
    def _recalculate_atr_thresholds(
        self,
        all_atr_pcts_10: List[float],
        all_atr_pcts_20: List[float]
    ) -> Optional[Dict]:
        """
        全銘柄のATR%からパーセンタイル閾値を再計算し保存
        
        Args:
            all_atr_pcts_10: 全銘柄のATR%(10)リスト
            all_atr_pcts_20: 全銘柄のATR%(20)リスト
            
        Returns:
            計算された閾値辞書。データ不足の場合はNone。
        """
        if not all_atr_pcts_10 or not all_atr_pcts_20:
            self.logger.warning("ATR%データなし: 閾値再計算をスキップ")
            return None
        
        thresholds = {
            'atr_pct_10': VolatilityAnalyzer.calculate_thresholds(all_atr_pcts_10),
            'atr_pct_20': VolatilityAnalyzer.calculate_thresholds(all_atr_pcts_20),
            'calculated_at': datetime.now().isoformat(),
        }
        
        self.result_cache.save_atr_thresholds(thresholds)
        self.logger.info(
            f"ATR閾値再計算完了: "
            f"ATR%(10) p25={thresholds['atr_pct_10']['p25']:.3f}, p75={thresholds['atr_pct_10']['p75']:.3f} | "
            f"ATR%(20) p25={thresholds['atr_pct_20']['p25']:.3f}, p75={thresholds['atr_pct_20']['p75']:.3f}"
        )
        
        return thresholds
    
    def _reclassify_approaching_signals(
        self,
        approaching_results: Dict[str, List[Dict]],
        thresholds: Dict
    ) -> Dict[str, List[Dict]]:
        """
        初回2パス処理: 接近シグナルのATRカテゴリを閾値に基づいて再分類
        
        Args:
            approaching_results: 戦略名→接近シグナルリストの辞書
            thresholds: 再計算されたパーセンタイル閾値
            
        Returns:
            再分類後の接近シグナル辞書
        """
        th_10 = thresholds.get('atr_pct_10')
        th_20 = thresholds.get('atr_pct_20')
        
        for strategy_name, signals in approaching_results.items():
            for signal in signals:
                atr_pct_10 = signal.get('atr_pct_10', 0)
                atr_pct_20 = signal.get('atr_pct_20', 0)
                
                # カテゴリ再分類
                if th_10 and atr_pct_10 > 0:
                    cat_10 = VolatilityAnalyzer.classify_volatility(
                        atr_pct_10, th_10['p25'], th_10['p75']
                    )
                    signal['volatility_category_10'] = cat_10
                else:
                    cat_10 = signal.get('volatility_category_10', '')
                
                if th_20 and atr_pct_20 > 0:
                    cat_20 = VolatilityAnalyzer.classify_volatility(
                        atr_pct_20, th_20['p25'], th_20['p75']
                    )
                    signal['volatility_category_20'] = cat_20
                else:
                    cat_20 = signal.get('volatility_category_20', '')
                
                # パターン再判定
                signal['volatility_pattern'] = VolatilityAnalyzer.get_volatility_pattern(
                    cat_10, cat_20
                )
        
        return approaching_results

    def _run_volatility_screener(self):
        """
        ボラティリティ乖離スクリーナーを実行

        バッチ処理のメインループで収集した指標計算済みDataFrameを流用し、
        三段階フィルタリング → 結果保存を実行する。
        追加のデータ取得は行わない。
        """
        if not self._stock_indicators:
            self.logger.warning("スクリーナー: 指標データがありません（スキップ）")
            return

        self.logger.info(
            f"=== ボラティリティスクリーナー実行: "
            f"{len(self._stock_indicators)}銘柄のデータを使用 ==="
        )

        try:
            results = self.screener_pipeline.run(
                self._stock_indicators, self._stock_names
            )

            result_dict = self.screener_pipeline.to_json_dict(results)
            self.result_cache.save_screener_result(result_dict)

            total_found = len(results.get('dynamic', [])) + len(results.get('large_cap', []))
            if total_found > 0:
                self.logger.info(
                    f"スクリーナー完了: 計{total_found}銘柄を出力"
                )
            else:
                self.logger.info("スクリーナー完了: 該当銘柄なし")

        except Exception as e:
            self.logger.error(f"スクリーナー実行エラー: {e}", exc_info=True)

        finally:
            # メモリ解放
            self._stock_indicators.clear()
            self._stock_names.clear()



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
