from .models import TechnicalData

def calculate_lines(tech: TechnicalData) -> tuple[str, str]:
    """
    テクニカル戦略名とデータに基づき、利確(TP)と損切(SL)のラインを文字列化して返す。
    Returns:
        (take_profit_line, stop_loss_line)
    """
    if tech.strategy_name == "新高値ブレイク":
        return ("株価 < 短期MA", "株価 < 短期MA")
        
    elif tech.strategy_name == "押し目買い":
        if tech.entry_price is None or tech.atr_10 is None:
            return ("判定不能", "判定不能")
        tp = tech.entry_price + (tech.atr_10 * 2.0)
        sl = tech.entry_price - (tech.atr_10 * 2.0)
        return (f"{tp:.1f}", f"{sl:.1f}")
        
    else:
        # 既存の6手法等（Adapter層から直接文字列でもらう場合）
        tp_str = tech.take_profit_text if tech.take_profit_text is not None else "設定なし"
        sl_str = tech.stop_loss_text if tech.stop_loss_text is not None else "設定なし"
        return (tp_str, sl_str)
