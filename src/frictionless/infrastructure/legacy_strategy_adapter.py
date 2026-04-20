import pandas as pd
from typing import List, Dict, Optional
import os
import sys

# 既存のstrategiesを利用するため
from src.strategies import get_all_strategies, BaseStrategy
from src.frictionless.domain.models import TechnicalData

# 各既存手法に対する、固定の利確・損切説明マッピング
EXIT_CONDITIONS_MAP = {
    "順張り空売り": ("短期MA > 中期MA", "短期MA > 中期MA"),
    "トレンド転換（上昇）": ("RSI(14)が70以上", "株価 < 75日MA"),
    "トレンド転換（下降）": ("RSI(14)が30以下", "株価 > 75日MA"),
    "押し目買い（空売り）": ("短期MA > 中期MA", "短期MA > 中期MA"),
    "新安値ブレイク（空売り）": ("株価 > 短期MA", "株価 > 短期MA"),
    "新高値更新リトライ": ("株価 < 短期MA", "株価 < 短期MA")
}

class LegacyStrategyAdapter:
    """
    既存の StockStrategyAnalyzer の資産（src/strategies 以下）を呼び出し、
    当システム（Frictionless Analyzer）専用のドメインモデルに変換・遮断するAdapter。
    """
    def __init__(self):
        self.strategies = get_all_strategies()
        
    def evaluate(self, df: pd.DataFrame) -> List[TechnicalData]:
        """
        全手法に対してシグナル判定を行い、最新日で「エントリー(1)」が点灯手法のリストを返す。
        """
        results = []
        if df is None or len(df) == 0:
            return results
            
        for strategy in self.strategies:
            try:
                signals = strategy.generate_signals(df)
                latest_signal = signals.iloc[-1]
                
                if latest_signal == 1:
                    strategy_name = strategy.name()
                    tp_str, sl_str = EXIT_CONDITIONS_MAP.get(strategy_name, ("条件到達時", "条件到達時"))
                    
                    tech_data = TechnicalData(
                        strategy_name=strategy_name,
                        is_entry=True,
                        take_profit_text=tp_str,
                        stop_loss_text=sl_str
                    )
                    results.append(tech_data)
                    
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Strategy {strategy.name()} Evaluation Error: {e}")
                
        return results
