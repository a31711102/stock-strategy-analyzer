"""
手法2: 押し目買い（買い手法）

条件:
1. 5日移動平均線の乖離率10%
2. 週足・月足が明確に上昇トレンド
3. 何らかの移動平均線が株価を下支えしており、近辺で反騰している
4. 日足で見ると下降トレンドである
5. 前日と比べて出来高が減少
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    calculate_divergence_rate, 
    is_volume_increasing,
    # ベクトル化版
    calculate_divergence_rate_vectorized,
    is_volume_increasing_vectorized,
    is_ma_trending_up_vectorized,
    is_price_near_ma_vectorized,
    generate_position_signals_vectorized
)


class PullbackBuyLong(BaseStrategy):
    """押し目買い手法"""
    
    def __init__(self, divergence_threshold: float = -10.0, use_vectorized: bool = True):
        """
        Args:
            divergence_threshold: 乖離率の閾値（%）
            use_vectorized: ベクトル化版を使用するか
        """
        super().__init__()
        self.divergence_threshold = divergence_threshold
        self.use_vectorized = use_vectorized
    
    def name(self) -> str:
        return "押し目買い"
    
    def strategy_type(self) -> str:
        return "long"
    
    def get_description(self) -> str:
        return "5日MA乖離率10%、週足・月足上昇トレンド、日足下降、出来高減少"
    
    def get_parameters(self) -> dict:
        return {'divergence_threshold': self.divergence_threshold}
    
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
        
        # ==== 必須条件 ====
        
        # 条件1: 長期上昇トレンド（200日MAが上向き + 75日MAが上向き）
        cond_long_trend = pd.Series(False, index=df.index)
        if 'SMA_200' in df.columns and 'SMA_75' in df.columns:
            sma200_up = is_ma_trending_up_vectorized(df['SMA_200'], 20)
            sma75_up = is_ma_trending_up_vectorized(df['SMA_75'], 20)
            cond_long_trend = sma200_up & sma75_up
        
        # 条件2: 移動平均線が下支え（25/75/200日MAの-2%以内、上方向は制限なし）
        support_found = pd.Series(False, index=df.index)
        for period in [25, 75, 200]:
            ma_col = f'SMA_{period}'
            if ma_col in df.columns:
                # 株価がMAの-2%以内（下支え状態）
                # MA * 0.98 <= Close <= MA * 1.02 の代わりに
                # MA * 0.98 <= Close (上方向は制限なし)
                lower_bound = df[ma_col] * 0.98
                is_supported = (df['Close'] >= lower_bound) & df[ma_col].notna()
                support_found = support_found | is_supported
        cond_support = support_found
        
        # 条件3: 日足下降トレンド（5日MAが下向き）
        cond_short_down = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns:
            cond_short_down = df['SMA_5'] < df['SMA_5'].shift(5)
        
        # 条件4: 出来高減少（当日陰線の場合のみ適用）
        cond_volume = pd.Series(True, index=df.index)  # デフォルトはTrue（条件なし）
        is_bearish = df['Close'] < df['Open']
        volume_decrease = ~is_volume_increasing_vectorized(df)
        # 陰線の日のみ出来高減少条件を適用
        cond_volume = ~is_bearish | (is_bearish & volume_decrease)
        
        # ==== OR条件（いずれか1つを満たせばOK）====
        
        # OR条件A: 5日MA乖離率-5%以下（緩和: -10%から-5%に）
        cond_divergence = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns:
            divergence = calculate_divergence_rate_vectorized(df['Close'], df['SMA_5'])
            cond_divergence = divergence <= -5.0  # 緩和: -10% → -5%
        
        # OR条件B: RCIが-80以下（売られすぎ）
        cond_rci_oversold = pd.Series(False, index=df.index)
        if 'RCI_9' in df.columns:
            cond_rci_oversold = df['RCI_9'] <= -80
        
        # OR条件を統合
        or_conditions = cond_divergence | cond_rci_oversold
        
        # 最終エントリー条件 = 必須条件 AND (OR条件のいずれか)
        entry_condition = cond_long_trend & cond_support & cond_short_down & cond_volume & or_conditions
        entry_condition.iloc[:200] = False
        
        # 決済条件: 5日MAを上回る + 陽線
        exit_condition = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns:
            is_bullish = df['Close'] > df['Open']
            above_ma5 = (df['Close'] > df['SMA_5']) & df['SMA_5'].notna()
            exit_condition = is_bullish & above_ma5
        
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
                if df['Close'].iloc[i] > df['SMA_5'].iloc[i]:
                    signals.iloc[i] = -1
                else:
                    signals.iloc[i] = 1
        
        return signals
    
    def check_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        """各条件のチェック"""
        row = df.iloc[index]
        
        conditions = {}
        
        if 'SMA_5' in row and not pd.isna(row['SMA_5']):
            divergence = calculate_divergence_rate(row['Close'], row['SMA_5'])
            conditions['5日MA乖離率-10%以下'] = divergence <= self.divergence_threshold
        else:
            conditions['5日MA乖離率-10%以下'] = False
        
        if index >= 50:
            sma_200_trend = df['SMA_200'].iloc[index] > df['SMA_200'].iloc[index - 20]
            conditions['長期上昇トレンド'] = sma_200_trend
        else:
            conditions['長期上昇トレンド'] = False
        
        support_found = False
        for period in [25, 75, 200]:
            ma_col = f'SMA_{period}'
            if ma_col in row and not pd.isna(row[ma_col]):
                if abs(calculate_divergence_rate(row['Close'], row[ma_col])) < 2.0:
                    support_found = True
                    break
        conditions['移動平均線が下支え'] = support_found
        
        if index >= 10:
            sma_5_trend = df['SMA_5'].iloc[index] < df['SMA_5'].iloc[index - 5]
            conditions['日足下降トレンド'] = sma_5_trend
        else:
            conditions['日足下降トレンド'] = False
        
        conditions['出来高減少'] = not is_volume_increasing(df, index)
        
        return conditions
