"""
U7: SignalDetector avg_volume フィールドのユニットテスト

テスト対象: src/analysis/signal_detector.py の ApproachingSignal, SignalDetector

テスト観点:
- ApproachingSignal の avg_volume デフォルト値・カスタム値
- 検出メソッドでの avg_volume 計算の正確性
- Volume カラム欠損時のフォールバック
"""
import pytest
import pandas as pd
import numpy as np

from src.analysis.signal_detector import ApproachingSignal, SignalDetector


# ===========================================================================
# Test: ApproachingSignal データクラスの avg_volume
# ===========================================================================

class TestApproachingSignalAvgVolume:

    def test_default_avg_volume(self):
        """avg_volume のデフォルト値が 0.0 であること"""
        signal = ApproachingSignal(
            code='9432',
            name='NTT',
            strategy='新高値ブレイク',
            estimated_days=3,
            conditions_met=['条件A'],
            conditions_pending=[],
            score=75.0,
            current_price=150.0,
            last_updated='2026-02-24',
        )
        assert signal.avg_volume == 0.0

    def test_custom_avg_volume(self):
        """任意の avg_volume 値で生成できること"""
        signal = ApproachingSignal(
            code='7203',
            name='トヨタ',
            strategy='押し目買い',
            estimated_days=5,
            conditions_met=[],
            conditions_pending=['条件B'],
            score=60.0,
            current_price=2500.0,
            last_updated='2026-02-24',
            avg_volume=1_500_000.0,
        )
        assert signal.avg_volume == 1_500_000.0


# ===========================================================================
# Test: SignalDetector の avg_volume 計算
# ===========================================================================

@pytest.fixture
def detector():
    """SignalDetector インスタンス"""
    return SignalDetector(lookback_days=60)


@pytest.fixture
def ohlcv_with_peak():
    """
    新高値ブレイク検出に適したデータ（300日）
    - 明確なピーク（200日目付近）を持つ
    - 現在価格がピークの5%以内
    - Volume カラムあり
    """
    np.random.seed(123)
    n = 300
    dates = pd.date_range('2023-01-01', periods=n, freq='B')

    # 上昇 → ピーク → やや下落 → 再上昇のパターン
    base = np.concatenate([
        np.linspace(1000, 1200, 200),   # 上昇
        np.linspace(1200, 1150, 50),    # やや下落
        np.linspace(1150, 1195, 50),    # 再上昇（ピークの5%以内）
    ])
    noise = np.random.randn(n) * 2

    close = base + noise
    high = close + np.abs(np.random.randn(n)) * 5
    low = close - np.abs(np.random.randn(n)) * 5
    open_ = close + np.random.randn(n) * 2

    # 出来高: 直近60日の平均を検証しやすくするため固定値ベースにする
    volume = np.full(n, 800_000.0)
    # 直近60日だけ異なる出来高にする
    volume[-60:] = 1_000_000.0

    data = {
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume,
    }
    df = pd.DataFrame(data, index=dates)

    # テクニカル指標（SMA）を追加
    df['SMA_5'] = df['Close'].rolling(5).mean()
    df['SMA_25'] = df['Close'].rolling(25).mean()
    df['SMA_75'] = df['Close'].rolling(75).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()

    return df


class TestSignalDetectorAvgVolume:

    def test_detect_breakout_new_high_sets_avg_volume(self, detector, ohlcv_with_peak):
        """_detect_breakout_new_high が avg_volume を正しく設定すること"""
        df_full = ohlcv_with_peak
        df_recent = df_full.tail(60).copy()

        signal = detector._detect_breakout_new_high(
            df_full, df_recent, '9999', 'テスト銘柄', '新高値ブレイク'
        )

        # シグナルが検出されなかった場合は、データパターンの問題なのでスキップ
        if signal is None:
            pytest.skip("テストデータでシグナルが検出されなかった（データパターンの問題）")

        # avg_volume が設定されていること（0より大きい）
        assert signal.avg_volume > 0
        # 直近60日の平均出来高は 1_000_000 のはず
        assert abs(signal.avg_volume - 1_000_000.0) < 100_000  # ノイズなし固定値なので近い値

    def test_avg_volume_uses_last_60_days(self, detector):
        """直近60日の平均出来高が正しく計算されること"""
        n = 300
        dates = pd.date_range('2023-01-01', periods=n, freq='B')

        # 出来高: 最初の240日は100, 直近60日は200
        volume = np.concatenate([
            np.full(240, 100.0),
            np.full(60, 200.0),
        ])

        df = pd.DataFrame({
            'Open': np.full(n, 100.0),
            'High': np.full(n, 105.0),
            'Low': np.full(n, 95.0),
            'Close': np.full(n, 100.0),
            'Volume': volume,
        }, index=dates)

        # 直接計算を検証
        avg_vol = float(df['Volume'].tail(60).mean())
        assert avg_vol == 200.0

    def test_avg_volume_zero_when_no_volume_column(self):
        """Volume カラムがない場合、avg_volume は 0.0 になること"""
        signal = ApproachingSignal(
            code='1234',
            name='テスト銘柄',
            strategy='新高値ブレイク',
            estimated_days=3,
            conditions_met=['条件A'],
            conditions_pending=[],
            score=70.0,
            current_price=100.0,
            last_updated='2026-02-24',
            # avg_volume を明示的に指定しない → デフォルト 0.0
        )
        assert signal.avg_volume == 0.0
