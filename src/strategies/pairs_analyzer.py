"""
ペアトレード（株式ロング・ショート）分析モジュール

相関係数（Correlation >= 0.85）と共和分（ADF検定 p-value < 0.05）を用いて
統計的に定常性のあるペアを抽出し、Ratio（比率）の乖離度（Zスコア）に基づいてエントリーシグナルを検出します。
"""
import logging
from typing import Dict, List, Any
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

logger = logging.getLogger(__name__)


class PairsAnalyzer:
    """ペアトレードのペア選定およびシグナル検出ロジック"""

    def __init__(
        self,
        correlation_threshold: float = 0.85,
        coint_threshold: float = 0.05,
        lookback_days: int = 251,
    ):
        """
        Args:
            correlation_threshold: 相関係数の閾値
            coint_threshold: 共和分テスト（ADF検定）のp値閾値
            lookback_days: 分析対象期間（過去N営業日）
        """
        self.correlation_threshold = correlation_threshold
        self.coint_threshold = coint_threshold
        self.lookback_days = lookback_days

    def analyze_pairs(
        self,
        stock_data: Dict[str, pd.DataFrame],
        stock_names: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        全銘柄から有効なペアを抽出し、直近の乖離状態を分析する

        Args:
            stock_data: {銘柄コード: 株価DataFrame} の辞書
            stock_names: {銘柄コード: 銘柄名} の辞書

        Returns:
            極上ペア（Zスコアが±3以上に乖離）のリスト
        """
        logger.info("ペアトレード分析を開始します")
        
        # 1. データの整合性チェックと過去251日終値のマージ
        close_dict = {}
        for code, df in stock_data.items():
            if df is None or len(df) < self.lookback_days:
                continue
            # 直近lookback_days分を抽出
            recent_df = df.tail(self.lookback_days)
            if 'Close' in recent_df.columns:
                close_dict[code] = recent_df['Close']

        if len(close_dict) < 2:
            logger.warning("分析に必要な十分なデータを持つ銘柄が足りません")
            return []

        # 終値DataFrameを作成 (インデックスは日付)
        prices_df = pd.DataFrame(close_dict)
        # 前後方向で補完し、欠損値がある行は削除（同一日付のデータを揃えるため）
        prices_df = prices_df.ffill().bfill().dropna(how='all')

        # 補完後にもlookback_days分確保されている銘柄のみ残す
        valid_cols = [col for col in prices_df.columns if prices_df[col].notna().sum() >= self.lookback_days]
        prices_df = prices_df[valid_cols].tail(self.lookback_days)
        
        if prices_df.shape[1] < 2:
            logger.warning("マージ後に有効な銘柄数が不足しています")
            return []

        logger.info(f"分析対象銘柄数: {prices_df.shape[1]}")

        # 2. リターン計算と相関係数行列の一括計算（ベクトル演算）
        returns_df = prices_df.pct_change().dropna()
        corr_matrix = returns_df.corr()

        # 相関フィルターを通過したペアのインデックスを抽出
        # 重複（A-BとB-A）および自己相関（A-A）を避けるため、上三角行列部分を対象にする
        cols = corr_matrix.columns
        candidate_pairs = []
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                corr = corr_matrix.iloc[i, j]
                if not np.isnan(corr) and corr >= self.correlation_threshold:
                    candidate_pairs.append((cols[i], cols[j], corr))

        logger.info(f"相関フィルター通過ペア数: {len(candidate_pairs)} (閾値: {self.correlation_threshold})")

        # 3. 共和分フィルター (ADF検定) およびシグナル計算
        results = []
        skipped_count = 0
        error_count = 0

        for code_a, code_b, corr in candidate_pairs:
            try:
                price_a = prices_df[code_a]
                price_b = prices_df[code_b]

                # Ratio（比率）計算
                ratio = price_a / price_b

                # 比率の無限大やNaNを除外
                if not np.isfinite(ratio).all() or ratio.isna().any():
                    skipped_count += 1
                    continue

                # ADF検定（単位根検定による定常性確認）
                # autolag='AIC' で最適なラグ数を自動決定
                adf_result = adfuller(ratio, autolag='AIC')
                p_value = adf_result[1]

                # 共和分フィルター (p-value < 0.05)
                if p_value >= self.coint_threshold:
                    continue

                # 統計量計算 (過去lookback_days全体)
                mean_ratio = ratio.mean()
                std_ratio = ratio.std()

                if std_ratio == 0:
                    continue

                # 直近（本日）のRatioおよびZスコア
                current_ratio = ratio.iloc[-1]
                z_score = (current_ratio - mean_ratio) / std_ratio

                # 直近価格
                price_a_curr = price_a.iloc[-1]
                price_b_curr = price_b.iloc[-1]

                # シグナル判定
                signal_type = None
                if z_score >= 3.0:
                    signal_type = "SHORT_A_LONG_B"  # A社高：Aをショート / Bをロング
                elif z_score <= -3.0:
                    signal_type = "LONG_A_SHORT_B"  # A社安：Aをロング / Bをショート

                # シグナルが点灯している（極上ペア）のみ結果に格納
                if signal_type:
                    results.append({
                        "stock_a": {
                            "code": code_a,
                            "name": stock_names.get(code_a, "不明"),
                            "price": float(price_a_curr),
                        },
                        "stock_b": {
                            "code": code_b,
                            "name": stock_names.get(code_b, "不明"),
                            "price": float(price_b_curr),
                        },
                        "correlation": float(corr),
                        "p_value": float(p_value),
                        "ratio_current": float(current_ratio),
                        "ratio_mean": float(mean_ratio),
                        "ratio_sigma": float(std_ratio),
                        "z_score": float(z_score),
                        "signal_type": signal_type,
                    })

            except Exception as e:
                error_count += 1
                # 大量のループでエラーログが溢れるのを防ぐため、デバッグレベルで出力
                logger.log(logging.DEBUG, f"ペア分析エラー ({code_a} - {code_b}): {e}")

        # Zスコアの絶対値の降順でソート（より乖離しているペアを上位に表示）
        results.sort(key=lambda x: abs(x["z_score"]), reverse=True)

        logger.info(
            f"分析完了: 極上ペア検出数: {len(results)} (スキップ: {skipped_count}, エラー: {error_count})"
        )
        return results
