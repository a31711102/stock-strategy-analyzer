"""
適合度計算モジュール

銘柄と投資手法の適合度を計算
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import yaml

from tqdm import tqdm

from ..backtest.engine import BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


class CompatibilityAnalyzer:
    """適合度分析クラス"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Args:
            config_path: 設定ファイルのパス
        """
        self.config_path = config_path
        self.backtest_engine = BacktestEngine(config_path)
        
        # 設定ファイル読み込み
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 並列処理設定
        backtest_config = config.get('backtest', {})
        self.enable_parallel = backtest_config.get('enable_parallel', True)
        self.max_workers = backtest_config.get('max_workers', 4)
        
        # 適合度計算の重み
        self.weights = {
            'total_return': 0.4,
            'sharpe_ratio': 0.3,
            'win_rate': 0.2,
            'max_drawdown': 0.1
        }
    
    def calculate_compatibility(
        self,
        stock_code: str,
        df: pd.DataFrame,
        strategies: List
    ) -> Dict[str, Dict]:
        """
        銘柄と複数手法の適合度を計算
        
        Args:
            stock_code: 銘柄コード
            df: テクニカル指標を含むOHLCVデータ
            strategies: 投資手法のリスト
        
        Returns:
            手法名をキーとした適合度情報の辞書
        """
        # ========================================================================
        # [警告] 逐次処理は2007年からの全期間データでタイムアウトするため無効化
        # 逐次処理を有効にする場合は、以下のコメントアウトを解除し、
        # 常に並列処理のreturn文をコメントアウトしてください。
        # ========================================================================
        # if self.enable_parallel and len(strategies) > 1:
        #     return self._calculate_compatibility_parallel(stock_code, df, strategies)
        # else:
        #     return self._calculate_compatibility_sequential(stock_code, df, strategies)
        
        # 常に並列処理を使用（タイムアウト防止のため）
        return self._calculate_compatibility_parallel(stock_code, df, strategies)
    
    def _run_single_backtest(self, stock_code: str, df: pd.DataFrame, strategy):
        """
        単一手法のバックテストを実行（並列処理用）
        """
        # 各スレッドで独立したBacktestEngineを使用
        engine = BacktestEngine(self.config_path)
        backtest_result = engine.run_backtest(df, strategy, stock_code)
        score = self._calculate_score(backtest_result)
        reason = self._generate_reason(backtest_result, score)
        
        return strategy.name(), {
            'score': score,
            'reason': reason,
            'backtest_result': backtest_result
        }
    
    def _calculate_compatibility_parallel(
        self,
        stock_code: str,
        df: pd.DataFrame,
        strategies: List
    ) -> Dict[str, Dict]:
        """
        並列処理で適合度を計算
        """
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 全手法を並列で実行
            futures = {
                executor.submit(self._run_single_backtest, stock_code, df, strategy): strategy
                for strategy in strategies
            }
            
            # プログレスバー付きで結果を収集
            for future in tqdm(as_completed(futures), total=len(strategies), 
                               desc="バックテスト実行中（並列）", unit="手法"):
                strategy_name, result = future.result()
                results[strategy_name] = result
                logger.info(f"{stock_code} - {strategy_name}: {result['score']:.1f}%")
        
        return results
    
    def _calculate_compatibility_sequential(
        self,
        stock_code: str,
        df: pd.DataFrame,
        strategies: List
    ) -> Dict[str, Dict]:
        """
        逐次処理で適合度を計算（フォールバック用）
        
        [警告] 2007年からの全期間データを使用する場合、この処理は
        タイムアウトする可能性が非常に高いです。
        通常は _calculate_compatibility_parallel を使用してください。
        """
        results = {}
        
        for strategy in tqdm(strategies, desc="バックテスト実行中", unit="手法"):
            # バックテスト実行
            backtest_result = self.backtest_engine.run_backtest(
                df, strategy, stock_code
            )
            
            # 適合度スコア計算
            score = self._calculate_score(backtest_result)
            
            # 適合理由生成
            reason = self._generate_reason(backtest_result, score)
            
            results[strategy.name()] = {
                'score': score,
                'reason': reason,
                'backtest_result': backtest_result
            }
            
            logger.info(f"{stock_code} - {strategy.name()}: {score:.1f}%")
        
        return results
    
    def _calculate_score(self, result: BacktestResult) -> float:
        """
        適合度スコアを計算（0-100%）
        
        条件フロー:
        ① 取引回数 = 0 → 適合度 = 0%
        ② リターン < -10% → 適合度 ≤ 20%
        ③ 勝率 < 40% かつ リターン ≤ 0 → 適合度 ≤ 30%
        ④ 勝率 < 40% → 適合度 ≤ 50%
        ⑤ 取引回数 < 5 → 適合度 ≤ 70%
        ⑥ すべてクリア → 最大100%
        
        Args:
            result: バックテスト結果
        
        Returns:
            適合度スコア
        """
        # ① 取引回数 = 0 → 適合度 = 0%
        if result.num_trades == 0:
            return 0.0
        
        # ② リターン < -10% → 適合度 ≤ 20%
        if result.total_return < -10:
            # -10%で20点、-30%で0点
            return max(0.0, min(20.0, 20 + result.total_return))
        
        # ③ 勝率 < 40% かつ リターン ≤ 0 → 適合度 ≤ 30%
        if result.win_rate < 40 and result.total_return <= 0:
            # 勝率0%で15点、勝率40%で30点 + リターン補正
            base = 15 + result.win_rate * 0.375
            return min(30.0, base + result.total_return * 0.5)
        
        # ④ 勝率 < 40% → 適合度 ≤ 50%
        if result.win_rate < 40:
            # 正のリターンがあるが勝率低い
            base = 30 + min(20.0, result.total_return * 0.5)
            return min(50.0, base)
        
        # ⑤ 取引回数 < 5 → 適合度 ≤ 70%
        if result.num_trades < 5:
            base = self._calculate_base_score(result)
            return min(70.0, base)
        
        # ⑥ すべてクリア → 最大100%
        return self._calculate_base_score(result)
    
    def _calculate_base_score(self, result: BacktestResult) -> float:
        """
        基本スコアを計算（条件クリア後に呼ばれる）
        
        構成:
        - 取引機会スコア（0-30）
        - 勝率スコア（0-30）
        - リターンスコア（0-40）- 区間別重み係数適用
        """
        # 取引機会スコア（0-30）: 10回で30点
        trade_score = min(30, result.num_trades * 3)
        
        # 勝率スコア（0-30）: 100%で30点
        win_score = min(30, result.win_rate * 0.3)
        
        # リターンスコア（0-40）- 区間別重み係数を適用
        total_return = result.total_return
        if total_return >= 20:
            # +20%以上: ×1.5（30~40点）
            return_score = min(40, 30 + (total_return - 20) * 0.5)
        elif total_return >= 10:
            # +10%~+20%: ×1.2（20~30点）
            return_score = 20 + (total_return - 10) * 1.0
        elif total_return >= 0:
            # 0%~+10%: ×1.0（10~20点）
            return_score = 10 + total_return * 1.0
        elif total_return >= -10:
            # -10%~0%: ×0.5（0~10点）
            return_score = max(0, 10 + total_return * 1.0)
        else:
            # -10%未満: 0点
            return_score = 0
        
        return trade_score + win_score + return_score
    
    def _generate_reason(self, result: BacktestResult, score: float) -> str:
        """
        適合理由を生成
        
        Args:
            result: バックテスト結果
            score: 適合度スコア
        
        Returns:
            適合理由の文字列
        """
        reasons = []
        
        # 取引なしの場合
        if result.num_trades == 0:
            reasons.append("[NG] 取引機会がありません")
            return "\n".join(reasons)
        
        # スコアに応じた総評
        if score >= 80:
            reasons.append("[OK] 非常に高い適合度")
        elif score >= 60:
            reasons.append("[OK] 高い適合度")
        elif score >= 40:
            reasons.append("[中] 中程度の適合度")
        elif score >= 20:
            reasons.append("[NG] 低い適合度")
        else:
            reasons.append("[NG] 非常に低い適合度")
        
        # リターン評価（区間別）
        if result.total_return >= 20:
            reasons.append(f"[OK] 高リターン: {result.total_return:.1f}%")
        elif result.total_return >= 10:
            reasons.append(f"[OK] 中リターン: {result.total_return:.1f}%")
        elif result.total_return >= 0:
            reasons.append(f"[中] 小リターン: {result.total_return:.1f}%")
        elif result.total_return >= -10:
            reasons.append(f"[NG] 小損失: {result.total_return:.1f}%")
        else:
            reasons.append(f"[NG] 大損失: {result.total_return:.1f}%")
        
        # 勝率評価
        if result.win_rate >= 60:
            reasons.append(f"[OK] 高勝率: {result.win_rate:.1f}%")
        elif result.win_rate >= 40:
            reasons.append(f"[中] 中勝率: {result.win_rate:.1f}%")
        else:
            reasons.append(f"[NG] 低勝率: {result.win_rate:.1f}%")
        
        # 取引回数評価
        if result.num_trades >= 10:
            reasons.append(f"[OK] 十分な取引機会: {result.num_trades}回")
        elif result.num_trades >= 5:
            reasons.append(f"[中] 取引機会あり: {result.num_trades}回")
        else:
            reasons.append(f"[NG] 取引機会少: {result.num_trades}回")
        
        # 最大下落率（ドローダウン）
        if result.max_drawdown < 20:
            reasons.append(f"[OK] 下落リスク小: 最大{result.max_drawdown:.1f}%下落")
        elif result.max_drawdown < 40:
            reasons.append(f"[中] 下落リスク中: 最大{result.max_drawdown:.1f}%下落")
        else:
            reasons.append(f"[NG] 下落リスク大: 最大{result.max_drawdown:.1f}%下落")
        
        return "\n".join(reasons)
    
    def rank_stocks_by_strategy(
        self,
        stock_data: Dict[str, pd.DataFrame],
        strategy,
        threshold: float = 0.0
    ) -> List[Tuple[str, float, str]]:
        """
        手法に対する銘柄をランキング
        
        Args:
            stock_data: 銘柄コードをキーとしたデータフレームの辞書
            strategy: 投資手法
            threshold: 適合度の閾値（%）
        
        Returns:
            (銘柄コード, 適合度, 理由)のリスト（適合度降順）
        """
        results = []
        
        for stock_code, df in tqdm(stock_data.items(), desc="銘柄分析中", unit="銘柄"):
            compatibility = self.calculate_compatibility(
                stock_code, df, [strategy]
            )
            
            score = compatibility[strategy.name()]['score']
            reason = compatibility[strategy.name()]['reason']
            
            if score >= threshold:
                results.append((stock_code, score, reason))
        
        # 適合度降順でソート
        results.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"Ranked {len(results)} stocks for {strategy.name()} "
                   f"(threshold: {threshold}%)")
        
        return results
