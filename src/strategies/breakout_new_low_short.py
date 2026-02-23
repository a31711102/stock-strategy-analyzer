"""
手法6: 新安値ブレイク（空売り手法）

条件:
1. 本日上場来安値または年初来安値を更新
2. そろそろ新安値
3. 当日出来高10万以上
4. 長期＞中期＞短期の順に移動平均線が並んでいる
5. 本日陰線である
6. 本日の出来高が明確に増加している
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    is_bearish_candle,
    check_ma_order,
    is_near_low,
    # ベクトル化版
    is_bearish_candle_vectorized,
    is_near_low_vectorized,
    check_ma_order_vectorized,
    is_volume_ratio_above_vectorized,
    generate_position_signals_vectorized
)


class BreakoutNewLowShort(BaseStrategy):
    """新安値ブレイク手法（空売り）"""
    
    def __init__(self, lookback: int = 60, min_volume: int = 100000, use_vectorized: bool = True):
        """
        Args:
            lookback: 新安値判定の期間
            min_volume: 最小出来高
            use_vectorized: ベクトル化版を使用するか
        """
        super().__init__()
        self.lookback = lookback
        self.min_volume = min_volume
        self.use_vectorized = use_vectorized
    
    def name(self) -> str:
        return "新安値ブレイク"
    
    def strategy_type(self) -> str:
        return "short"
    
    def get_description(self) -> str:
        return "そろそろ新安値、陰線、出来高増加、移動平均逆行配列"
    
    def get_parameters(self) -> dict:
        return {
            'lookback': self.lookback,
            'min_volume': self.min_volume
        }
    
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """売買シグナルを生成"""
        if self.use_vectorized:
            return self._generate_signals_vectorized(df)
        else:
            return self._generate_signals_loop(df)
    
    def _generate_signals_vectorized(self, df: pd.DataFrame) -> pd.Series:
        """売買シグナルを生成（ベクトル化版）"""
        n = len(df)
        signals = pd.Series(0, index=df.index)
        
        min_period = max(200, self.lookback)
        if n <= min_period:
            return signals
        
        # 条件1: 新安値更新
        recent_low = df['Low'].shift(1).rolling(window=self.lookback, min_periods=1).min()
        cond_new_low = df['Low'] <= recent_low
        
        # 条件2: そろそろ新安値
        cond_near_low = is_near_low_vectorized(df, self.lookback, 5.0)
        
        # 条件3: 出来高10万以上
        cond_volume = df['Volume'] >= self.min_volume
        
        # 条件4: 移動平均逆行配列（長期 > 中期 > 短期）
        ma_columns = ['SMA_200', 'SMA_75', 'SMA_25', 'SMA_5']
        cond_ma_order = check_ma_order_vectorized(df, ma_columns, ascending=True)
        
        # 条件5: 陰線
        cond_bearish = is_bearish_candle_vectorized(df)
        
        # 条件6: 出来高1.5倍以上増加
        cond_volume_surge = is_volume_ratio_above_vectorized(df, 1.5)
        
        # 全条件
        entry_condition = cond_new_low & cond_near_low & cond_volume & cond_ma_order & cond_bearish & cond_volume_surge
        entry_condition.iloc[:min_period] = False
        
        # 決済条件: 5日MAを上回る
        exit_condition = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns:
            exit_condition = (df['Close'] > df['SMA_5']) & df['SMA_5'].notna()
        
        # シグナル生成（ベクトル化版）
        signals = generate_position_signals_vectorized(entry_condition, exit_condition)
        
        return signals
    
    def _generate_signals_loop(self, df: pd.DataFrame) -> pd.Series:
        """売買シグナルを生成（従来のループ版）"""
        signals = pd.Series(0, index=df.index)
        
        for i in range(len(df)):
            if i < max(200, self.lookback):
                continue
            
            conditions = self.check_conditions(df, i)
            
            if all(conditions.values()):
                signals.iloc[i] = 1
            
            elif i > 0 and signals.iloc[i-1] == 1:
                if df['Close'].iloc[i] > df['SMA_5'].iloc[i]:
                    signals.iloc[i] = -1
                else:
                    signals.iloc[i] = 1
        
        return signals
    
    def check_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        """各条件のチェック"""
        row = df.iloc[index]
        prev_row = df.iloc[index - 1]
        
        conditions = {}
        
        recent_low = df['Low'].iloc[max(0, index - self.lookback):index].min()
        conditions['新安値更新'] = row['Low'] <= recent_low
        
        conditions['そろそろ新安値'] = is_near_low(df, index, self.lookback, 5.0)
        
        conditions['出来高10万以上'] = row['Volume'] >= self.min_volume
        
        ma_values = []
        for period in [200, 75, 25, 5]:
            ma_col = f'SMA_{period}'
            if ma_col in row and not pd.isna(row[ma_col]):
                ma_values.append(row[ma_col])
        
        conditions['移動平均逆行配列'] = check_ma_order(ma_values, ascending=True) if len(ma_values) == 4 else False
        
        conditions['本日陰線'] = is_bearish_candle(row)
        
        volume_ratio = row['Volume'] / prev_row['Volume'] if prev_row['Volume'] > 0 else 0
        conditions['出来高明確に増加'] = volume_ratio >= 1.5
        
        return conditions
