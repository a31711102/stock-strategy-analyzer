"""
ボラティリティ乖離スクリーナー: 統合パイプライン

三段階フィルタリングを統合し、最終的な ScreenerResult リストを生成する。

Stage1: 流動性・需給フィルタ（全銘柄 → ~1500銘柄）
Stage2: ボラティリティ評価（→ RVR上位20銘柄）
Stage3: ターゲット計算・ポジションサイジング・トレンド判定

責務:
- 各ステージの実行順序制御
- 銘柄名の解決
- 結果の整形

やらないこと:
- データ取得（呼び出し元がstock_indicatorsを渡す）
- 結果の永続化（ResultCacheが担当）
"""
import logging
from typing import Optional
from datetime import datetime

from src.screener.liquidity_filter import LiquidityFilter, LiquidityFilterParams
from src.screener.volatility_evaluator import VolatilityEvaluator, VolatilityEvalParams
from src.screener.target_calculator import TargetCalculator, ScreenerResult
from src.screener.trend_judge import TrendJudge
from src.screener import config

import pandas as pd

logger = logging.getLogger(__name__)


class ScreenerPipeline:
    """
    ボラティリティ乖離スクリーナーの統合パイプライン

    使い方:
        pipeline = ScreenerPipeline()
        results = pipeline.run(stock_indicators, stock_names)
    """

    def __init__(
        self,
        risk_jpy: int = config.DEFAULT_RISK_JPY,
        min_norm_atr: float = config.MIN_NORM_ATR,
        top_n: int = config.TOP_N,
        liquidity_params: Optional[LiquidityFilterParams] = None,
    ):
        """
        Args:
            risk_jpy: 許容損失額（円）
            min_norm_atr: Norm_ATR最小値（%）。市場ボラに応じて調整可能。
            top_n: 上位N銘柄を選定
            liquidity_params: 流動性フィルタパラメータ（テスト用注入）
        """
        self.liquidity_filter = LiquidityFilter(params=liquidity_params)
        self.volatility_evaluator = VolatilityEvaluator(
            params=VolatilityEvalParams(min_norm_atr=min_norm_atr, top_n=top_n)
        )
        self.target_calculator = TargetCalculator(risk_jpy=risk_jpy)
        self.trend_judge = TrendJudge()

    def run(
        self,
        stock_indicators: dict[str, pd.DataFrame],
        stock_names: dict[str, str],
    ) -> dict[str, list[ScreenerResult]]:
        """
        三段階フィルタリングパイプラインを実行

        Args:
            stock_indicators: {銘柄コード: 指標計算済みDataFrame} の辞書
            stock_names: {銘柄コード: 銘柄名} の辞書

        Returns:
            'dynamic' と 'large_cap' のキーごとに ScreenerResult のリストを格納した辞書。
        """
        total_count = len(stock_indicators)
        logger.info(f"=== ボラティリティスクリーナー開始: {total_count}銘柄 ===")

        # --- Stage 1: 流動性・需給フィルタ ---
        stage1_codes = self.liquidity_filter.apply(stock_indicators)
        if not stage1_codes:
            logger.warning("Stage1: 流動性フィルタを通過する銘柄がありません")
            return {'dynamic': [], 'large_cap': []}

        # --- Stage 2: ボラティリティ評価 ---
        vol_scores = self.volatility_evaluator.evaluate(
            stage1_codes, stock_indicators
        )
        if not vol_scores:
            logger.warning("Stage2: ボラティリティ条件を満たす銘柄がありません")
            return {'dynamic': [], 'large_cap': []}

        # --- 分割＆ランキング ---
        dynamic_scores = sorted(vol_scores, key=lambda s: s.rvr, reverse=True)[:self.volatility_evaluator.params.top_n]
        
        # 大型株フィルタ: 売買代金 = Close * Volume_MA_5 >= 10,000,000,000 (100億円)
        large_cap_scores = []
        for vs in vol_scores:
            df = stock_indicators.get(vs.code)
            if df is not None:
                vol_5 = df.iloc[-1].get('Volume_MA_5', 0)
                if pd.notna(vol_5) and vs.close * vol_5 >= 10_000_000_000:
                    large_cap_scores.append(vs)
                    
        # 大型株の並び順はNorm_ATR降順
        large_cap_scores = sorted(large_cap_scores, key=lambda s: s.norm_atr, reverse=True)[:self.volatility_evaluator.params.top_n]

        # --- Stage 3: ターゲット計算 ---
        def calc_targets(scores):
            results = []
            for rank, vs in enumerate(scores, 1):
                df = stock_indicators.get(vs.code)
                if df is None:
                    continue
                name = stock_names.get(vs.code, vs.code)
                status = self.trend_judge.judge(df)
                result = self.target_calculator.calculate(
                    vol_score=vs, df=df, name=name, rank=rank, status=status
                )
                if result:
                    results.append(result)
            return results

        dynamic_results = calc_targets(dynamic_scores)
        large_cap_results = calc_targets(large_cap_scores)

        logger.info(
            f"=== スクリーナー完了: "
            f"{total_count}銘柄 → Stage1:{len(stage1_codes)} → "
            f"Stage2:{len(vol_scores)} → 最終 Dynamic:{len(dynamic_results)}, LargeCap:{len(large_cap_results)} ==="
        )

        return {
            'dynamic': dynamic_results,
            'large_cap': large_cap_results
        }

    def to_json_dict(self, results: dict[str, list[ScreenerResult]]) -> dict:
        """
        結果をJSON保存用の辞書に変換

        Args:
            results: ScreenerPipeline.run() が返す辞書

        Returns:
            JSON保存用の辞書
        """
        return {
            'generated_at': datetime.now().isoformat(),
            'parameters': {
                'min_norm_atr': self.volatility_evaluator.params.min_norm_atr,
                'min_avg_volume': self.liquidity_filter.params.min_avg_volume_5d,
                'keltner_multiplier': self.target_calculator.keltner_multiplier,
                'top_n': self.volatility_evaluator.params.top_n,
                'default_risk_jpy': self.target_calculator.risk_jpy,
            },
            'total_results': len(results.get('dynamic', [])) + len(results.get('large_cap', [])),
            'stocks': [r.to_dict() for r in results.get('dynamic', [])],
            'stocks_large_cap': [r.to_dict() for r in results.get('large_cap', [])],
        }
