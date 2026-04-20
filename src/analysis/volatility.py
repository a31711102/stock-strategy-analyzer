"""
ボラティリティ分析モジュール

ATR（Average True Range）を用いたボラティリティの分類・傾向分析を行う。
- パーセンタイルベースのカテゴリ分類（高ボラ/中ボラ/低ボラ）
- レシオ方式の傾向分析（拡大/横ばい/縮小）
- ATR(10)×ATR(20)の組み合わせパターン判定
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


# ATR(10)×ATR(20)の組み合わせパターン定義
_VOLATILITY_PATTERNS: Dict[Tuple[str, str], str] = {
    ("high", "high"): "恒常高ボラ",
    ("high", "mid"): "短期急変",
    ("high", "low"): "異常変動",
    ("mid", "high"): "ボラ沈静化",
    ("mid", "mid"): "標準",
    ("mid", "low"): "やや活発化",
    ("low", "high"): "急収束型",
    ("low", "mid"): "直近静穏",
    ("low", "low"): "恒常低ボラ",
}


class VolatilityAnalyzer:
    """
    ボラティリティ分析クラス

    責務:
    - ATR%（正規化ATR）の計算
    - パーセンタイルベースのカテゴリ分類
    - レシオ方式の傾向分析
    - ATR(10)×ATR(20)の組み合わせパターン判定

    やらないこと:
    - ATR自体の計算（TechnicalIndicators.calculate_atrが担当）
    - データの永続化（ResultCacheが担当）
    - UIへの表示
    """

    # レシオ方式の傾向判定閾値（ユーザー承認済み: ±10%）
    TREND_EXPANDING_THRESHOLD = 1.10
    TREND_CONTRACTING_THRESHOLD = 0.90

    # レシオ計算のベースライン期間
    BASELINE_PERIOD = 14

    @staticmethod
    def calculate_atr_pct(df: pd.DataFrame, period: int) -> Optional[float]:
        """
        ATR%（正規化ATR）を計算

        ATR% = (ATR / 終値) × 100
        株価水準の異なる銘柄を公平に比較するための正規化処理。

        Args:
            df: ATR_{period}カラムを含むDataFrame
            period: ATR期間（10 or 20）

        Returns:
            直近のATR%値。計算不可の場合はNone。
        """
        atr_col = f'ATR_{period}'
        if atr_col not in df.columns:
            return None

        last = df.iloc[-1]
        atr_value = last.get(atr_col)
        close_value = last.get('Close')

        if pd.isna(atr_value) or pd.isna(close_value) or close_value == 0:
            return None

        return float((atr_value / close_value) * 100)

    @staticmethod
    def classify_volatility(atr_pct: Optional[float], p25: float, p75: float) -> str:
        """
        パーセンタイル閾値でボラティリティカテゴリを分類

        Args:
            atr_pct: ATR%の値
            p25: 25パーセンタイル閾値
            p75: 75パーセンタイル閾値

        Returns:
            "high", "mid", "low" のいずれか。分類不可の場合は空文字。
        """
        if atr_pct is None:
            return ""

        if atr_pct >= p75:
            return "high"
        elif atr_pct <= p25:
            return "low"
        else:
            return "mid"

    @staticmethod
    def get_volatility_pattern(category_10: str, category_20: str) -> str:
        """
        ATR(10)×ATR(20)の組み合わせパターン名を返す

        Args:
            category_10: ATR(10)のカテゴリ（"high"/"mid"/"low"）
            category_20: ATR(20)のカテゴリ（"high"/"mid"/"low"）

        Returns:
            パターン名（例: "恒常高ボラ", "短期急変"）。判定不可の場合は空文字。
        """
        if not category_10 or not category_20:
            return ""

        return _VOLATILITY_PATTERNS.get((category_10, category_20), "")

    @staticmethod
    def detect_trend(df: pd.DataFrame, short_period: int = 10) -> Tuple[str, float]:
        """
        レシオ方式でボラティリティ傾向を判定

        直近ATR(10)を、ATR(10)の14期間単純移動平均（ベースライン）と比較する。

        ATR_ratio = 直近ATR(10) / ATR(10)の14期間SMA
        - ratio > 1.10: 拡大（expanding）
        - ratio < 0.90: 縮小（contracting）
        - その他: 横ばい（stable）

        Args:
            df: ATR_{short_period}カラムを含むDataFrame
            short_period: 短期ATR期間（デフォルト: 10）

        Returns:
            (傾向文字列, ATRレシオ値) のタプル。
            計算不可の場合は ("", 0.0)。
        """
        atr_col = f'ATR_{short_period}'
        if atr_col not in df.columns:
            return ("", 0.0)

        atr_series = df[atr_col].dropna()

        # ベースライン計算に十分なデータが必要
        baseline_period = VolatilityAnalyzer.BASELINE_PERIOD
        if len(atr_series) < baseline_period:
            return ("", 0.0)

        # 直近のATR値
        current_atr = float(atr_series.iloc[-1])

        # ベースライン: ATRの直近14期間のSMA
        baseline = float(atr_series.tail(baseline_period).mean())

        # ゼロ除算防止
        if baseline == 0:
            return ("stable", 1.0)

        ratio = current_atr / baseline

        if ratio > VolatilityAnalyzer.TREND_EXPANDING_THRESHOLD:
            trend = "expanding"
        elif ratio < VolatilityAnalyzer.TREND_CONTRACTING_THRESHOLD:
            trend = "contracting"
        else:
            trend = "stable"

        return (trend, round(ratio, 3))

    @staticmethod
    def calculate_thresholds(all_atr_pcts: List[float]) -> Dict[str, float]:
        """
        全銘柄のATR%リストからパーセンタイル閾値を算出

        Args:
            all_atr_pcts: 全銘柄のATR%値のリスト（None/NaN除外済み前提）

        Returns:
            {"p25": float, "p75": float} の辞書。
            データ不足の場合は p25=0.0, p75=0.0 を返す。
        """
        valid = [v for v in all_atr_pcts if v is not None and not np.isnan(v)]

        if len(valid) < 4:
            logger.warning(f"ATR%の有効データが不足: {len(valid)}件")
            return {"p25": 0.0, "p75": 0.0}

        arr = np.array(valid)
        return {
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
        }

    @staticmethod
    def build_atr_info(
        df: pd.DataFrame,
        thresholds_10: Optional[Dict[str, float]] = None,
        thresholds_20: Optional[Dict[str, float]] = None,
    ) -> Dict:
        """
        1銘柄分のATR情報を一括生成

        Args:
            df: テクニカル指標計算済みのDataFrame
            thresholds_10: ATR(10)のパーセンタイル閾値 {"p25": float, "p75": float}
            thresholds_20: ATR(20)のパーセンタイル閾値 {"p25": float, "p75": float}

        Returns:
            ATR情報の辞書。以下のキーを含む:
            - atr_10, atr_20: ATR絶対値
            - atr_pct_10, atr_pct_20: ATR%
            - volatility_category_10, volatility_category_20: カテゴリ
            - volatility_pattern: 組み合わせパターン名
            - volatility_trend: 傾向
            - atr_ratio: ATRレシオ
        """
        result = {
            "atr_10": 0.0,
            "atr_20": 0.0,
            "atr_pct_10": 0.0,
            "atr_pct_20": 0.0,
            "volatility_category_10": "",
            "volatility_category_20": "",
            "volatility_pattern": "",
            "volatility_trend": "",
            "atr_ratio": 0.0,
        }

        if df is None or df.empty:
            return result

        # ATR絶対値
        last = df.iloc[-1]
        if 'ATR_10' in last and pd.notna(last['ATR_10']):
            result["atr_10"] = round(float(last['ATR_10']), 2)
        if 'ATR_20' in last and pd.notna(last['ATR_20']):
            result["atr_20"] = round(float(last['ATR_20']), 2)

        # ATR%
        atr_pct_10 = VolatilityAnalyzer.calculate_atr_pct(df, 10)
        atr_pct_20 = VolatilityAnalyzer.calculate_atr_pct(df, 20)

        if atr_pct_10 is not None:
            result["atr_pct_10"] = round(atr_pct_10, 3)
        if atr_pct_20 is not None:
            result["atr_pct_20"] = round(atr_pct_20, 3)

        # カテゴリ分類（閾値がある場合のみ）
        cat_10 = ""
        cat_20 = ""

        if thresholds_10 is not None:
            cat_10 = VolatilityAnalyzer.classify_volatility(
                atr_pct_10, thresholds_10["p25"], thresholds_10["p75"]
            )
            result["volatility_category_10"] = cat_10

        if thresholds_20 is not None:
            cat_20 = VolatilityAnalyzer.classify_volatility(
                atr_pct_20, thresholds_20["p25"], thresholds_20["p75"]
            )
            result["volatility_category_20"] = cat_20

        # 組み合わせパターン
        result["volatility_pattern"] = VolatilityAnalyzer.get_volatility_pattern(
            cat_10, cat_20
        )

        # 傾向分析（レシオ方式）
        trend, ratio = VolatilityAnalyzer.detect_trend(df, short_period=10)
        result["volatility_trend"] = trend
        result["atr_ratio"] = ratio

        return result
