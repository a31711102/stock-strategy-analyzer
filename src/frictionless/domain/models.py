from dataclasses import dataclass
from typing import Optional
from enum import Enum

class TrendStatus(Enum):
    UP = "🟩 上昇"
    FLAT = "🟨 横ばい"
    DOWN = "🟥 低下"
    ERROR = "⚠️ 判定不能"

@dataclass
class FundamentalData:
    sales_yoy_pct: Optional[float]
    ordinary_profit_yoy_pct: Optional[float]
    operating_profit_yoy_pct: Optional[float]
    operating_profit_margin_pct: Optional[float]
    ordinary_profit_margin_pct: Optional[float]
    roic_pct: Optional[float]
    equity_ratio_pct: Optional[float]
    interest_bearing_debt_ratio_pct: Optional[float]

@dataclass
class TechnicalData:
    strategy_name: str
    is_entry: bool
    entry_price: Optional[float] = None
    atr_10: Optional[float] = None
    take_profit_text: Optional[str] = None
    stop_loss_text: Optional[str] = None

@dataclass
class StockAnalysisResult:
    stock_code: str
    fundamental_status: TrendStatus
    strategies: list[str]
    take_profit_line: str
    stop_loss_line: str
