"""
投資手法の基底クラス

全ての投資手法はこのクラスを継承して実装する
"""
from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """投資手法の基底クラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def name(self) -> str:
        """手法名を返す"""
        pass
    
    @abstractmethod
    def strategy_type(self) -> str:
        """
        手法タイプを返す
        
        Returns:
            'long' または 'short'
        """
        pass
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        売買シグナルを生成
        
        Args:
            df: テクニカル指標を含むOHLCVデータ
        
        Returns:
            売買シグナル（1: 買い, -1: 売り, 0: なし）
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """手法の説明を返す"""
        pass
    
    @abstractmethod
    def get_parameters(self) -> dict:
        """手法のパラメータを返す"""
        pass
    
    @abstractmethod
    def check_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        """
        各条件のチェック結果を返す（適合理由生成用）
        
        Args:
            df: データフレーム
            index: チェックする行のインデックス
        
        Returns:
            条件名と判定結果の辞書
        """
        pass
    
    def get_reason(self, df: pd.DataFrame, index: int) -> str:
        """
        適合理由を生成
        
        Args:
            df: データフレーム
            index: チェックする行のインデックス
        
        Returns:
            適合理由の文字列
        """
        conditions = self.check_conditions(df, index)
        met_conditions = [name for name, result in conditions.items() if result]
        
        if not met_conditions:
            return "条件を満たしていません"
        
        reason = f"{self.name()}の条件を満たしています:\n"
        for cond in met_conditions:
            reason += f"  ✓ {cond}\n"
        
        return reason.strip()
