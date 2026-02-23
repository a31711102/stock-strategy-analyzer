"""
手法7: 上昇トレンド反転（空売り手法）

条件:
1. 当日出来高10万以上
2. 本日を含めて3日連続陰線
3. ローソク足の上ヒゲが長い
4. 短期移動平均線が中期移動平均線を下抜け（移動平均線のデッドクロス）
5. MACDがデッドクロスを形成
6. RCIが-100方向へ反転、もしくは-80近辺
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    has_long_upper_shadow,
    is_dead_cross,
    count_consecutive_candles,
    is_bearish_candle,
    # ベクトル化版
    has_long_upper_shadow_vectorized,
    is_dead_cross_vectorized,
    count_consecutive_bearish_vectorized,
    generate_position_signals_vectorized
)


class TrendReversalDownShort(BaseStrategy):
    """上昇トレンド反転手法（空売り）"""
    
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
        return "上昇トレンド反転"
    
    def strategy_type(self) -> str:
        return "short"
    
    def get_description(self) -> str:
        return "3日連続陰線、デッドクロス、RCI反転"
    
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
        
        # 条件2: 3日連続陰線
        cond_3_bearish = count_consecutive_bearish_vectorized(df, 3)
        
        # 条件3: 上ヒゲ長い
        cond_upper_shadow = has_long_upper_shadow_vectorized(df)
        
        # 条件4: デッドクロス（2日以内に発生）
        cond_dead_cross = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns and 'SMA_25' in df.columns:
            dc_today = is_dead_cross_vectorized(df['SMA_5'], df['SMA_25'])
            # 直近2日以内にDCが発生したか
            cond_dead_cross = dc_today.rolling(window=2, min_periods=1).sum() > 0
        
        # 条件6: RCI下降傾向
        cond_rci = pd.Series(False, index=df.index)
        if 'RCI_9' in df.columns:
            rci = df['RCI_9']
            rci_prev = rci.shift(1)
            rci_prev2 = rci.shift(2)
            # RCIが下降傾向（直近2日で減少 or 直近3日で減少）
            rci_decreasing = (rci < rci_prev) | ((rci < rci_prev2) & (rci_prev <= rci_prev2))
            # RCIが極端に低くない（-80以上）
            rci_not_low = rci >= -80
            cond_rci = rci_decreasing & rci_not_low
        
        # OR条件グループ: MACDデッドクロス（オプショナル）
        cond_macd_dc = pd.Series(True, index=df.index)  # デフォルトはTrue（条件なし）
        if 'MACD_12_26_9' in df.columns and 'MACDs_12_26_9' in df.columns:
            macd_dc = is_dead_cross_vectorized(df['MACD_12_26_9'], df['MACDs_12_26_9'])
            # 直近5日以内にMACDデッドクロスが発生 or MACDがシグナルを下回っている
            macd_below_signal = df['MACD_12_26_9'] < df['MACDs_12_26_9']
            cond_macd_dc = macd_dc.rolling(window=5, min_periods=1).sum() > 0
            cond_macd_dc = cond_macd_dc | macd_below_signal
        
        # 全条件（MACDはOR条件として統合）
        entry_condition = cond_volume & cond_3_bearish & cond_upper_shadow & cond_dead_cross & cond_rci & cond_macd_dc
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
        prev_row = df.iloc[index - 1]
        
        conditions = {}
        
        conditions['出来高10万以上'] = row['Volume'] >= self.min_volume
        
        consecutive_bearish = count_consecutive_candles(df, index, 'bearish')
        conditions['3日連続陰線'] = consecutive_bearish >= 3
        
        conditions['上ヒゲ長い'] = has_long_upper_shadow(row)
        
        conditions['移動平均デッドクロス'] = is_dead_cross(
            row['SMA_5'], row['SMA_25'],
            prev_row['SMA_5'], prev_row['SMA_25']
        )
        
        if 'RCI_9' in row and 'RCI_9' in prev_row:
            rci_current = row['RCI_9']
            rci_prev = prev_row['RCI_9']
            conditions['RCI反転or-80近辺'] = (
                (rci_prev > rci_current and rci_current < -50) or
                (-90 <= rci_current <= -70)
            )
        else:
            conditions['RCI反転or-80近辺'] = False
        
        or_conditions = {}
        
        if 'MACD_12_26_9' in row and 'MACDs_12_26_9' in row:
            macd = row['MACD_12_26_9']
            signal = row['MACDs_12_26_9']
            prev_macd = prev_row['MACD_12_26_9']
            prev_signal = prev_row['MACDs_12_26_9']
            or_conditions['MACDデッドクロス'] = is_dead_cross(macd, signal, prev_macd, prev_signal)
        else:
            or_conditions['MACDデッドクロス'] = False
        
        conditions['OR条件グループ'] = any(or_conditions.values())
        
        return conditions
