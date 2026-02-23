"""
手法5: 押し目空売り（空売り手法）

条件:
1. 当日出来高10万以上
2. 本日陰線である
3. ローソク足の上ヒゲが長い
4. 現在株価はチャートの山の頂点ではない
5. 長期＞中期＞短期の順に移動平均線が並んでいる
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    is_bearish_candle,
    has_long_upper_shadow,
    check_ma_order,
    is_peak,
    calculate_divergence_rate,
    # ベクトル化版
    is_bearish_candle_vectorized,
    has_long_upper_shadow_vectorized,
    check_ma_order_vectorized,
    is_peak_vectorized,
    is_price_below_ma_near_vectorized,
    generate_position_signals_vectorized
)


class PullbackShort(BaseStrategy):
    """押し目空売り手法"""
    
    def __init__(self, min_volume: int = 100000, use_vectorized: bool = True):
        """
        Args:
            min_volume: 最小出来高
            use_vectorized: ベクトル化版を使用するか
        """
        super().__init__()
        self.min_volume = min_volume
        self.use_vectorized = use_vectorized
    
    def name(self) -> str:
        return "押し目空売り"
    
    def strategy_type(self) -> str:
        return "short"
    
    def get_description(self) -> str:
        return "陰線、上ヒゲ長い、移動平均逆行配列、移動平均線が抵抗線"
    
    def get_parameters(self) -> dict:
        return {'min_volume': self.min_volume}
    
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
        
        if n <= 200:
            return signals
        
        # 条件1: 出来高10万以上
        cond_volume = df['Volume'] >= self.min_volume
        
        # 条件2: 陰線
        cond_bearish = is_bearish_candle_vectorized(df)
        
        # 条件3: 上ヒゲ長い
        cond_upper_shadow = has_long_upper_shadow_vectorized(df)
        
        # 条件4: 山の頂点ではない
        cond_not_peak = ~is_peak_vectorized(df)
        
        # 条件5: 移動平均逆行配列
        ma_columns = ['SMA_200', 'SMA_75', 'SMA_25', 'SMA_5']
        cond_ma_order = check_ma_order_vectorized(df, ma_columns, ascending=True)
        
        # 条件6: 移動平均線が抵抗線（75/200日MAの-2%～0%の範囲）
        resistance_found = pd.Series(False, index=df.index)
        for period in [75, 200]:
            ma_col = f'SMA_{period}'
            if ma_col in df.columns:
                resistance_found = resistance_found | is_price_below_ma_near_vectorized(
                    df['Close'], df[ma_col], -2.0, 0.0
                )
        cond_resistance = resistance_found
        
        # 全条件
        entry_condition = cond_volume & cond_bearish & cond_upper_shadow & cond_not_peak & cond_ma_order & cond_resistance
        entry_condition.iloc[:200] = False
        
        # 決済条件: 短期MAが中期MAを上回る
        exit_condition = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns and 'SMA_25' in df.columns:
            exit_condition = df['SMA_5'] > df['SMA_25']
        
        # シグナル生成（ベクトル化版）
        signals = generate_position_signals_vectorized(entry_condition, exit_condition)
        
        return signals
    
    def _generate_signals_loop(self, df: pd.DataFrame) -> pd.Series:
        """売買シグナルを生成（従来のループ版）"""
        signals = pd.Series(0, index=df.index)
        
        for i in range(len(df)):
            if i < 200:
                continue
            
            conditions = self.check_conditions(df, i)
            
            if all(conditions.values()):
                signals.iloc[i] = 1
            
            elif i > 0 and signals.iloc[i-1] == 1:
                if df['SMA_5'].iloc[i] > df['SMA_25'].iloc[i]:
                    signals.iloc[i] = -1
                else:
                    signals.iloc[i] = 1
        
        return signals
    
    def check_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        """各条件のチェック"""
        row = df.iloc[index]
        
        conditions = {}
        
        conditions['出来高10万以上'] = row['Volume'] >= self.min_volume
        conditions['本日陰線'] = is_bearish_candle(row)
        conditions['上ヒゲ長い'] = has_long_upper_shadow(row)
        conditions['山の頂点ではない'] = not is_peak(df, index)
        
        ma_values = []
        for period in [200, 75, 25, 5]:
            ma_col = f'SMA_{period}'
            if ma_col in row and not pd.isna(row[ma_col]):
                ma_values.append(row[ma_col])
        
        conditions['移動平均逆行配列'] = check_ma_order(ma_values, ascending=True) if len(ma_values) == 4 else False
        
        resistance_found = False
        for period in [75, 200]:
            ma_col = f'SMA_{period}'
            if ma_col in row and not pd.isna(row[ma_col]):
                ma_value = row[ma_col]
                diff_pct = ((row['Close'] - ma_value) / ma_value) * 100
                if -2.0 <= diff_pct <= 0:
                    resistance_found = True
                    break
        
        conditions['移動平均線が抵抗線'] = resistance_found
        
        return conditions
