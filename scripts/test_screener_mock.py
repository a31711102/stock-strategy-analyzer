"""
スクリーナー結果のモックデータを生成し、静的ページ生成をテストするスクリプト
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.batch.result_cache import ResultCache

# テスト用モックデータ
mock_result = {
    "generated_at": "2026-04-10T22:00:00+09:00",
    "parameters": {
        "min_norm_atr": 2.0,
        "min_avg_volume": 500000,
        "keltner_multiplier": 2.0,
        "top_n": 20,
        "default_risk_jpy": 30000
    },
    "total_results": 5,
    "stocks": [
        {
            "rank": 1, "ticker": "9984", "name": "ソフトバンクグループ",
            "rvr": 2.35, "norm_atr": 4.12, "atr_10": 265.0,
            "target_buy": 8420.0, "stop_loss": 7890.0,
            "current_price": 8572.0, "proximity_pct": 1.77,
            "is_proximity_alert": False, "quantity": 100,
            "is_sub_unit": False, "capital": 842000.0,
            "sma_25": 8950.0, "avg_volume_5d": 8500000, "status": "Range"
        },
        {
            "rank": 2, "ticker": "6758", "name": "ソニーグループ",
            "rvr": 2.10, "norm_atr": 3.50, "atr_10": 180.0,
            "target_buy": 4800.0, "stop_loss": 4440.0,
            "current_price": 4830.0, "proximity_pct": 0.62,
            "is_proximity_alert": True, "quantity": 100,
            "is_sub_unit": False, "capital": 480000.0,
            "sma_25": 5160.0, "avg_volume_5d": 6200000, "status": "Down"
        },
        {
            "rank": 3, "ticker": "7203", "name": "トヨタ自動車",
            "rvr": 1.95, "norm_atr": 2.80, "atr_10": 85.0,
            "target_buy": 2870.0, "stop_loss": 2700.0,
            "current_price": 3050.0, "proximity_pct": 5.90,
            "is_proximity_alert": False, "quantity": 100,
            "is_sub_unit": False, "capital": 287000.0,
            "sma_25": 3040.0, "avg_volume_5d": 12000000, "status": "Up"
        },
        {
            "rank": 4, "ticker": "8306", "name": "三菱UFJ",
            "rvr": 1.80, "norm_atr": 2.30, "atr_10": 45.0,
            "target_buy": 1860.0, "stop_loss": 1770.0,
            "current_price": 1950.0, "proximity_pct": 4.62,
            "is_proximity_alert": False, "quantity": 300,
            "is_sub_unit": False, "capital": 558000.0,
            "sma_25": 1950.0, "avg_volume_5d": 25000000, "status": "Sideways"
        },
        {
            "rank": 5, "ticker": "4063", "name": "信越化学工業",
            "rvr": 1.75, "norm_atr": 3.90, "atr_10": 350.0,
            "target_buy": 8280.0, "stop_loss": 7580.0,
            "current_price": 8980.0, "proximity_pct": 7.80,
            "is_proximity_alert": False, "quantity": 0,
            "is_sub_unit": True, "capital": 0,
            "sma_25": 8980.0, "avg_volume_5d": 1800000, "status": "Up"
        },
    ]
}

if __name__ == "__main__":
    cache = ResultCache(str(PROJECT_ROOT / "results"))
    cache.save_screener_result(mock_result)
    print(f"モックデータ保存完了: {len(mock_result['stocks'])}銘柄")
    print("次に 'python scripts/generate_static_pages.py' を実行してください")
