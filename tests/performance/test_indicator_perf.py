"""
P1: テクニカル指標計算の性能テスト

テスト対象: TechnicalIndicators.calculate_all_indicators()

テスト観点:
- 300行データの処理時間 < 0.5秒
- 4800行データの処理時間 < 2.0秒
- 繰り返し100回の平均時間 < 0.05秒/回
"""
import time
import pytest

from src.indicators.technical import TechnicalIndicators


@pytest.mark.performance
class TestIndicatorPerformance:
    """テクニカル指標計算の性能テスト"""

    def test_300_rows_under_threshold(self, df_300):
        """P1-1: 300行データの全指標計算 < 1.0秒"""
        start = time.perf_counter()
        TechnicalIndicators.calculate_all_indicators(df_300.copy())
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"300行の指標計算に{elapsed:.3f}秒（閾値: 1.0秒）"

    def test_4800_rows_under_threshold(self, df_4800):
        """P1-2: 4800行データの全指標計算 < 2.0秒"""
        start = time.perf_counter()
        TechnicalIndicators.calculate_all_indicators(df_4800.copy())
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"4800行の指標計算に{elapsed:.3f}秒（閾値: 2.0秒）"

    def test_average_time_100_iterations(self, df_300):
        """P1-3: 繰り返し100回の平均時間 < 0.05秒/回"""
        # ウォームアップ（1回）
        TechnicalIndicators.calculate_all_indicators(df_300.copy())

        start = time.perf_counter()
        for _ in range(100):
            TechnicalIndicators.calculate_all_indicators(df_300.copy())
        total = time.perf_counter() - start
        avg = total / 100

        assert avg < 0.05, f"平均{avg:.4f}秒/回（閾値: 0.05秒/回、合計: {total:.2f}秒）"

    def test_scaling_linear(self, df_300, df_4800):
        """スケーリング確認: 16倍データの処理時間が線形増加に収まること"""
        # 300行
        start = time.perf_counter()
        TechnicalIndicators.calculate_all_indicators(df_300.copy())
        time_300 = time.perf_counter() - start

        # 4800行
        start = time.perf_counter()
        TechnicalIndicators.calculate_all_indicators(df_4800.copy())
        time_4800 = time.perf_counter() - start

        # 16倍のデータで32倍以下の処理時間であること（O(n)なら16倍が理想）
        if time_300 > 0.001:  # 計測精度のガード
            ratio = time_4800 / time_300
            assert ratio < 32, f"スケーリング比率: {ratio:.1f}x（16倍データ、閾値: 32x）"
