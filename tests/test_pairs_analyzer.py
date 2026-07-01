import pytest
import numpy as np
import pandas as pd
from src.strategies.pairs_analyzer import PairsAnalyzer


def generate_coint_pair(
    seed: int = 42,
    n_days: int = 251,
    drift: bool = False,
    shock_at_end: float = 0.0,
):
    """
    テスト用の共和分（または非共和分）ペアデータを生成する
    
    Price_B = ランダムウォーク
    Ratio = 定常AR(1)プロセス または ドリフトする非定常プロセス
    Price_A = Price_B * Ratio
    """
    np.random.seed(seed)
    
    # 1. B社の価格（ランダムウォーク）
    price_b = 1000.0 + np.cumsum(np.random.normal(0, 10, n_days))
    price_b = np.clip(price_b, 100, 10000) # 負値を防ぐ
    
    # 2. Ratioの生成
    ratio = np.zeros(n_days)
    if drift:
        # ドリフトするランダムウォーク (非定常、共和分なし)
        ratio[0] = 1.5
        for t in range(1, n_days):
            ratio[t] = ratio[t - 1] + 0.01 + np.random.normal(0, 0.02)
    else:
        # 平均回帰AR(1)プロセス (定常、共和分あり)
        mean_ratio = 1.5
        rho = 0.7  # 平均回帰の強さ
        ratio[0] = mean_ratio
        for t in range(1, n_days):
            ratio[t] = mean_ratio + rho * (ratio[t - 1] - mean_ratio) + np.random.normal(0, 0.005)

            
    # 最終日にショック（異常乖離）を発生させる
    if shock_at_end != 0.0:
        ratio[-1] += shock_at_end

    price_a = price_b * ratio
    
    # DataFrame作成
    df_a = pd.DataFrame({'Close': price_a}, index=pd.date_range(end='2026-07-01', periods=n_days))
    df_b = pd.DataFrame({'Close': price_b}, index=pd.date_range(end='2026-07-01', periods=n_days))
    
    return df_a, df_b


def test_pairs_analyzer_success_short_signal():
    """正常系: 共和分関係があり、直近でRatioが急拡大(+3σ超)したペアが SHORT_A_LONG_B シグナルとして検出されること"""
    df_a, df_b = generate_coint_pair(seed=42, shock_at_end=0.05)  # A社を急騰させる


    stock_data = {"9901": df_a, "9902": df_b}
    stock_names = {"9901": "A社", "9902": "B社"}

    analyzer = PairsAnalyzer(correlation_threshold=0.80, coint_threshold=0.05, lookback_days=251)
    results = analyzer.analyze_pairs(stock_data, stock_names)

    # 検出結果の検証
    assert len(results) == 1
    res = results[0]
    assert res["stock_a"]["code"] == "9901"
    assert res["stock_b"]["code"] == "9902"
    assert res["correlation"] >= 0.80
    assert res["p_value"] < 0.05
    assert res["z_score"] >= 3.0
    assert res["signal_type"] == "SHORT_A_LONG_B"


def test_pairs_analyzer_success_long_signal():
    """正常系: 共和分関係があり、直近でRatioが急縮小(-3σ未満)したペアが LONG_A_SHORT_B シグナルとして検出されること"""
    df_a, df_b = generate_coint_pair(seed=42, shock_at_end=-0.05)  # A社を急落させる


    stock_data = {"9901": df_a, "9902": df_b}
    stock_names = {"9901": "A社", "9902": "B社"}

    analyzer = PairsAnalyzer(correlation_threshold=0.80, coint_threshold=0.05, lookback_days=251)
    results = analyzer.analyze_pairs(stock_data, stock_names)

    # 検出結果の検証
    assert len(results) == 1
    res = results[0]
    assert res["stock_a"]["code"] == "9901"
    assert res["stock_b"]["code"] == "9902"
    assert res["z_score"] <= -3.0
    assert res["signal_type"] == "LONG_A_SHORT_B"


def test_pairs_analyzer_no_signal_when_not_deviated():
    """正常系: 共和分関係はあるが、直近の乖離が小さいためシグナルが出ないこと"""
    df_a, df_b = generate_coint_pair(seed=42, shock_at_end=0.0)  # ショックなし

    stock_data = {"9901": df_a, "9902": df_b}
    stock_names = {"9901": "A社", "9902": "B社"}

    analyzer = PairsAnalyzer(correlation_threshold=0.80, coint_threshold=0.05, lookback_days=251)
    results = analyzer.analyze_pairs(stock_data, stock_names)

    # シグナルは出ていないはず
    assert len(results) == 0


def test_pairs_analyzer_filter_by_correlation():
    """相関フィルター: 相関係数が閾値未満のペアは除外されること"""
    # 完全に無関係な2つのランダムウォーク (相関が低い)
    np.random.seed(123)
    price_a = 1000.0 + np.cumsum(np.random.normal(0, 10, 251))
    price_b = 1000.0 + np.cumsum(np.random.normal(0, 10, 251))
    df_a = pd.DataFrame({'Close': price_a}, index=pd.date_range(end='2026-07-01', periods=251))
    df_b = pd.DataFrame({'Close': price_b}, index=pd.date_range(end='2026-07-01', periods=251))

    stock_data = {"9901": df_a, "9902": df_b}
    stock_names = {"9901": "A社", "9902": "B社"}

    # 相関閾値を高めに設定 (0.95)
    analyzer = PairsAnalyzer(correlation_threshold=0.95, coint_threshold=0.05, lookback_days=251)
    results = analyzer.analyze_pairs(stock_data, stock_names)

    assert len(results) == 0


def test_pairs_analyzer_filter_by_cointegration():
    """共和分フィルター: 比率が平均回帰しない（非定常）ペアは除外されること"""
    # 比率がドリフトする非共和分ペアを生成し、最後に無理やり大きなショックを与えてZスコアだけ引き上げる
    df_a, df_b = generate_coint_pair(seed=42, drift=True, shock_at_end=2.0)

    stock_data = {"9901": df_a, "9902": df_b}
    stock_names = {"9901": "A社", "9902": "B社"}

    analyzer = PairsAnalyzer(correlation_threshold=0.50, coint_threshold=0.05, lookback_days=251)
    results = analyzer.analyze_pairs(stock_data, stock_names)

    # 共和分テスト（ADF検定）で不合格となり、結果が空であること
    assert len(results) == 0


def test_pairs_analyzer_insufficient_data_skips():
    """データ不足銘柄のスキップ: データ数が251日未満の銘柄は安全にスキップされ、エラーにならないこと"""
    df_a, _ = generate_coint_pair(seed=42)
    # B社は100日分しかないデータ不足状態
    df_b_short = pd.DataFrame({'Close': np.random.normal(100, 5, 100)}, 
                              index=pd.date_range(end='2026-07-01', periods=100))

    stock_data = {"9901": df_a, "9902": df_b_short}
    stock_names = {"9901": "A社", "9902": "B社"}

    analyzer = PairsAnalyzer(correlation_threshold=0.50, coint_threshold=0.05, lookback_days=251)
    results = analyzer.analyze_pairs(stock_data, stock_names)

    # エラーで落ちずに安全に空リストが返ってくること
    assert len(results) == 0
