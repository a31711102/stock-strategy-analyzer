"""
CWH (Cup with Handle) パターン検出器のユニットテスト
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.analysis.cup_with_handle import CupWithHandleDetector, CupWithHandleResult

def _make_dummy_ohlcv(price_series, volume_series=None):
    """価格系列からダミーのOHLCV DataFrameを作成する"""
    n = len(price_series)
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    df = pd.DataFrame({
        'Open': price_series,
        'High': price_series * 1.01,
        'Low': price_series * 0.99,
        'Close': price_series,
        'Volume': volume_series if volume_series is not None else np.full(n, 10000.0)
    }, index=dates)
    
    # テクニカル指標のダミーを適宜追加（移動平均など）
    df['SMA_5'] = df['Close'].rolling(5).mean()
    df['SMA_25'] = df['Close'].rolling(25).mean()
    df['SMA_75'] = df['Close'].rolling(75).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()
    return df

def test_typical_cup_with_handle():
    """典型的で教科書通りのCWHパターン（形成済）が正しく検出され高スコアとなること"""
    # 300日分のデータを作成
    # 0-100日: 上昇トレンド (1000から1200)
    # 100-150日: カップ左側下降 (1200から900、約25%下落)
    # 150-180日: カップ底で低迷（U字型、900付近で推移）
    # 180-230日: カップ右側上昇 (900から1180)
    # 230-245日: ハンドル形成（1180から1070へ約9.3%の調整）
    # 245-250日: ハンドルから少し上昇 (1070から1100)
    
    n = 240
    prices = np.zeros(n)
    
    # 0-100日: 上昇
    prices[:100] = np.linspace(1000, 1200, 100)
    # 100-150日: 下落
    prices[100:150] = np.linspace(1200, 900, 50)
    # 150-180日: 底（U字の平らな部分）
    prices[150:180] = np.full(30, 900) + np.sin(np.linspace(0, np.pi, 30)) * 10
    # 180-220日: 右側上昇（右高値を220日目に）
    prices[180:220] = np.linspace(900, 1180, 40)
    prices[220] = 1180
    # 220-232日: ハンドル調整 (12日)
    prices[220:232] = np.linspace(1180, 1070, 12)
    # 232-240日: 持ち直し (8日)
    prices[232:] = np.linspace(1070, 1175, 8)
    
    # 出来高: 底で枯れ、右側上昇で増加、ハンドルで再度枯れ
    volumes = np.full(n, 10000.0)
    volumes[100:150] = np.linspace(10000, 3000, 50)
    volumes[150:180] = np.full(30, 2000.0)  # 底での出来高枯れ
    volumes[180:220] = np.linspace(3000, 25000, 40) # 上昇時の出来高増
    volumes[220:232] = np.linspace(25000, 4000, 12) # ハンドル出来高枯れ
    volumes[232:] = np.linspace(4000, 15000, 8)

    
    df = _make_dummy_ohlcv(prices, volumes)
    
    detector = CupWithHandleDetector()
    result = detector.detect(df)
    
    assert result.status == "formed"
    assert result.score >= 80
    assert 20.0 <= result.cup_depth_pct <= 30.0
    assert 8.0 <= result.handle_depth_pct <= 12.0
    assert result.volume_confirmation


def test_cup_with_handle_forming():
    """カップ完成後の浅い調整（ハンドル形成開始）を『形成間近』と判定すること"""
    n = 240
    prices = np.zeros(n)
    
    # カップ形成までは典型的パターンと同じ
    prices[:100] = np.linspace(1000, 1200, 100)
    prices[100:150] = np.linspace(1200, 900, 50)
    prices[150:180] = np.full(30, 900)
    prices[180:230] = np.linspace(900, 1180, 50)
    # 230-240日: ハンドル形成の途中の下落（1180から1080へ約8.5%下落中）
    prices[230:] = np.linspace(1180, 1080, 10)
    
    volumes = np.full(n, 10000.0)
    volumes[150:180] = np.full(30, 2000.0) # 底
    volumes[180:230] = np.linspace(3000, 20000, 50) # 上昇
    volumes[230:] = np.linspace(20000, 5000, 10) # 出来高減少
    
    df = _make_dummy_ohlcv(prices, volumes)
    
    detector = CupWithHandleDetector()
    result = detector.detect(df)
    
    assert result.status == "forming"
    assert result.score >= 50

    assert 8.0 <= result.handle_depth_pct <= 12.0

def test_cwh_v_shape_rejection():
    """底の平らな期間がなく、V字型で戻したパターンはCWHとして拒絶（none）されること"""
    n = 200
    prices = np.zeros(n)
    
    # 0-100日: 横ばい
    prices[:100] = np.full(100, 1000.0)
    # 100-140日: V字下降
    prices[100:140] = np.linspace(1000, 800, 40)
    # 140-180日: V字上昇（底でのもみ合いが全くない）
    prices[140:180] = np.linspace(800, 990, 40)
    # 180-195日: ハンドル調整
    prices[180:195] = np.linspace(990, 900, 15)
    prices[195:] = np.linspace(900, 920, 5)
    
    df = _make_dummy_ohlcv(prices)
    
    detector = CupWithHandleDetector()
    result = detector.detect(df)
    
    # V字型形状のためCWHとしては不合格
    assert result.status == "none"
    assert result.score < 50

def test_cwh_invalid_depths():
    """カップが深すぎる(>40%)、または浅すぎる(<10%)場合に CWH と判定されないこと"""
    detector = CupWithHandleDetector()
    
    # ケースA: 深すぎる (50%下落)
    n = 260
    prices_deep = np.zeros(n)
    prices_deep[:100] = np.linspace(1000, 1200, 100)
    prices_deep[100:150] = np.linspace(1200, 600, 50)  # 50%下落
    prices_deep[150:180] = np.full(30, 600)
    prices_deep[180:230] = np.linspace(600, 1180, 50)
    prices_deep[230:245] = np.linspace(1180, 1070, 15)
    prices_deep[245:] = np.linspace(1070, 1100, 15)
    
    df_deep = _make_dummy_ohlcv(prices_deep)
    result_deep = detector.detect(df_deep)
    assert result_deep.status == "none"
    
    # ケースB: 浅すぎる (5%下落)
    prices_shallow = np.zeros(n)
    prices_shallow[:100] = np.linspace(1000, 1200, 100)
    prices_shallow[100:150] = np.linspace(1200, 1140, 50) # 5%下落
    prices_shallow[150:180] = np.full(30, 1140)
    prices_shallow[180:230] = np.linspace(1140, 1195, 50)
    prices_shallow[230:245] = np.linspace(1195, 1180, 15)
    prices_shallow[245:] = np.linspace(1180, 1185, 15)
    
    df_shallow = _make_dummy_ohlcv(prices_shallow)
    result_shallow = detector.detect(df_shallow)
    assert result_shallow.status == "none"
