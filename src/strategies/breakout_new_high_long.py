"""
手法1: 新高値ブレイク（買い手法）

条件:
1. そろそろ新高値（直近N日の高値に近い）
2. 前日と比べて出来高が増加
3. 本日陽線で、5日移動平均を上抜け
4. 移動平均線が5日＞25日＞75日＞200日に並んでいる
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    is_bullish_candle,
    check_ma_order,
    is_near_high,
    is_volume_increasing,
    # ベクトル化版
    is_bullish_candle_vectorized,
    is_near_high_vectorized,
    is_volume_increasing_vectorized,
    check_ma_order_vectorized,
    generate_position_signals_vectorized
)



class BreakoutNewHighLong(BaseStrategy):
    """新高値ブレイク手法（買い）"""
    
    def __init__(self, lookback: int = 60, threshold_pct: float = 3.0, use_vectorized: bool = True):
        """
        Args:
            lookback: 新高値判定の期間
            threshold_pct: 高値との差が何%以内で「そろそろ」とするか（デフォルト: 3.0%）
            use_vectorized: ベクトル化版を使用するか（デフォルト: True）
        """
        super().__init__()
        self.lookback = lookback
        self.threshold_pct = threshold_pct
        self.use_vectorized = use_vectorized
    
    def name(self) -> str:
        return "新高値ブレイク"
    
    def strategy_type(self) -> str:
        return "long"
    
    def get_description(self) -> str:
        return "そろそろ新高値で出来高増加、陽線で5日MA上抜け、移動平均が順行配列"
    
    def get_parameters(self) -> dict:
        return {
            'lookback': self.lookback,
            'threshold_pct': self.threshold_pct
        }
    
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """売買シグナルを生成"""
        if self.use_vectorized:
            return self._generate_signals_vectorized(df)
        else:
            return self._generate_signals_loop(df)
    
    def _generate_signals_vectorized(self, df: pd.DataFrame) -> pd.Series:
        """
        売買シグナルを生成（ベクトル化版・高速）
        
        [処理概要]
        1. 各条件をベクトル演算で一括計算
        2. 全条件を満たす行にエントリーシグナル(1)を設定
        3. 決済条件を満たす行にエグジットシグナル(-1)を設定
        """
        n = len(df)
        signals = pd.Series(0, index=df.index)
        
        # 最低限必要なデータ期間
        min_period = max(200, self.lookback)
        if n <= min_period:
            return signals
        
        # ===== 条件1: そろそろ新高値 =====
        # 株価に応じて閾値を動的に調整
        # 3000円以上: 3%, 1000円未満: 5%, その他: 4%
        avg_price = df['Close'].mean()
        if avg_price >= 3000:
            threshold = 3.0
        elif avg_price < 1000:
            threshold = 5.0
        else:
            threshold = 4.0
        cond_near_high = is_near_high_vectorized(df, self.lookback, threshold)
        
        # ===== 条件2: 出来高増加（前日比1.5倍以上）=====
        cond_volume = pd.Series(False, index=df.index)
        if 'Volume' in df.columns:
            cond_volume = df['Volume'] >= df['Volume'].shift(1) * 1.5
        
        # ===== 条件3: 陽線かつ5日MA上抜け =====
        cond_bullish = is_bullish_candle_vectorized(df)
        cond_above_ma5 = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns:
            cond_above_ma5 = (df['Close'] > df['SMA_5']) & df['SMA_5'].notna()
        cond_bullish_above_ma = cond_bullish & cond_above_ma5
        
        # ===== 条件4: OR条件グループ =====
        # A) MA完全順行配列（5日 > 25日 > 75日 > 200日）
        ma_columns = ['SMA_5', 'SMA_25', 'SMA_75', 'SMA_200']
        cond_ma_full_order = check_ma_order_vectorized(df, ma_columns, ascending=True)
        
        # B) 5日 > 25日 かつ 終値 > 75日MA（上昇初期）
        cond_short_over_mid = pd.Series(False, index=df.index)
        cond_above_ma75 = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns and 'SMA_25' in df.columns:
            cond_short_over_mid = df['SMA_5'] > df['SMA_25']
        if 'SMA_75' in df.columns:
            cond_above_ma75 = df['Close'] > df['SMA_75']
        cond_early_uptrend = cond_short_over_mid & cond_above_ma75
        
        # C) 新高値更新 かつ 出来高2倍以上（ブレイクアウト確定）
        cond_new_high = pd.Series(False, index=df.index)
        cond_volume_2x = pd.Series(False, index=df.index)
        high_rolling = df['High'].rolling(window=self.lookback, min_periods=self.lookback).max()
        cond_new_high = df['High'] >= high_rolling
        if 'Volume' in df.columns:
            cond_volume_2x = df['Volume'] >= df['Volume'].shift(1) * 2
        cond_breakout_confirmed = cond_new_high & cond_volume_2x
        
        # OR条件グループ（A OR B OR C）
        cond_or_group = cond_ma_full_order | cond_early_uptrend | cond_breakout_confirmed
        
        # ===== 全条件を満たす行 =====
        entry_condition = cond_near_high & cond_volume & cond_bullish_above_ma & cond_or_group
        
        # 最低期間以降にのみシグナルを設定
        entry_condition.iloc[:min_period] = False
        
        # ===== 決済条件: 陰線で5日線を下抜け =====
        exit_condition = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns:
            # 陰線（終値 < 始値）
            is_bearish = df['Close'] < df['Open']
            # 5日線を下抜け（終値 < 5日MA）
            below_ma5 = (df['Close'] < df['SMA_5']) & df['SMA_5'].notna()
            # 条件を満たす
            exit_condition = is_bearish & below_ma5
        
        # ===== シグナル生成（ベクトル化版）=====
        signals = generate_position_signals_vectorized(entry_condition, exit_condition)
        
        return signals

    
    def _generate_signals_loop(self, df: pd.DataFrame) -> pd.Series:
        """売買シグナルを生成（従来のループ版・互換性維持用）"""
        signals = pd.Series(0, index=df.index)
        
        for i in range(len(df)):
            if i < max(200, self.lookback):  # 最低限必要なデータ期間
                continue
            
            conditions = self.check_conditions(df, i)
            
            # 全条件を満たす場合、買いシグナル
            if all(conditions.values()):
                signals.iloc[i] = 1
            
            # 簡易的な決済ルール: 5日移動平均を下回ったら決済
            elif i > 0 and signals.iloc[i-1] == 1:
                if df['Close'].iloc[i] < df['SMA_5'].iloc[i]:
                    signals.iloc[i] = -1
                else:
                    signals.iloc[i] = 1  # ポジション継続
        
        return signals
    
    def check_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        """各条件のチェック"""
        row = df.iloc[index]
        prev_row = df.iloc[index - 1] if index > 0 else row
        
        conditions = {}
        
        # 1. そろそろ新高値
        conditions['そろそろ新高値'] = is_near_high(
            df, index, self.lookback, self.threshold_pct
        )
        
        # 2. 前日と比べて出来高が増加
        conditions['出来高増加'] = is_volume_increasing(df, index)
        
        # 3. 本日陽線で、5日移動平均を上抜け
        is_bullish = is_bullish_candle(row)
        above_ma5 = row['Close'] > row['SMA_5'] if 'SMA_5' in row and not pd.isna(row['SMA_5']) else False
        conditions['陽線かつ5日MA上抜け'] = is_bullish and above_ma5
        
        # 4. 移動平均線が5日＞25日＞75日＞200日
        ma_values = []
        for period in [5, 25, 75, 200]:
            ma_col = f'SMA_{period}'
            if ma_col in row and not pd.isna(row[ma_col]):
                ma_values.append(row[ma_col])
        
        conditions['移動平均順行配列'] = check_ma_order(ma_values, ascending=True) if len(ma_values) == 4 else False
        
        return conditions

