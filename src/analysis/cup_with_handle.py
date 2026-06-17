"""
カップウィズハンドル（CWH）パターンの検出・スコアリングモジュール
"""
import pandas as pd
import numpy as np
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple

@dataclass
class CupWithHandleResult:
    """CWH判定結果データクラス"""
    status: str            # "forming" | "formed" | "none"
    score: float           # 0-100 パターン品質スコア
    cup_depth_pct: float   # カップの深さ（%）
    cup_duration_days: int  # カップの期間（営業日）
    handle_depth_pct: float # ハンドルの深さ（%）  
    handle_duration_days: int # ハンドルの期間
    pivot_price: float     # ピボットポイント（ブレイクアウト価格）
    cup_left_high: float   # カップ左側の高値
    cup_bottom: float      # カップの底値
    cup_right_high: float  # カップ右側の高値
    volume_confirmation: bool # 出来高確認
    score_breakdown: dict = field(default_factory=dict)  # 各要素の得点内訳


class CupWithHandleDetector:
    """CWHパターンの検出およびスコアリングを行うクラス"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Args:
            config_path: 設定ファイルのパス
        """
        # デフォルトパラメータの設定
        self.cup_depth_min = 10.0
        self.cup_depth_max = 40.0
        self.cup_duration_min = 25
        self.cup_duration_max = 260
        self.handle_depth_ratio_max = 0.50
        self.handle_ideal_depth_min = 8.0
        self.handle_ideal_depth_max = 12.0
        self.handle_duration_min = 5
        self.handle_duration_max = 20
        self.u_shape_min_stay_ratio = 0.15
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                p = config.get('pattern_detection', {}).get('cup_with_handle', {})
                if p:
                    self.cup_depth_min = p.get('cup_depth_min', self.cup_depth_min)
                    self.cup_depth_max = p.get('cup_depth_max', self.cup_depth_max)
                    self.cup_duration_min = p.get('cup_duration_min', self.cup_duration_min)
                    self.cup_duration_max = p.get('cup_duration_max', self.cup_duration_max)
                    self.handle_depth_ratio_max = p.get('handle_depth_ratio_max', self.handle_depth_ratio_max)
                    self.handle_ideal_depth_min = p.get('handle_ideal_depth_min', self.handle_ideal_depth_min)
                    self.handle_ideal_depth_max = p.get('handle_ideal_depth_max', self.handle_ideal_depth_max)
                    self.handle_duration_min = p.get('handle_duration_min', self.handle_duration_min)
                    self.handle_duration_max = p.get('handle_duration_max', self.handle_duration_max)
                    self.u_shape_min_stay_ratio = p.get('u_shape_min_stay_ratio', self.u_shape_min_stay_ratio)
        except Exception:
            pass # 設定ファイルが無い/読み込めない場合はデフォルト値を使用

    def detect(self, df: pd.DataFrame) -> CupWithHandleResult:
        """
        最新行（最新日）におけるCWHパターンの検出
        """
        if len(df) == 0:
            return CupWithHandleResult("none", 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, False)
        return self.detect_at(df, len(df) - 1)

    def detect_at(self, df: pd.DataFrame, index: int) -> CupWithHandleResult:
        """
        指定インデックスの日におけるCWHパターンの検出・スコアリング
        """
        # 最低限必要な期間のチェック
        min_required = self.cup_duration_min + self.handle_duration_min
        if index < min_required or len(df) <= index:
            return CupWithHandleResult("none", 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, False)

        # 1. カップ左高値の探索
        # indexから遡り、過去の探索範囲内で最高値（High）を探す
        start_lookback = max(0, index - self.cup_duration_max - self.handle_duration_max)
        end_lookback = max(0, index - self.cup_duration_min - self.handle_duration_min)
        
        if start_lookback >= end_lookback:
            return CupWithHandleResult("none", 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, False)
            
        search_range_highs = df['High'].iloc[start_lookback:end_lookback]
        if len(search_range_highs) == 0:
            return CupWithHandleResult("none", 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, False)
            
        left_high = search_range_highs.max()
        left_high_idx = search_range_highs.idxmax()
        left_high_pos = df.index.get_loc(left_high_idx)

        # 2. カップ底の探索（左高値以降で、現在のハンドルの前の最安値）
        # 探索範囲: 左高値から、現在よりハンドルの最小期間手前まで
        end_bottom_search = max(left_high_pos + 10, index - self.handle_duration_min)
        if left_high_pos + 5 >= end_bottom_search:
            return CupWithHandleResult("none", 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, False)
            
        search_range_lows = df['Low'].iloc[left_high_pos:end_bottom_search]
        cup_bottom = search_range_lows.min()
        cup_bottom_idx = search_range_lows.idxmin()
        cup_bottom_pos = df.index.get_loc(cup_bottom_idx)

        # 3. カップ右高値の探索（底以降、現在より数日前までの最大値）
        # 右高値はハンドル期間の開始点となる
        start_right_search = cup_bottom_pos + 5
        end_right_search = index - 2 # 出来高やローソク足確認用に数日残す
        if start_right_search >= end_right_search:
            return CupWithHandleResult("none", 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, False)
            
        search_range_right = df['High'].iloc[start_right_search:end_right_search]
        right_high = search_range_right.max()
        right_high_idx = search_range_right.idxmax()
        right_high_pos = df.index.get_loc(right_high_idx)

        # 各種パラメータの計算
        cup_depth_pct = ((left_high - cup_bottom) / left_high) * 100
        cup_duration_days = right_high_pos - left_high_pos
        
        # カップ期間の検証
        if not (self.cup_duration_min <= cup_duration_days <= self.cup_duration_max):
            return CupWithHandleResult("none", 0.0, 0.0, 0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, False)

        # ハンドル期間の計算
        handle_duration_days = index - right_high_pos
        
        # ハンドル価格の検証
        handle_prices = df['Close'].iloc[right_high_pos:index+1]
        handle_low = df['Low'].iloc[right_high_pos:index+1].min()
        handle_depth_pct = ((right_high - handle_low) / right_high) * 100
        
        current_price = df['Close'].iloc[index]
        diff_from_right_high = ((right_high - current_price) / right_high) * 100

        # スコア計算
        score_breakdown = {}

        # 1) カップ深さのスコア（25点満点）
        if self.cup_depth_min <= cup_depth_pct <= self.cup_depth_max:
            if 15.0 <= cup_depth_pct <= 30.0:
                cup_depth_score = 25.0
            elif 10.0 <= cup_depth_pct < 15.0 or 30.0 < cup_depth_pct <= 35.0:
                cup_depth_score = 20.0
            else:
                cup_depth_score = 10.0
        else:
            cup_depth_score = 0.0
        score_breakdown['cup_depth'] = cup_depth_score

        # 2) カップ形状・U字度のスコア（20点満点）
        # 底付近（下落幅の下位20%のゾーン）に終値が滞在した日数の比率
        bottom_zone = cup_bottom + (left_high - cup_bottom) * 0.20
        cup_closes = df['Close'].iloc[left_high_pos:right_high_pos]
        stay_days = (cup_closes <= bottom_zone).sum()
        stay_ratio = stay_days / len(cup_closes) if len(cup_closes) > 0 else 0.0
        
        if stay_ratio >= 0.30:
            shape_score = 20.0
        elif stay_ratio >= 0.20:
            shape_score = 15.0
        elif stay_ratio >= 0.15:
            shape_score = 10.0
        else:
            shape_score = 0.0
        score_breakdown['cup_shape'] = shape_score

        # 3) 左右対称性のスコア（10点満点）
        sym_diff = abs(left_high - right_high) / left_high * 100
        if sym_diff <= 3.0:
            sym_score = 10.0
        elif sym_diff <= 5.0:
            sym_score = 7.0
        elif sym_diff <= 10.0:
            sym_score = 3.0
        else:
            sym_score = 0.0
        score_breakdown['symmetry'] = sym_score

        # 4) 出来高パターンのスコア（20点満点）
        # A) カップ底付近での出来高減少
        bottom_range = df['Volume'].iloc[max(0, cup_bottom_pos-5):min(len(df), cup_bottom_pos+6)]
        avg_volume_bottom = bottom_range.mean() if len(bottom_range) > 0 else 0.0
        
        # 過去25日平均出来高（底時点）
        df_vol_ma = df['Volume'].rolling(25).mean()
        ma_vol_at_bottom = df_vol_ma.iloc[cup_bottom_pos] if cup_bottom_pos < len(df_vol_ma) else 1.0
        if pd.isna(ma_vol_at_bottom) or ma_vol_at_bottom == 0:
            ma_vol_at_bottom = 1.0
            
        vol_dry_at_bottom = (avg_volume_bottom / ma_vol_at_bottom) <= 0.80

        # B) 右側上昇時の出来高増加
        right_climb_volumes = df['Volume'].iloc[cup_bottom_pos:right_high_pos]
        climb_volume_max = right_climb_volumes.max() if len(right_climb_volumes) > 0 else 0.0
        ma_vol_at_right = df_vol_ma.iloc[right_high_pos] if right_high_pos < len(df_vol_ma) else 1.0
        if pd.isna(ma_vol_at_right) or ma_vol_at_right == 0:
            ma_vol_at_right = 1.0
            
        vol_spike_at_right = (climb_volume_max / ma_vol_at_right) >= 1.30

        if vol_dry_at_bottom and vol_spike_at_right:
            volume_score = 20.0
        elif vol_dry_at_bottom or vol_spike_at_right:
            volume_score = 15.0
        else:
            volume_score = 5.0
        score_breakdown['volume_pattern'] = volume_score
        volume_confirmation = vol_dry_at_bottom or vol_spike_at_right

        # 5) ハンドル品質のスコア（25点満点）
        # ハンドルが深すぎる場合は0点
        if handle_depth_pct > cup_depth_pct * self.handle_depth_ratio_max or handle_depth_pct > 25.0:
            handle_score = 0.0
        else:
            # 出来高の減少傾向（右高値以降のハンドル期間）
            handle_volumes = df['Volume'].iloc[right_high_pos:index+1]
            avg_volume_handle = handle_volumes.mean() if len(handle_volumes) > 0 else 0.0
            
            # 右側上昇期の平均出来高と比較
            avg_volume_climb = right_climb_volumes.mean() if len(right_climb_volumes) > 0 else 1.0
            if avg_volume_climb == 0:
                avg_volume_climb = 1.0
                
            handle_vol_dry = (avg_volume_handle / avg_volume_climb) <= 0.85

            if self.handle_ideal_depth_min <= handle_depth_pct <= self.handle_ideal_depth_max:
                handle_score = 25.0 if handle_vol_dry else 20.0
            elif 5.0 <= handle_depth_pct <= 15.0:
                handle_score = 20.0 if handle_vol_dry else 15.0
            elif 15.0 < handle_depth_pct <= 20.0:
                handle_score = 10.0
            else:
                handle_score = 5.0
        score_breakdown['handle_quality'] = handle_score

        # 総合スコア（100点満点）
        total_score = sum(score_breakdown.values())

        # 状態（status）の決定
        # ハンドル期間が長すぎるか、ハンドルが深すぎる場合は none
        if not (self.handle_duration_min <= handle_duration_days <= self.handle_duration_max):
            status = "none"
        elif handle_score == 0.0 or total_score < 50.0:
            status = "none"
        else:
            # 形成済（formed）: ハンドルから持ち直し、ピボット（右高値）に接近
            # 形成間近（forming）: ハンドルの底付近での浅い調整中
            if diff_from_right_high <= 3.0:
                status = "formed"
            elif self.handle_ideal_depth_min <= diff_from_right_high <= self.handle_ideal_depth_max + 2.0:
                status = "forming"
            else:
                status = "none"

        # 状態が none の場合はスコアをリセット
        if status == "none":
            total_score = 0.0
            score_breakdown = {k: 0.0 for k in score_breakdown.keys()}

        return CupWithHandleResult(
            status=status,
            score=total_score,
            cup_depth_pct=cup_depth_pct,
            cup_duration_days=cup_duration_days,
            handle_depth_pct=handle_depth_pct,
            handle_duration_days=handle_duration_days,
            pivot_price=right_high,
            cup_left_high=left_high,
            cup_bottom=cup_bottom,
            cup_right_high=right_high,
            volume_confirmation=volume_confirmation,
            score_breakdown=score_breakdown
        )
