"""
手法4: 下降トレンド反転（買い手法）

条件:
1. 出来高前日比1.2倍以上
2. 当日出来高10万以上（流動性高）
3. 短期移動平均線＞中期移動平均線
4. 当日移動平均線がゴールデンクロス
5. 長期移動平均線が横ばいor上向き
6. 長期移動平均と株価を比べた際に、乖離率が10%以内である
7. 直近5日でローソク足の実体が大きすぎない、実体が株価の10%以上ではないのが目安
8. ローソク足の下ヒゲが長い
9. 株価が長期移動平均線よりも上にある
10. 当日or前日が陽線
11. RCIが-80~+80の間で、マイナス圏から＋圏方向に推移していること
12. RCIがゴールデンクロスを形成
13. 2日以上連続陽線で、2日とも出来高が増加している
"""
import pandas as pd
import numpy as np
from typing import Dict
from .base import BaseStrategy
from .utils import (
    is_bullish_candle,
    is_golden_cross,
    has_long_lower_shadow,
    calculate_divergence_rate,
    count_consecutive_candles,
    get_body_size_ratio,
    # ベクトル化版
    is_bullish_candle_vectorized,
    is_golden_cross_vectorized,
    has_long_lower_shadow_vectorized,
    calculate_divergence_rate_vectorized,
    get_body_size_ratio_vectorized,
    is_volume_ratio_above_vectorized,
    is_ma_trending_up_vectorized,
    count_consecutive_bullish_vectorized,
    generate_position_signals_vectorized
)


