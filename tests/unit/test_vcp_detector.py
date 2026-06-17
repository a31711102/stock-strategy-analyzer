"""
VCP (Volatility Contraction Pattern) 検出器のユニットテスト
"""
import pytest
import pandas as pd
import numpy as np

from src.analysis.vcp_detector import VCPDetector, VCPResult, Contraction

def _make_dummy_ohlcv(price_series, volume_series=None, ma_override=None):
    """価格系列からダミーのOHLCV DataFrameを作成する"""
    n = len(price_series)
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    df = pd.DataFrame({
        'Open': price_series,
        'High': price_series * 1.005,
        'Low': price_series * 0.995,
        'Close': price_series,
        'Volume': volume_series if volume_series is not None else np.full(n, 10000.0)
    }, index=dates)
    
    # トレンドテンプレート用の移動平均
    if ma_override:
        df['SMA_25'] = ma_override.get('SMA_25', df['Close'] * 0.95)
        df['SMA_75'] = ma_override.get('SMA_75', df['Close'] * 0.90)
        df['SMA_200'] = ma_override.get('SMA_200', df['Close'] * 0.80)
    else:
        # デフォルトはきれいな順行配列 (株価 > 25 > 75 > 200)
        df['SMA_25'] = df['Close'] * 0.95
        df['SMA_75'] = df['Close'] * 0.90
        df['SMA_200'] = df['Close'] * 0.85
        
    return df

def test_typical_3_contractions_vcp():
    """典型的3回収縮VCP（20% -> 10% -> 5%）が正しく検出され高スコアとなること"""
    # 300日分のデータを作成
    # 長期上昇トレンドののち、持ち合い（VCP）形成
    n = 250
    prices = np.zeros(n)
    
    # 0-100日: 上昇トレンド (800から1200)
    prices[:100] = np.linspace(800, 1200, 100)
    
    # 100-150日: 第1収縮 (1200から960へ20%下落後、1150へ戻す)
    prices[100:125] = np.linspace(1200, 960, 25)
    prices[125:150] = np.linspace(960, 1150, 25)
    
    # 150-190日: 第2収縮 (1150から1035へ10%下落後, 1120へ戻す)
    prices[150:170] = np.linspace(1150, 1035, 20)
    prices[170:190] = np.linspace(1035, 1120, 20)
    
    # 190-220日: 第3収縮 (1120から1064へ5%下落後, 1110へ戻す)
    prices[190:205] = np.linspace(1120, 1064, 15)
    prices[205:220] = np.linspace(1064, 1110, 15)
    
    # 220-250日: 最終微収縮またはピボット付近での保ち合い (1110から1090-1110範囲でタイトに推移)
    prices[220:] = np.linspace(1110, 1112, 30) # 横ばいで極めてタイト
    
    # 出来高: 段階的に減少し、最後は極小（枯れ）
    volumes = np.zeros(n)
    volumes[:100] = 15000.0  # 上昇中
    volumes[100:150] = np.linspace(12000, 8000, 50)  # 第1
    volumes[150:190] = np.linspace(8000, 5000, 40)   # 第2
    volumes[190:220] = np.linspace(5000, 3000, 30)   # 第3
    volumes[220:] = np.full(30, 2000.0)              # 最終出来高枯れ (平均の約30-40%水準)
    
    df = _make_dummy_ohlcv(prices, volumes)
    
    detector = VCPDetector()
    result = detector.detect(df)
    
    assert result.detected
    assert result.status == "detected"
    assert result.score >= 70
    assert result.num_contractions >= 3
    assert result.contractions[0].depth_pct == pytest.approx(20.0, abs=1.0)
    assert result.contractions[1].depth_pct == pytest.approx(10.0, abs=1.0)
    assert result.contractions[2].depth_pct == pytest.approx(5.0, abs=1.0)
    assert result.volume_dry_up
    assert result.trend_template_met


def test_vcp_potential_2_contractions():
    """収縮が2回のみ検出された場合、『potential（兆候あり）』と判定すること"""
    n = 200
    prices = np.zeros(n)
    prices[:100] = np.linspace(800, 1200, 100)
    
    # 第1収縮: 1200 -> 960 (20%) -> 1150
    prices[100:125] = np.linspace(1200, 960, 25)
    prices[125:150] = np.linspace(960, 1150, 25)
    
    # 第2収縮: 1150 -> 1035 (10%) -> 1120
    prices[150:175] = np.linspace(1150, 1035, 25)
    prices[175:] = np.linspace(1035, 1120, 25)
    
    df = _make_dummy_ohlcv(prices)
    
    detector = VCPDetector()
    result = detector.detect(df)
    
    # 収縮回数が2回のため、満たさないが potential 扱い
    assert result.status == "potential"
    assert 40 <= result.score < 70
    assert result.num_contractions == 2

def test_vcp_expanding_rejection():
    """ボラティリティが縮小せず拡大しているパターンはVCPとして拒絶（none）されること"""
    n = 200
    prices = np.zeros(n)
    prices[:100] = np.linspace(800, 1000, 100)
    
    # 第1収縮: 5% (1000 -> 950 -> 990)
    prices[100:125] = np.linspace(1000, 950, 25)
    prices[125:150] = np.linspace(950, 990, 25)
    
    # 第2収縮: 15% (990 -> 840 -> 960)
    prices[150:175] = np.linspace(990, 840, 25)
    prices[175:] = np.linspace(840, 960, 25)
    
    df = _make_dummy_ohlcv(prices)
    
    detector = VCPDetector()
    result = detector.detect(df)
    
    assert result.status == "none"
    assert result.score < 40

def test_vcp_trend_template_failure():
    """上昇トレンドのテンプレート条件を満たさない場合、スコアが大幅に減点され none になること"""
    n = 250
    prices = np.zeros(n)
    prices[:100] = np.linspace(800, 1200, 100)
    prices[100:125] = np.linspace(1200, 960, 25)
    prices[125:150] = np.linspace(960, 1150, 25)
    prices[150:170] = np.linspace(1150, 1035, 20)
    prices[170:190] = np.linspace(1035, 1120, 20)
    prices[190:205] = np.linspace(1120, 1064, 15)
    prices[205:220] = np.linspace(1064, 1110, 15)
    prices[220:] = np.linspace(1110, 1112, 30)
    
    # SMAを下降配列にオーバーライド (株価が移動平均より下など、弱い状態)
    ma_override = {
        'SMA_25': np.full(n, 1300.0), # 価格(1110)より上
        'SMA_75': np.full(n, 1350.0),
        'SMA_200': np.full(n, 1400.0)
    }
    
    df = _make_dummy_ohlcv(prices, ma_override=ma_override)
    
    detector = VCPDetector()
    result = detector.detect(df)
    
    assert not result.trend_template_met
    assert result.status == "none"
    assert result.score < 40
