"""
シグナル接近検出モジュール

直近1〜3ヶ月のデータをもとに、各戦略のシグナル発生が近い銘柄を検出する。
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class StrategyType(Enum):
    """戦略タイプ"""
    BREAKOUT_NEW_HIGH = "新高値ブレイク"
    PULLBACK_BUY = "押し目買い"
    RETRY_NEW_HIGH = "新高値リトライ"
    TREND_REVERSAL_UP = "下降トレンド反転"
    PULLBACK_SHORT = "押し目空売り"
    BREAKOUT_NEW_LOW = "新安値ブレイク"
    TREND_REVERSAL_DOWN = "上昇トレンド反転"
    MOMENTUM_SHORT = "順張り空売り"


@dataclass
class ApproachingSignal:
    """接近シグナル情報"""
    code: str
    name: str
    strategy: str
    estimated_days: Optional[int]  # 推定残り日数（None=不明）
    conditions_met: List[str]       # 満たしている条件
    conditions_pending: List[str]   # 未達の条件
    score: float                    # 接近スコア（0-100）
    current_price: float
    last_updated: str


class SignalDetector:
    """シグナル接近検出クラス"""
    
    def __init__(self, lookback_days: int = 60):
        """
        Args:
            lookback_days: 分析対象期間（日数）
        """
        self.lookback_days = lookback_days
    
    def detect_all_strategies(self, df: pd.DataFrame, code: str, name: str) -> Dict[str, ApproachingSignal]:
        """
        全戦略のシグナル接近を検出
        
        Args:
            df: 株価データ（指標計算済み）
            code: 銘柄コード
            name: 銘柄名
        
        Returns:
            戦略名をキーとした接近シグナル辞書
        """
        results = {}
        
        # 直近データのみ使用
        if len(df) > self.lookback_days:
            df_recent = df.tail(self.lookback_days).copy()
        else:
            df_recent = df.copy()
        
        if len(df_recent) < 20:  # 最低限必要なデータ
            return results
        
        # 各戦略の検出
        detectors = {
            StrategyType.BREAKOUT_NEW_HIGH.value: self._detect_breakout_new_high,
            StrategyType.PULLBACK_BUY.value: self._detect_pullback_buy,
            StrategyType.RETRY_NEW_HIGH.value: self._detect_retry_new_high,
            StrategyType.TREND_REVERSAL_UP.value: self._detect_trend_reversal_up,
            StrategyType.PULLBACK_SHORT.value: self._detect_pullback_short,
            StrategyType.BREAKOUT_NEW_LOW.value: self._detect_breakout_new_low,
            StrategyType.TREND_REVERSAL_DOWN.value: self._detect_trend_reversal_down,
            StrategyType.MOMENTUM_SHORT.value: self._detect_momentum_short,
        }
        
        for strategy_name, detector_func in detectors.items():
            try:
                signal = detector_func(df, df_recent, code, name, strategy_name)
                if signal and signal.score >= 40:  # 40%以上の接近のみ
                    results[strategy_name] = signal
            except Exception as e:
                # エラーは無視して次の戦略へ
                continue
        
        return results
    
    def _detect_breakout_new_high(
        self, 
        df_full: pd.DataFrame, 
        df_recent: pd.DataFrame,
        code: str, 
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        新高値ブレイク接近検出
        
        条件:
        ①前回の山の高値まで5%以内
        ②5日MAの3%以内
        ③直近5日で出来高増加傾向かつ1〜3か月平均の1.2倍以上
        ④5日MAを株価が上抜けしそう
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # 前回の山の高値を探す（ピーク検出）
        peaks = self._find_peaks(df_full['High'], window=10)
        if len(peaks) == 0:
            return None
        
        # 最新のピークの高値
        recent_peak_high = peaks.max()
        
        # 条件①: 高値まで5%以内
        diff_to_high = ((recent_peak_high - current_price) / recent_peak_high) * 100
        if 0 < diff_to_high <= 5:
            conditions_met.append(f"高値まで{diff_to_high:.1f}%")
        elif 5 < diff_to_high <= 10:
            conditions_pending.append(f"高値まで{diff_to_high:.1f}%（目標: 5%以内）")
        else:
            return None  # 遠すぎる
        
        # 条件②: 5日MAの3%以内
        if 'SMA_5' in last and pd.notna(last['SMA_5']):
            sma5_diff = abs(((current_price - last['SMA_5']) / last['SMA_5']) * 100)
            if sma5_diff <= 3:
                conditions_met.append(f"5日MA乖離{sma5_diff:.1f}%")
            else:
                conditions_pending.append(f"5日MA乖離{sma5_diff:.1f}%（目標: 3%以内）")
        else:
            conditions_pending.append("5日MA算出不可")
        
        # 条件③: 出来高増加傾向かつ平均の1.2倍以上
        if 'Volume' in df_recent.columns:
            avg_volume = df_full['Volume'].tail(60).mean()
            recent_volume = df_recent['Volume'].tail(5).mean()
            vol_increase = df_recent['Volume'].tail(5).is_monotonic_increasing or \
                          (df_recent['Volume'].iloc[-1] > df_recent['Volume'].iloc[-2])
            
            if vol_increase and recent_volume >= avg_volume * 1.2:
                conditions_met.append("出来高増加傾向かつ平均1.2倍以上")
            elif vol_increase or recent_volume >= avg_volume:
                conditions_pending.append("出来高条件部分達成")
            else:
                conditions_pending.append("出来高増加が必要")
        
        # 条件④: 5日MAを上抜けしそう
        if 'SMA_5' in last and pd.notna(last['SMA_5']):
            if current_price > last['SMA_5']:
                conditions_met.append("5日MA上抜け済み")
            elif current_price >= last['SMA_5'] * 0.98:
                conditions_met.append("5日MA上抜け間近")
            else:
                conditions_pending.append("5日MA上抜けまで距離あり")
        
        # スコア計算
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        # 残り日数推定
        estimated_days = self._estimate_days_to_signal(diff_to_high, score)
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=estimated_days,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _detect_pullback_buy(
        self,
        df_full: pd.DataFrame,
        df_recent: pd.DataFrame,
        code: str,
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        押し目買い接近検出
        
        条件:
        - 長期上昇トレンド中
        - 5日MAから-3%〜-5%乖離
        - RCI -50〜-80
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # 長期上昇トレンド確認
        if 'SMA_200' in last and 'SMA_75' in last:
            if pd.notna(last['SMA_200']) and len(df_full) > 20:
                sma200_trend_up = df_full['SMA_200'].iloc[-1] > df_full['SMA_200'].iloc[-20]
                sma75_trend_up = df_full['SMA_75'].iloc[-1] > df_full['SMA_75'].iloc[-20] if 'SMA_75' in df_full.columns else False
                
                if sma200_trend_up and sma75_trend_up:
                    conditions_met.append("長期上昇トレンド")
                elif sma200_trend_up or sma75_trend_up:
                    conditions_pending.append("トレンド確認中")
                else:
                    return None  # 下降トレンドでは対象外
        else:
            return None
        
        # 5日MA乖離率
        if 'SMA_5' in last and pd.notna(last['SMA_5']):
            divergence = ((current_price - last['SMA_5']) / last['SMA_5']) * 100
            if -5 <= divergence <= -3:
                conditions_met.append(f"5日MA乖離{divergence:.1f}%（適正範囲）")
            elif -7 <= divergence < -3:
                conditions_met.append(f"5日MA乖離{divergence:.1f}%")
            elif -3 < divergence <= 0:
                conditions_pending.append(f"5日MA乖離{divergence:.1f}%（更に下落待ち）")
            else:
                return None
        
        # RCI確認
        if 'RCI_9' in last and pd.notna(last['RCI_9']):
            rci = last['RCI_9']
            if -80 <= rci <= -50:
                conditions_met.append(f"RCI {rci:.0f}（売られすぎ圏）")
            elif -50 < rci <= -30:
                conditions_pending.append(f"RCI {rci:.0f}（売られすぎ接近）")
            elif rci < -80:
                conditions_met.append(f"RCI {rci:.0f}（極度売られすぎ）")
            else:
                conditions_pending.append(f"RCI {rci:.0f}（まだ高い）")
        
        # スコア計算
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        estimated_days = 3 if score >= 60 else 7
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=estimated_days,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _detect_retry_new_high(
        self,
        df_full: pd.DataFrame,
        df_recent: pd.DataFrame,
        code: str,
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        新高値リトライ接近検出
        
        条件:
        - 高値まで10%以内
        - OR: ゴールデンクロス間近
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # ピーク検出
        peaks = self._find_peaks(df_full['High'], window=10)
        if len(peaks) == 0:
            return None
        
        recent_peak_high = peaks.max()
        
        # 条件: 高値まで10%以内
        diff_to_high = ((recent_peak_high - current_price) / recent_peak_high) * 100
        if 0 < diff_to_high <= 10:
            conditions_met.append(f"高値まで{diff_to_high:.1f}%")
        elif 10 < diff_to_high <= 15:
            conditions_pending.append(f"高値まで{diff_to_high:.1f}%（目標: 10%以内）")
        else:
            return None
        
        # OR条件: ゴールデンクロス間近
        if 'SMA_5' in last and 'SMA_25' in last:
            if pd.notna(last['SMA_5']) and pd.notna(last['SMA_25']):
                ma_diff = ((last['SMA_5'] - last['SMA_25']) / last['SMA_25']) * 100
                if ma_diff > 0:
                    conditions_met.append("ゴールデンクロス済み")
                elif ma_diff >= -2:
                    conditions_met.append(f"GC間近（差{ma_diff:.1f}%）")
                else:
                    conditions_pending.append(f"5日MAと25日MAの差{ma_diff:.1f}%")
        
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        estimated_days = self._estimate_days_to_signal(diff_to_high, score)
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=estimated_days,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _detect_trend_reversal_up(
        self,
        df_full: pd.DataFrame,
        df_recent: pd.DataFrame,
        code: str,
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        下降トレンド反転接近検出
        
        条件:
        ①GC間近（5日MAと25日MAの差1%以内）
        ②RCI上昇傾向
        ③直近10日で過半数以上が陽線
        ④陽線の時のみ出来高が増加
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # 条件①: GC間近
        if 'SMA_5' in last and 'SMA_25' in last:
            if pd.notna(last['SMA_5']) and pd.notna(last['SMA_25']):
                ma_diff = ((last['SMA_5'] - last['SMA_25']) / last['SMA_25']) * 100
                if ma_diff > 0:
                    conditions_met.append("ゴールデンクロス済み")
                elif ma_diff >= -1:
                    conditions_met.append(f"GC間近（差{ma_diff:.1f}%）")
                elif ma_diff >= -3:
                    conditions_pending.append(f"GC接近中（差{ma_diff:.1f}%）")
                else:
                    return None
        else:
            return None
        
        # 条件②: RCI上昇傾向
        if 'RCI_9' in df_recent.columns:
            rci_recent = df_recent['RCI_9'].tail(5).dropna()
            if len(rci_recent) >= 2:
                if rci_recent.iloc[-1] > rci_recent.iloc[-2]:
                    conditions_met.append(f"RCI上昇傾向（{rci_recent.iloc[-1]:.0f}）")
                else:
                    conditions_pending.append("RCI上昇待ち")
        
        # 条件③: 直近10日で過半数以上が陽線
        bullish_count = (df_recent['Close'].tail(10) > df_recent['Open'].tail(10)).sum()
        if bullish_count >= 6:
            conditions_met.append(f"陽線{bullish_count}/10日")
        elif bullish_count >= 4:
            conditions_pending.append(f"陽線{bullish_count}/10日（目標: 6以上）")
        else:
            conditions_pending.append(f"陽線{bullish_count}/10日")
        
        # 条件④: 陽線の時のみ出来高増加
        recent_10 = df_recent.tail(10)
        bullish_days = recent_10[recent_10['Close'] > recent_10['Open']]
        if len(bullish_days) > 0:
            vol_increase_on_bullish = (bullish_days['Volume'] > bullish_days['Volume'].shift(1)).sum()
            if vol_increase_on_bullish >= len(bullish_days) * 0.5:
                conditions_met.append("陽線時出来高増加")
            else:
                conditions_pending.append("陽線時出来高増加待ち")
        
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        estimated_days = 3 if score >= 70 else 5
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=estimated_days,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _detect_pullback_short(
        self,
        df_full: pd.DataFrame,
        df_recent: pd.DataFrame,
        code: str,
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        押し目空売り接近検出
        
        条件:
        - 長期下降トレンド
        - 5日MAから+3%〜+5%乖離
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # 長期下降トレンド確認
        if 'SMA_200' in last and 'SMA_75' in last:
            if pd.notna(last['SMA_200']) and len(df_full) > 20:
                sma200_trend_down = df_full['SMA_200'].iloc[-1] < df_full['SMA_200'].iloc[-20]
                sma75_trend_down = df_full['SMA_75'].iloc[-1] < df_full['SMA_75'].iloc[-20] if 'SMA_75' in df_full.columns else False
                
                if sma200_trend_down and sma75_trend_down:
                    conditions_met.append("長期下降トレンド")
                elif sma200_trend_down or sma75_trend_down:
                    conditions_pending.append("トレンド確認中")
                else:
                    return None
        else:
            return None
        
        # 5日MA乖離率
        if 'SMA_5' in last and pd.notna(last['SMA_5']):
            divergence = ((current_price - last['SMA_5']) / last['SMA_5']) * 100
            if 3 <= divergence <= 5:
                conditions_met.append(f"5日MA乖離+{divergence:.1f}%（適正範囲）")
            elif 0 < divergence < 3:
                conditions_pending.append(f"5日MA乖離+{divergence:.1f}%（更に上昇待ち）")
            else:
                return None
        
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=5,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _detect_breakout_new_low(
        self,
        df_full: pd.DataFrame,
        df_recent: pd.DataFrame,
        code: str,
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        新安値ブレイク接近検出
        
        条件:
        ①前回の谷の安値まで5%以内
        ②当日陰線
        ③出来高が増加
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # トラフ（谷）検出
        troughs = self._find_troughs(df_full['Low'], window=10)
        if len(troughs) == 0:
            return None
        
        recent_trough_low = troughs.min()
        
        # 条件①: 安値まで5%以内
        diff_to_low = ((current_price - recent_trough_low) / recent_trough_low) * 100
        if 0 < diff_to_low <= 5:
            conditions_met.append(f"安値まで{diff_to_low:.1f}%")
        elif 5 < diff_to_low <= 10:
            conditions_pending.append(f"安値まで{diff_to_low:.1f}%（目標: 5%以内）")
        else:
            return None
        
        # 条件②: 当日陰線
        if last['Close'] < last['Open']:
            conditions_met.append("当日陰線")
        else:
            conditions_pending.append("陰線待ち")
        
        # 条件③: 出来高増加
        if len(df_recent) >= 2:
            if last['Volume'] > df_recent['Volume'].iloc[-2]:
                conditions_met.append("出来高増加")
            else:
                conditions_pending.append("出来高増加待ち")
        
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        estimated_days = self._estimate_days_to_signal(diff_to_low, score)
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=estimated_days,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _detect_trend_reversal_down(
        self,
        df_full: pd.DataFrame,
        df_recent: pd.DataFrame,
        code: str,
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        上昇トレンド反転接近検出
        
        条件:
        ①DC間近（5日MAと25日MAの差1%以内）
        ②RCI下降傾向
        ③直近10日で過半数以上が陰線
        ④陰線の時のみ出来高が増加
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # 条件①: DC間近
        if 'SMA_5' in last and 'SMA_25' in last:
            if pd.notna(last['SMA_5']) and pd.notna(last['SMA_25']):
                ma_diff = ((last['SMA_5'] - last['SMA_25']) / last['SMA_25']) * 100
                if ma_diff < 0:
                    conditions_met.append("デッドクロス済み")
                elif ma_diff <= 1:
                    conditions_met.append(f"DC間近（差{ma_diff:.1f}%）")
                elif ma_diff <= 3:
                    conditions_pending.append(f"DC接近中（差{ma_diff:.1f}%）")
                else:
                    return None
        else:
            return None
        
        # 条件②: RCI下降傾向
        if 'RCI_9' in df_recent.columns:
            rci_recent = df_recent['RCI_9'].tail(5).dropna()
            if len(rci_recent) >= 2:
                if rci_recent.iloc[-1] < rci_recent.iloc[-2]:
                    conditions_met.append(f"RCI下降傾向（{rci_recent.iloc[-1]:.0f}）")
                else:
                    conditions_pending.append("RCI下降待ち")
        
        # 条件③: 直近10日で過半数以上が陰線
        bearish_count = (df_recent['Close'].tail(10) < df_recent['Open'].tail(10)).sum()
        if bearish_count >= 6:
            conditions_met.append(f"陰線{bearish_count}/10日")
        elif bearish_count >= 4:
            conditions_pending.append(f"陰線{bearish_count}/10日（目標: 6以上）")
        else:
            conditions_pending.append(f"陰線{bearish_count}/10日")
        
        # 条件④: 陰線の時のみ出来高増加
        recent_10 = df_recent.tail(10)
        bearish_days = recent_10[recent_10['Close'] < recent_10['Open']]
        if len(bearish_days) > 0:
            vol_increase_on_bearish = (bearish_days['Volume'] > bearish_days['Volume'].shift(1)).sum()
            if vol_increase_on_bearish >= len(bearish_days) * 0.5:
                conditions_met.append("陰線時出来高増加")
            else:
                conditions_pending.append("陰線時出来高増加待ち")
        
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=3 if score >= 70 else 5,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _detect_momentum_short(
        self,
        df_full: pd.DataFrame,
        df_recent: pd.DataFrame,
        code: str,
        name: str,
        strategy: str
    ) -> Optional[ApproachingSignal]:
        """
        順張り空売り接近検出
        
        条件:
        - MA順序: 長期 > 中期 > 短期（短期が最も下）
        - 5日MA下抜け間近
        """
        conditions_met = []
        conditions_pending = []
        
        last = df_recent.iloc[-1]
        current_price = last['Close']
        
        # MA順序確認: 長期 > 中期 > 短期
        if 'SMA_200' in last and 'SMA_75' in last and 'SMA_25' in last and 'SMA_5' in last:
            sma200 = last['SMA_200']
            sma75 = last['SMA_75']
            sma25 = last['SMA_25']
            sma5 = last['SMA_5']
            
            if all(pd.notna(v) for v in [sma200, sma75, sma25, sma5]):
                if sma200 > sma75 > sma25 > sma5:
                    conditions_met.append("MA完全下降配列（200>75>25>5）")
                elif sma75 > sma25 > sma5:
                    conditions_met.append("MA下降配列（75>25>5）")
                elif sma25 > sma5:
                    conditions_pending.append("短期MA下位（25>5）、長期確認中")
                else:
                    return None
            else:
                return None
        else:
            return None
        
        # 5日MA下抜け間近
        if 'SMA_5' in last and pd.notna(last['SMA_5']):
            if current_price < last['SMA_5']:
                conditions_met.append("5日MA下抜け済み")
            elif current_price <= last['SMA_5'] * 1.02:
                conditions_met.append("5日MA下抜け間近")
            else:
                conditions_pending.append("5日MA下抜けまで距離あり")
        
        total_conditions = len(conditions_met) + len(conditions_pending)
        score = (len(conditions_met) / total_conditions * 100) if total_conditions > 0 else 0
        
        return ApproachingSignal(
            code=code,
            name=name,
            strategy=strategy,
            estimated_days=3 if score >= 70 else 7,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            score=score,
            current_price=current_price,
            last_updated=str(df_recent.index[-1])
        )
    
    def _find_peaks(self, series: pd.Series, window: int = 10) -> pd.Series:
        """山（ピーク）を検出"""
        rolling_max = series.rolling(window=window*2+1, center=True, min_periods=1).max()
        peaks = series[series == rolling_max]
        return peaks
    
    def _find_troughs(self, series: pd.Series, window: int = 10) -> pd.Series:
        """谷（トラフ）を検出"""
        rolling_min = series.rolling(window=window*2+1, center=True, min_periods=1).min()
        troughs = series[series == rolling_min]
        return troughs
    
    def _estimate_days_to_signal(self, distance_pct: float, score: float) -> int:
        """シグナルまでの推定日数を計算"""
        if score >= 80:
            return 1
        elif score >= 60:
            return 3
        elif distance_pct <= 2:
            return 2
        elif distance_pct <= 5:
            return 5
        else:
            return 7
