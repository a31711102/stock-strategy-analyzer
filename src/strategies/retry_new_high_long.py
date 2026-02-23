"""
手法3: 新高値リトライ（買い手法）

条件:
1. そろそろ新高値もしくは上場来高値である
2. 本日新高値ではない
3. 本日陽線である
4. 当日安値が前日安値を割っていない
5. 価格が前日比5%以上である
6. 前日が陰線
7. 本日ボリンジャーバンド3シグマを抜けた
8. 前日と比べて出来高が明確に増加
9. 前日に株価が中期移動平均線上にある、もしくは支持線となっており少し上にある
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    is_bullish_candle,
    is_bearish_candle,
    is_near_high,
    is_volume_increasing,
    calculate_divergence_rate,
    # ベクトル化版
    is_bullish_candle_vectorized,
    is_bearish_candle_vectorized,
    is_near_high_vectorized,
    is_volume_ratio_above_vectorized,
    calculate_divergence_rate_vectorized,
    is_price_near_ma_vectorized,
    generate_position_signals_vectorized
)


class RetryNewHighLong(BaseStrategy):
    """新高値リトライ手法"""
    
    def __init__(self, lookback: int = 60, price_change_threshold: float = 5.0, use_vectorized: bool = True):
        """
        Args:
            lookback: 新高値判定の期間
            price_change_threshold: 前日比の閾値（%）
            use_vectorized: ベクトル化版を使用するか
        """
        super().__init__()
        self.lookback = lookback
        self.price_change_threshold = price_change_threshold
        self.use_vectorized = use_vectorized
    
    def name(self) -> str:
        return "新高値リトライ"
    
    def strategy_type(self) -> str:
        return "long"
    
    def get_description(self) -> str:
        return "そろそろ新高値、陽線、前日比5%以上、ボリンジャーバンド3σ抜け"
    
    def get_parameters(self) -> dict:
        return {
            'lookback': self.lookback,
            'price_change_threshold': self.price_change_threshold
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
        
        # 必須条件
        # 条件1: そろそろ新高値
        cond_near_high = is_near_high_vectorized(df, self.lookback, 5.0)
        
        # 条件2: 本日新高値ではない
        recent_high = df['High'].shift(1).rolling(window=self.lookback, min_periods=1).max()
        cond_not_new_high = df['High'] < recent_high
        
        # 条件3: 本日陽線
        cond_bullish = is_bullish_candle_vectorized(df)
        
        # 条件4: 当日安値が前日安値以上
        cond_low_above = df['Low'] >= df['Low'].shift(1)
        
        # 条件5: 出来高1.5倍以上増加
        cond_volume_surge = is_volume_ratio_above_vectorized(df, 1.5)
        
        # OR条件グループ
        # OR条件1: 前日比5%以上
        price_change = ((df['Close'] - df['Close'].shift(1)) / df['Close'].shift(1)) * 100
        or_cond_price = price_change >= self.price_change_threshold
        
        # OR条件2: 前日陰線
        or_cond_prev_bearish = is_bearish_candle_vectorized(df).shift(1).fillna(False)
        
        # OR条件3: ボリンジャーバンド3σ抜け
        or_cond_bb = pd.Series(False, index=df.index)
        if 'BBU_20_3.0' in df.columns:
            or_cond_bb = df['Close'] > df['BBU_20_3.0']
        
        # OR条件4: 前日中期MA近辺
        or_cond_ma_near = pd.Series(False, index=df.index)
        if 'SMA_75' in df.columns:
            divergence = calculate_divergence_rate_vectorized(df['Close'].shift(1), df['SMA_75'].shift(1)).abs()
            or_cond_ma_near = divergence < 5.0
        
        cond_or_group = or_cond_price | or_cond_prev_bearish | or_cond_bb | or_cond_ma_near
        
        # 全条件
        entry_condition = cond_near_high & cond_not_new_high & cond_bullish & cond_low_above & cond_volume_surge & cond_or_group
        entry_condition.iloc[:min_period] = False
        
        # 決済条件: BBL下限を下回る
        exit_condition = pd.Series(False, index=df.index)
        if 'BBL_20_3.0' in df.columns:
            exit_condition = df['Close'] < df['BBL_20_3.0']
        
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
                if 'BBL_20_3.0' in df.columns and df['Close'].iloc[i] < df['BBL_20_3.0'].iloc[i]:
                    signals.iloc[i] = -1
                else:
                    signals.iloc[i] = 1
        
        return signals
    
    def check_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        """各条件のチェック"""
        row = df.iloc[index]
        prev_row = df.iloc[index - 1]
        
        conditions = {}
        
        conditions['そろそろ新高値'] = is_near_high(df, index, self.lookback, 5.0)
        
        recent_high = df['High'].iloc[max(0, index - self.lookback):index].max()
        conditions['本日新高値ではない'] = row['High'] < recent_high
        
        conditions['本日陽線'] = is_bullish_candle(row)
        conditions['当日安値が前日安値以上'] = row['Low'] >= prev_row['Low']
        
        volume_ratio = row['Volume'] / prev_row['Volume'] if prev_row['Volume'] > 0 else 0
        conditions['出来高明確に増加'] = volume_ratio >= 1.5
        
        or_conditions = {}
        
        price_change = ((row['Close'] - prev_row['Close']) / prev_row['Close']) * 100
        or_conditions['前日比5%以上'] = price_change >= self.price_change_threshold
        
        or_conditions['前日陰線'] = is_bearish_candle(prev_row)
        
        if 'BBU_20_3.0' in row:
            or_conditions['ボリンジャーバンド3σ抜け'] = row['Close'] > row['BBU_20_3.0']
        else:
            or_conditions['ボリンジャーバンド3σ抜け'] = False
        
        if 'SMA_75' in prev_row and not pd.isna(prev_row['SMA_75']):
            divergence = calculate_divergence_rate(prev_row['Close'], prev_row['SMA_75'])
            or_conditions['前日中期MA近辺'] = abs(divergence) < 5.0
        else:
            or_conditions['前日中期MA近辺'] = False
        
        conditions['OR条件グループ'] = any(or_conditions.values())
        
        return conditions
