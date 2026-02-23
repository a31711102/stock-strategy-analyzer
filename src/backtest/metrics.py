"""
パフォーマンス指標計算モジュール
"""
import pandas as pd
import numpy as np
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """パフォーマンス指標計算クラス"""
    
    @staticmethod
    def calculate_total_return(equity_curve: pd.Series) -> float:
        """
        総リターンを計算
        
        Args:
            equity_curve: 資産推移
        
        Returns:
            総リターン（%）
        """
        if len(equity_curve) == 0:
            return 0.0
        
        initial = equity_curve.iloc[0]
        final = equity_curve.iloc[-1]
        
        if initial == 0:
            return 0.0
        
        return ((final - initial) / initial) * 100
    
    @staticmethod
    def calculate_annual_return(equity_curve: pd.Series, days: int) -> float:
        """
        年率リターンを計算
        
        Args:
            equity_curve: 資産推移
            days: 取引日数
        
        Returns:
            年率リターン（%）
        """
        if days == 0:
            return 0.0
        
        total_return = PerformanceMetrics.calculate_total_return(equity_curve)
        years = days / 252  # 営業日ベース
        
        if years == 0:
            return 0.0
        
        return ((1 + total_return / 100) ** (1 / years) - 1) * 100
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: pd.Series) -> float:
        """
        最大ドローダウンを計算
        
        Args:
            equity_curve: 資産推移
        
        Returns:
            最大ドローダウン（%）
        """
        if len(equity_curve) == 0:
            return 0.0
        
        # 累積最大値
        cummax = equity_curve.cummax()
        
        # ドローダウン
        drawdown = (equity_curve - cummax) / cummax * 100
        
        return abs(drawdown.min())
    
    @staticmethod
    def calculate_sharpe_ratio(
        returns: pd.Series, 
        risk_free_rate: float = 0.0
    ) -> float:
        """
        シャープレシオを計算
        
        Args:
            returns: リターンのシリーズ
            risk_free_rate: リスクフリーレート（年率%）
        
        Returns:
            シャープレシオ
        """
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        
        # 日次リターンの平均と標準偏差
        mean_return = returns.mean()
        std_return = returns.std()
        
        # 年率換算
        annual_return = mean_return * 252
        annual_std = std_return * np.sqrt(252)
        
        if annual_std == 0:
            return 0.0
        
        return (annual_return - risk_free_rate) / annual_std
    
    @staticmethod
    def calculate_win_rate(trades: List[Dict]) -> float:
        """
        勝率を計算
        
        Args:
            trades: 取引履歴のリスト
        
        Returns:
            勝率（%）
        """
        if len(trades) == 0:
            return 0.0
        
        winning_trades = sum(1 for trade in trades if trade['profit'] > 0)
        return (winning_trades / len(trades)) * 100
    
    @staticmethod
    def calculate_profit_factor(trades: List[Dict]) -> float:
        """
        プロフィットファクターを計算
        
        Args:
            trades: 取引履歴のリスト
        
        Returns:
            プロフィットファクター
        """
        if len(trades) == 0:
            return 0.0
        
        gross_profit = sum(trade['profit'] for trade in trades if trade['profit'] > 0)
        gross_loss = abs(sum(trade['profit'] for trade in trades if trade['profit'] < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    @staticmethod
    def calculate_all_metrics(
        equity_curve: pd.Series,
        returns: pd.Series,
        trades: List[Dict],
        days: int
    ) -> Dict[str, float]:
        """
        全てのパフォーマンス指標を計算
        
        Args:
            equity_curve: 資産推移
            returns: リターンのシリーズ
            trades: 取引履歴
            days: 取引日数
        
        Returns:
            指標の辞書
        """
        metrics = {
            'total_return': PerformanceMetrics.calculate_total_return(equity_curve),
            'annual_return': PerformanceMetrics.calculate_annual_return(equity_curve, days),
            'max_drawdown': PerformanceMetrics.calculate_max_drawdown(equity_curve),
            'sharpe_ratio': PerformanceMetrics.calculate_sharpe_ratio(returns),
            'win_rate': PerformanceMetrics.calculate_win_rate(trades),
            'profit_factor': PerformanceMetrics.calculate_profit_factor(trades),
            'num_trades': len(trades)
        }
        
        logger.info(f"Calculated performance metrics: {metrics}")
        return metrics
