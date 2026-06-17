"""
VCP（Volatility Contraction Pattern）パターンの検出・スコアリングモジュール
"""
import pandas as pd
import numpy as np
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

@dataclass
class Contraction:
    """個別の収縮データクラス"""
    high: float            # 収縮の高値
    low: float             # 収縮の安値
    depth_pct: float       # 収縮の深さ（%）
    duration_days: int     # 収縮の期間
    volume_avg: float      # 期間中の平均出来高
    high_idx: Any = None   # 高値の日付（またはインデックス）
    low_idx: Any = None    # 安値の日付


@dataclass
class VCPResult:
    """VCP判定結果データクラス"""
    detected: bool         # VCPが検出されたか
    status: str            # "detected" | "potential" | "none"
    score: float           # 0-100 パターン品質スコア
    num_contractions: int  # 収縮の回数
    contractions: List[Contraction]  # 各収縮の詳細
    pivot_price: float     # ピボットポイント
    tightness_ratio: float # 最終収縮の絞り込み度合い
    volume_dry_up: bool    # 出来高枯れの確認
    trend_template_met: bool # トレンドテンプレート条件
    score_breakdown: dict = field(default_factory=dict)  # 各要素の得点内訳


class VCPDetector:
    """VCPパターンの検出およびスコアリングを行うクラス"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Args:
            config_path: 設定ファイルのパス
        """
        # デフォルトパラメータの設定
        self.min_contractions = 3
        self.contraction_shrink_threshold = 0.80
        self.volume_dry_up_threshold = 0.80
        self.trend_template_ma = [25, 75, 200]
        self.max_distance_from_52w_high = 25.0
        self.min_distance_from_52w_low = 30.0
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                p = config.get('pattern_detection', {}).get('vcp', {})
                if p:
                    self.min_contractions = p.get('min_contractions', self.min_contractions)
                    self.contraction_shrink_threshold = p.get('contraction_shrink_threshold', self.contraction_shrink_threshold)
                    self.volume_dry_up_threshold = p.get('volume_dry_up_threshold', self.volume_dry_up_threshold)
                    self.trend_template_ma = p.get('trend_template_ma', self.trend_template_ma)
                    self.max_distance_from_52w_high = p.get('max_distance_from_52w_high', self.max_distance_from_52w_high)
                    self.min_distance_from_52w_low = p.get('min_distance_from_52w_low', self.min_distance_from_52w_low)
        except Exception:
            pass # 設定ファイルが無い/読み込めない場合はデフォルト値を使用

    def detect(self, df: pd.DataFrame) -> VCPResult:
        """
        最新行（最新日）におけるVCPパターンの検出
        """
        if len(df) == 0:
            return VCPResult(False, "none", 0.0, 0, [], 0.0, 0.0, False, False)
        return self.detect_at(df, len(df) - 1)

    def detect_at(self, df: pd.DataFrame, index: int) -> VCPResult:
        """
        指定インデックスの日におけるVCPパターンの検出・スコアリング
        """
        # 最低限必要な期間のチェック
        if index < 120 or len(df) <= index:
            return VCPResult(False, "none", 0.0, 0, [], 0.0, 0.0, False, False)

        # 1. トレンドテンプレートの判定
        current_price = df['Close'].iloc[index]
        trend_template_met = False
        trend_score = 0.0

        has_ma = all(f'SMA_{p}' in df.columns for p in self.trend_template_ma)
        if has_ma:
            ma25 = df['SMA_25'].iloc[index]
            ma75 = df['SMA_75'].iloc[index]
            ma200 = df['SMA_200'].iloc[index]
            
            # MAの並び順 (株価 > 25 > 75 > 200)
            ma_ordered = current_price > ma25 > ma75 > ma200
            
            # 200日MAが上向き
            ma200_up = False
            if index >= 20:
                ma200_up = ma200 >= df['SMA_200'].iloc[index - 20]
            
            # 52週（260営業日）高値/安値
            lookback_52w = min(260, index + 1)
            high_52w = df['High'].iloc[index - lookback_52w + 1:index + 1].max()
            low_52w = df['Low'].iloc[index - lookback_52w + 1:index + 1].min()
            
            # 高値からの乖離率 (25%以内)
            dist_high = ((high_52w - current_price) / high_52w) * 100
            dist_high_ok = dist_high <= self.max_distance_from_52w_high
            
            # 安値からの上昇率 (30%以上)
            dist_low = ((current_price - low_52w) / low_52w) * 100
            dist_low_ok = dist_low >= self.min_distance_from_52w_low
            
            trend_template_met = ma_ordered and ma200_up and dist_high_ok and dist_low_ok
            
            # 配点 (20点満点)
            if trend_template_met:
                trend_score = 20.0
            elif ma_ordered and ma200_up:
                trend_score = 15.0
            elif ma_ordered:
                trend_score = 10.0
            else:
                trend_score = 0.0

        # 2. 収縮（Contraction）の検出
        # 直近200営業日のスイングハイ/ローを検出して収縮ウェーブを作成
        lookback_period = 200
        start_idx = max(0, index - lookback_period)
        sub_df = df.iloc[start_idx:index + 1]
        
        # スイングハイ・ローを検出（窓幅5日）
        highs_mask = sub_df['High'] == sub_df['High'].rolling(11, center=True, min_periods=1).max()
        lows_mask = sub_df['Low'] == sub_df['Low'].rolling(11, center=True, min_periods=1).min()
        
        peaks = [] # (index, price)
        troughs = []
        
        for idx, is_high in highs_mask.items():
            if is_high:
                peaks.append((idx, df.loc[idx, 'High']))
        for idx, is_low in lows_mask.items():
            if is_low:
                troughs.append((idx, df.loc[idx, 'Low']))
                
        # 時系列順にマージして交互に並べる
        all_points = sorted(peaks + troughs, key=lambda x: x[0])
        
        # 高値 -> 安値のペアを作成して収縮幅を算出
        contractions: List[Contraction] = []
        
        # 簡易的に、高値のあとにくる安値を探し、その間の最大下落幅を収縮とする
        temp_high = None
        temp_high_idx = None
        
        for pt in all_points:
            pt_idx, pt_price = pt
            # 出来高の移動平均などを取得しておく
            pos = df.index.get_loc(pt_idx)
            
            # 高値の特定
            if pt in peaks:
                temp_high = pt_price
                temp_high_idx = pt_idx
            # 高値のあとの安値を特定
            elif pt in troughs and temp_high is not None:
                low_idx = pt_idx
                low_price = pt_price
                
                # 高値と安値の位置
                h_pos = df.index.get_loc(temp_high_idx)
                l_pos = df.index.get_loc(low_idx)
                
                if l_pos > h_pos:
                    depth = ((temp_high - low_price) / temp_high) * 100
                    duration = l_pos - h_pos
                    
                    # 期間中の平均出来高
                    vol_slice = df['Volume'].iloc[h_pos:l_pos+1]
                    vol_avg = vol_slice.mean() if len(vol_slice) > 0 else 0.0
                    
                    contractions.append(Contraction(
                        high=temp_high,
                        low=low_price,
                        depth_pct=depth,
                        duration_days=duration,
                        volume_avg=vol_avg,
                        high_idx=temp_high_idx,
                        low_idx=low_idx
                    ))
                    # ペアを作成したらリセット
                    temp_high = None

        # 収縮を直近から順に見て、縮小傾向にある部分を抽出
        valid_contractions = []
        
        # 深さが1.5%未満の微小なブレは除外
        filtered_contractions = [c for c in contractions if c.depth_pct >= 1.5]
        
        if len(filtered_contractions) >= 2:
            # 時系列の最後から遡って、前回の収縮幅より小さくなっている連続部分を特定
            # 例: [20%, 12%, 6%] -> 段階的に縮小している
            # 逆向きに見ていき、後ろが前より小さくなっている（後ろ <= 前 * threshold）
            temp_list = []
            last_c = filtered_contractions[-1]
            temp_list.append(last_c)
            
            for c in reversed(filtered_contractions[:-1]):
                if last_c.depth_pct <= c.depth_pct * self.contraction_shrink_threshold:
                    temp_list.append(c)
                    last_c = c
                else:
                    # 縮小傾向が途切れたら終了
                    break
            valid_contractions = list(reversed(temp_list))
            
        num_contractions = len(valid_contractions)
        pivot_price = valid_contractions[-1].high if num_contractions > 0 else current_price

        # スコア計算
        score_breakdown = {}
        score_breakdown['trend_template'] = trend_score

        # 1) 収縮回数のスコア（15点満点）
        if num_contractions >= 5:
            count_score = 15.0
        elif num_contractions == 4:
            count_score = 12.0
        elif num_contractions == 3:
            count_score = 8.0
        else:
            count_score = 0.0
        score_breakdown['num_contractions'] = count_score

        # 2) 収縮の縮小率のスコア（30点満点）
        shrink_score = 0.0
        if num_contractions >= 2:
            # 各収縮が前回の何倍になっているか
            ratios = []
            for i in range(1, num_contractions):
                ratios.append(valid_contractions[i].depth_pct / valid_contractions[i-1].depth_pct)
            max_ratio = max(ratios) if ratios else 1.0
            
            if max_ratio <= 0.50:  # 全て半減以下 (Minerviniルール)
                shrink_score = 30.0
            elif max_ratio <= 0.65:
                shrink_score = 20.0
            elif max_ratio <= self.contraction_shrink_threshold:
                shrink_score = 10.0
        score_breakdown['shrink_ratio'] = shrink_score

        # 3) 出来高枯れのスコア（25点満点）
        # 最終収縮付近（直近10営業日）の平均出来高
        final_vol_slice = df['Volume'].iloc[max(0, index-9):index+1]
        avg_vol_final = final_vol_slice.mean() if len(final_vol_slice) > 0 else 0.0
        
        # 過去60日平均出来高
        avg_vol_60 = df['Volume'].iloc[max(0, index-60):index+1].mean()
        if avg_vol_60 == 0:
            avg_vol_60 = 1.0
            
        dry_up_ratio = avg_vol_final / avg_vol_60
        volume_dry_up = dry_up_ratio <= self.volume_dry_up_threshold

        
        if dry_up_ratio <= 0.50:
            vol_score = 25.0
        elif dry_up_ratio <= 0.60:
            vol_score = 20.0
        elif dry_up_ratio <= 0.70:
            vol_score = 15.0
        elif dry_up_ratio <= 0.80:
            vol_score = 5.0
        else:
            vol_score = 0.0
        score_breakdown['volume_dry_up'] = vol_score

        # 4) ピボット近接度のスコア（10点満点）
        dist_pivot = abs((pivot_price - current_price) / pivot_price) * 100 if pivot_price > 0 else 100.0
        if dist_pivot <= 2.0:
            pivot_score = 10.0
        elif dist_pivot <= 5.0:
            pivot_score = 7.0
        elif dist_pivot <= 10.0:
            pivot_score = 3.0
        else:
            pivot_score = 0.0
        score_breakdown['pivot_proximity'] = pivot_score

        # 総合スコア
        total_score = sum(score_breakdown.values())

        # 判定ステータス
        # トレンドが壊れているか、収縮が2回未満の場合は none
        if num_contractions < 2 or trend_score == 0.0:
            status = "none"
        else:
            if num_contractions < self.min_contractions:
                # 2回収縮の場合
                if total_score >= 40.0:
                    status = "potential"
                else:
                    status = "none"
            else:
                # 3回以上収縮の場合
                if total_score >= 70.0:
                    status = "detected"
                elif total_score >= 40.0:
                    status = "potential"
                else:
                    status = "none"

        detected = status != "none"
        tightness_ratio = valid_contractions[-1].depth_pct if num_contractions > 0 else 0.0

        # 状態が none の場合はスコアをリセット
        if status == "none":
            total_score = 0.0
            score_breakdown = {k: 0.0 for k in score_breakdown.keys()}

        return VCPResult(
            detected=detected,
            status=status,
            score=total_score,
            num_contractions=num_contractions,
            contractions=valid_contractions,
            pivot_price=pivot_price,
            tightness_ratio=tightness_ratio,
            volume_dry_up=volume_dry_up,
            trend_template_met=trend_template_met,
            score_breakdown=score_breakdown
        )
