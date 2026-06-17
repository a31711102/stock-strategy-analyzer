"""
市場区分ユーティリティ

data_j.xls（JPX上場銘柄一覧）から銘柄コード→市場区分のマップを構築し、
東証プライム判定を提供する。
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)

PRIME_KEYWORD = 'プライム'


def is_prime(market_segment: str) -> bool:
    """市場区分文字列が東証プライムかどうかを判定"""
    return PRIME_KEYWORD in (market_segment or '')


def load_market_map(stock_list_path: str) -> Dict[str, str]:
    """
    銘柄リスト（data_j.xls）から {銘柄コード: 市場区分} のマップを構築

    Args:
        stock_list_path: data_j.xls のパス

    Returns:
        {コード(str): 市場区分(str)} の辞書。読み込み失敗時は空辞書。
    """
    import pandas as pd

    try:
        df = pd.read_excel(stock_list_path)
        # daily_batch.load_stock_list と同じカラム順（2列目=コード, 4列目=市場・商品区分）
        code_col = df.columns[1]
        market_col = df.columns[3]
        market_map = {
            str(code): str(market)
            for code, market in zip(df[code_col], df[market_col])
        }
        logger.info(f"市場区分マップ構築完了: {len(market_map)}銘柄")
        return market_map
    except Exception as e:
        logger.error(f"市場区分マップ構築エラー ({stock_list_path}): {e}")
        return {}
