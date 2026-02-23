"""
手法8: 順張り空売り（空売り手法）

条件:
1. 出来高前日比1.2倍以上
2. 当日出来高10万以上（流動性高）
3. 中期移動平均線＞短期移動平均線
4. 当日移動平均線がデッドクロス
5. 本日陰線
6. ローソク足の上ヒゲが長い
7. 前日と比べて出来高が増加
8. 移動平均線が長期＞中期＞短期の順に並んでいる
9. 信用倍率が5倍以上
10. 移動平均線のデッドクロスが直近3日以内
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    is_bearish_candle,
    has_long_upper_shadow,
    is_dead_cross,
    check_ma_order,
    is_volume_increasing,
    # ベクトル化版
    is_bearish_candle_vectorized,
    has_long_upper_shadow_vectorized,
    is_dead_cross_vectorized,
    check_ma_order_vectorized,
    is_volume_increasing_vectorized,
    is_volume_ratio_above_vectorized,
    count_bearish_in_window_vectorized,
    generate_position_signals_vectorized
)


class MomentumShort(BaseStrategy):
    """順張り空売り手法"""
    
    def __init__(self, min_volume: int = 100000, min_margin_ratio: float = 5.0, use_vectorized: bool = True):
        """
        Args:
            min_volume: 最小出来高
            min_margin_ratio: 最小信用倍率
            use_vectorized: ベクトル化版を使用するか
        """
        super().__init__()
        self.min_volume = min_volume
        self.min_margin_ratio = min_margin_ratio
        self.use_vectorized = use_vectorized
    
    def name(self) -> str:
        return "順張り空売り"
    
    def strategy_type(self) -> str:
        return "short"
    
    def get_description(self) -> str:
        return "デッドクロス、陰線、上ヒゲ長い、出来高増加、移動平均逆行配列、直近10日間の過半数が陰線"
    
    def get_parameters(self) -> dict:
        return {
            'min_volume': self.min_volume,
            'min_margin_ratio': self.min_margin_ratio
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
        
        if n <= 200:
            return signals
        
        # 条件1: 出来高前日比1.2倍以上
        cond_volume_ratio = is_volume_ratio_above_vectorized(df, 1.2)
        
        # 条件2: 出来高10万以上
        cond_volume = df['Volume'] >= self.min_volume
        
        # 条件3: 中期 > 短期
        cond_mid_over_short = pd.Series(False, index=df.index)
        if 'SMA_25' in df.columns and 'SMA_5' in df.columns:
            cond_mid_over_short = df['SMA_25'] > df['SMA_5']
        
        # 条件4: デッドクロス
        cond_dead_cross = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns and 'SMA_25' in df.columns:
            cond_dead_cross = is_dead_cross_vectorized(df['SMA_5'], df['SMA_25'])
        
        # 条件5: 陰線
        cond_bearish = is_bearish_candle_vectorized(df)
        
        # 条件6: 上ヒゲ長い
        cond_upper_shadow = has_long_upper_shadow_vectorized(df)
        
        # 条件7: 出来高増加
        cond_volume_inc = is_volume_increasing_vectorized(df)
        
        # 条件8: 移動平均逆行配列
        ma_columns = ['SMA_200', 'SMA_75', 'SMA_25', 'SMA_5']
        cond_ma_order = check_ma_order_vectorized(df, ma_columns, ascending=True)
        
        # 条件11: 直近10日間の過半数が陰線
        bearish_count = count_bearish_in_window_vectorized(df, 10)
        cond_majority_bearish = bearish_count > 5
        
        # OR条件: デッドクロス直近3日以内
        dc_today = cond_dead_cross
        dc_1day = cond_dead_cross.shift(1).fillna(False)
        dc_2day = cond_dead_cross.shift(2).fillna(False)
        cond_or_group = dc_today | dc_1day | dc_2day
        
        # 全条件
        entry_condition = (cond_volume_ratio & cond_volume & cond_mid_over_short & 
                          cond_bearish & cond_upper_shadow & cond_volume_inc & 
                          cond_ma_order & cond_majority_bearish & cond_or_group)
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
            
            conditions_without_margin = {k: v for k, v in conditions.items() 
                                        if k != '信用倍率5倍以上'}
            
            if all(conditions_without_margin.values()):
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
        prev_row = df.iloc[index - 1]
        
        conditions = {}
        
        volume_ratio = row['Volume'] / prev_row['Volume'] if prev_row['Volume'] > 0 else 0
        conditions['出来高前日比1.2倍以上'] = volume_ratio >= 1.2
        
        conditions['出来高10万以上'] = row['Volume'] >= self.min_volume
        conditions['中期MA>短期MA'] = row['SMA_25'] > row['SMA_5']
        
        conditions['デッドクロス'] = is_dead_cross(
            row['SMA_5'], row['SMA_25'],
            prev_row['SMA_5'], prev_row['SMA_25']
        )
        
        conditions['本日陰線'] = is_bearish_candle(row)
        conditions['上ヒゲ長い'] = has_long_upper_shadow(row)
        conditions['出来高増加'] = is_volume_increasing(df, index)
        
        ma_values = []
        for period in [200, 75, 25, 5]:
            ma_col = f'SMA_{period}'
            if ma_col in row and not pd.isna(row[ma_col]):
                ma_values.append(row[ma_col])
        
        conditions['移動平均逆行配列'] = check_ma_order(ma_values, ascending=True) if len(ma_values) == 4 else False
        
        if index >= 9:
            bearish_count = 0
            for j in range(index - 9, index + 1):
                if is_bearish_candle(df.iloc[j]):
                    bearish_count += 1
            conditions['直近10日間の過半数が陰線'] = bearish_count > 5
        else:
            conditions['直近10日間の過半数が陰線'] = False
        
        or_conditions = {}
        or_conditions['信用倍率5倍以上'] = False
        
        dead_cross_recent = False
        for j in range(max(0, index - 2), index + 1):
            if j > 0:
                if is_dead_cross(
                    df['SMA_5'].iloc[j], df['SMA_25'].iloc[j],
                    df['SMA_5'].iloc[j-1], df['SMA_25'].iloc[j-1]
                ):
                    dead_cross_recent = True
                    break
        or_conditions['デッドクロス直近3日以内'] = dead_cross_recent
        
        conditions['OR条件グループ'] = any(or_conditions.values())
        
        return conditions