class TrendReversalUpLong(BaseStrategy):
    """
    下降トレンド反転手法
    
    必須条件（10条件）:
    1. 出来高前日比1.2倍以上
    2. 当日出来高10万以上
    3. 短期移動平均線＞中期移動平均線
    4. 当日移動平均線がゴールデンクロス
    5. 長期移動平均線が横ばいor上向き
    6. 直近5日でローソク足の実体が大きすぎない
    7. ローソク足の下ヒゲが長い
    8. 株価が長期移動平均線よりも上
    9. 当日or前日が陽線
    10. RCIが-80~+80の間でマイナス圈から＋圈方向
    
    OR条件グループ（オプショナル、いずれか1つ）:
    - 長期MAとの乖離率10%以内
    - RCIゴールデンクロス
    - 2日以上連続陽線で出来高増加
    """
    
    def __init__(self, min_volume: int = 100000, or_conditions_required: bool = False, use_vectorized: bool = True):
        """
        Args:
            min_volume: 最小出来高
            or_conditions_required: OR条件を必須とするか（False=オプショナル、True=必須）
            use_vectorized: ベクトル化版を使用するか
        """
        super().__init__()
        self.min_volume = min_volume
        self.or_conditions_required = or_conditions_required
        self.use_vectorized = use_vectorized
    
    def name(self) -> str:
        return "下降トレンド反転"
    
    def strategy_type(self) -> str:
        return "long"
    
    def get_description(self) -> str:
        return "ゴールデンクロス、RCI反転、連続陽線、出来高増加"
    
    def get_parameters(self) -> dict:
        return {
            'min_volume': self.min_volume,
            'or_conditions_required': self.or_conditions_required
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
        
        # 条件3: 短期 > 中期
        cond_short_over_mid = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns and 'SMA_25' in df.columns:
            cond_short_over_mid = df['SMA_5'] > df['SMA_25']
        
        # 条件4: ゴールデンクロス（直近3日以内に発生）
        cond_golden_cross = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns and 'SMA_25' in df.columns:
            gc_today = is_golden_cross_vectorized(df['SMA_5'], df['SMA_25'])
            # 直近3日以内にGCが発生したか
            cond_golden_cross = gc_today.rolling(window=3, min_periods=1).sum() > 0
        
        # 条件5: 長期MA上向き
        cond_long_up = pd.Series(False, index=df.index)
        if 'SMA_200' in df.columns:
            cond_long_up = is_ma_trending_up_vectorized(df['SMA_200'], 10)
        
        # 条件7: 直近5日の実体が大きすぎない
        body_ratio = get_body_size_ratio_vectorized(df)
        large_body = (body_ratio > 0.10).rolling(window=5, min_periods=1).sum()
        cond_body_ok = large_body == 0
        
        # 条件8: 下ヒゲ長い
        cond_lower_shadow = has_long_lower_shadow_vectorized(df)
        
        # 条件9: 株価 > 長期MA
        cond_above_200 = pd.Series(False, index=df.index)
        if 'SMA_200' in df.columns:
            cond_above_200 = df['Close'] > df['SMA_200']
        
        # 条件10: 当日or前日陽線
        is_bullish = is_bullish_candle_vectorized(df)
        cond_bullish_today_or_prev = is_bullish | is_bullish.shift(1).fillna(False)
        
        # 条件11: RCI上昇傾向（直近3日で増加）
        cond_rci = pd.Series(False, index=df.index)
        if 'RCI_9' in df.columns:
            rci = df['RCI_9']
            rci_prev = rci.shift(1)
            rci_prev2 = rci.shift(2)
            # RCIが上昇傾向（直近2日で増加 or 直近3日で増加）
            rci_increasing = (rci > rci_prev) | ((rci > rci_prev2) & (rci_prev >= rci_prev2))
            # RCIが極端に高くない（+80以下）
            rci_not_high = rci <= 80
            cond_rci = rci_increasing & rci_not_high
        
        # 全必須条件
        entry_condition = (cond_volume_ratio & cond_volume & cond_short_over_mid & 
                          cond_golden_cross & cond_long_up & cond_body_ok &
                          cond_lower_shadow & cond_above_200 & cond_bullish_today_or_prev & cond_rci)
        
        # OR条件グループ
        if self.or_conditions_required:
            # OR条件1: 長期MA乖離率10%以内
            or_cond_divergence = pd.Series(False, index=df.index)
            if 'SMA_200' in df.columns:
                divergence = calculate_divergence_rate_vectorized(df['Close'], df['SMA_200']).abs()
                or_cond_divergence = divergence <= 10.0
            
            # OR条件2: RCIゴールデンクロス
            or_cond_rci_gc = pd.Series(False, index=df.index)
            if 'RCI_9' in df.columns and 'RCI_26' in df.columns:
                or_cond_rci_gc = is_golden_cross_vectorized(df['RCI_9'], df['RCI_26'])
            
            # OR条件3: 2日連続陽線で出来高増加
            is_2_bullish = count_consecutive_bullish_vectorized(df, 2)
            vol_inc_today = df['Volume'] > df['Volume'].shift(1)
            vol_inc_prev = df['Volume'].shift(1) > df['Volume'].shift(2)
            or_cond_bullish_vol = is_2_bullish & vol_inc_today & vol_inc_prev
            
            cond_or_group = or_cond_divergence | or_cond_rci_gc | or_cond_bullish_vol
            entry_condition = entry_condition & cond_or_group
        
        entry_condition.iloc[:200] = False
        
        # 決済条件: 短期MAが中期MAを下回る
        exit_condition = pd.Series(False, index=df.index)
        if 'SMA_5' in df.columns and 'SMA_25' in df.columns:
            exit_condition = df['SMA_5'] < df['SMA_25']
        
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
                if df['SMA_5'].iloc[i] < df['SMA_25'].iloc[i]:
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
        conditions['短期MA>中期MA'] = row['SMA_5'] > row['SMA_25']
        
        conditions['ゴールデンクロス'] = is_golden_cross(
            row['SMA_5'], row['SMA_25'],
            prev_row['SMA_5'], prev_row['SMA_25']
        )
        
        if index >= 10:
            conditions['長期MA上向き'] = df['SMA_200'].iloc[index] >= df['SMA_200'].iloc[index - 10]
        else:
            conditions['長期MA上向き'] = False
        
        large_body_count = 0
        for j in range(max(0, index - 4), index + 1):
            if get_body_size_ratio(df.iloc[j]) > 0.10:
                large_body_count += 1
        conditions['実体が大きすぎない'] = large_body_count == 0
        
        conditions['下ヒゲ長い'] = has_long_lower_shadow(row)
        conditions['株価>長期MA'] = row['Close'] > row['SMA_200']
        conditions['当日or前日陽線'] = is_bullish_candle(row) or is_bullish_candle(prev_row)
        
        if 'RCI_9' in row and 'RCI_9' in prev_row:
            rci_current = row['RCI_9']
            rci_prev = prev_row['RCI_9']
            conditions['RCI反転'] = (-80 <= rci_current <= 80 and 
                                    rci_prev < 0 and rci_current > 0)
        else:
            conditions['RCI反転'] = False
        
        or_conditions = {}
        
        divergence = calculate_divergence_rate(row['Close'], row['SMA_200'])
        or_conditions['長期MA乖離率10%以内'] = abs(divergence) <= 10.0
        
        if 'RCI_9' in row and 'RCI_26' in row:
            or_conditions['RCIゴールデンクロス'] = is_golden_cross(
                row['RCI_9'], row['RCI_26'],
                prev_row['RCI_9'], prev_row['RCI_26']
            )
        else:
            or_conditions['RCIゴールデンクロス'] = False
        
        consecutive_bullish = count_consecutive_candles(df, index, 'bullish')
        volume_increasing_2days = (index >= 1 and 
                                   row['Volume'] > prev_row['Volume'] and
                                   prev_row['Volume'] > df['Volume'].iloc[index - 2] if index >= 2 else False)
        or_conditions['連続陽線かつ出来高増加'] = consecutive_bullish >= 2 and volume_increasing_2days
        
        if self.or_conditions_required:
            conditions['OR条件グループ'] = any(or_conditions.values())
        else:
            conditions['OR条件グループ'] = True
        
        return conditions
