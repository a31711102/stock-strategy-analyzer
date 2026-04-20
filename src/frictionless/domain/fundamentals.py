from .models import FundamentalData, TrendStatus

def evaluate_fundamentals(data: FundamentalData) -> TrendStatus:
    """
    提供された財務指標データに基づき、🟩上昇 / 🟨横ばい / 🟥低下 のステータスを返却する。
    一部のデータがNone（パース失敗・そもそも未開示等）の場合は
    数式の破綻を防ぐため、安全に ⚠️ 判定不能 にフォールバックする。
    """
    # 必須パラメータの欠損チェック
    if data.sales_yoy_pct is None or \
       data.operating_profit_margin_pct is None or data.ordinary_profit_margin_pct is None or \
       data.roic_pct is None or data.equity_ratio_pct is None or data.interest_bearing_debt_ratio_pct is None:
        return TrendStatus.ERROR
        
    # 利益成長の判定（経常利益があれば経常を、なければ営業利益をみる）
    if data.ordinary_profit_yoy_pct is None and data.operating_profit_yoy_pct is None:
        return TrendStatus.ERROR

    # 上昇判定の条件
    profit_yoy_up = (data.ordinary_profit_yoy_pct >= 5) if data.ordinary_profit_yoy_pct is not None else (data.operating_profit_yoy_pct >= 5)
    
    is_up = (
        data.sales_yoy_pct >= 3 and
        profit_yoy_up and
        (data.operating_profit_margin_pct >= 10 or data.ordinary_profit_margin_pct >= 10) and
        data.roic_pct > 7 and
        data.equity_ratio_pct >= 40 and
        data.interest_bearing_debt_ratio_pct <= 200
    )
    if is_up:
        return TrendStatus.UP
        
    # 横ばい判定の条件（上昇条件を満たさなかった場合）
    profit_yoy_flat = (data.ordinary_profit_yoy_pct >= -5) if data.ordinary_profit_yoy_pct is not None else (data.operating_profit_yoy_pct >= -5)

    is_flat = (
        data.sales_yoy_pct >= -3 and
        profit_yoy_flat and
        data.roic_pct >= 5 and
        data.equity_ratio_pct >= 40 and
        data.interest_bearing_debt_ratio_pct <= 250
    )
    if is_flat:
        return TrendStatus.FLAT

    return TrendStatus.DOWN
