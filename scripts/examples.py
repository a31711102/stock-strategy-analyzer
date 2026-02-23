"""
使用例スクリプト

基本的な使い方を示すサンプルコード
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from src.data.fetcher import StockDataFetcher
from src.data.cache import DataCache
from src.indicators.technical import TechnicalIndicators
from src.analysis.compatibility import CompatibilityAnalyzer
from src.strategies.breakout_new_high_long import BreakoutNewHighLong
from src.strategies.pullback_buy_long import PullbackBuyLong


def example_single_stock_analysis():
    """単一銘柄の分析例"""
    print("=" * 60)
    print("例1: 単一銘柄の分析")
    print("=" * 60)
    
    # 銘柄コード
    stock_code = "9432"  # NTT
    
    # データ取得
    print(f"\n銘柄 {stock_code} のデータを取得中...")
    fetcher = StockDataFetcher(start_date="2007-01-01")
    cache = DataCache()
    
    df = cache.get(stock_code)
    if df is None:
        df = fetcher.fetch_stock_data(stock_code)
        if df is not None:
            cache.set(stock_code, df)
    
    if df is None:
        print("データ取得に失敗しました")
        return
    
    print(f"データ取得完了: {len(df)} 行")
    
    # テクニカル指標計算
    print("\nテクニカル指標を計算中...")
    df = TechnicalIndicators.calculate_all_indicators(df)
    print("計算完了")
    
    # 手法インスタンス作成
    strategies = [
        BreakoutNewHighLong(),
        PullbackBuyLong()
    ]
    
    # 適合度分析
    print("\n適合度を分析中...")
    analyzer = CompatibilityAnalyzer()
    results = analyzer.calculate_compatibility(stock_code, df, strategies)
    
    # 結果表示
    print(f"\n{'='*60}")
    print(f"銘柄コード: {stock_code}")
    print(f"{'='*60}")
    
    for strategy_name, result in results.items():
        print(f"\n【{strategy_name}】")
        print(f"適合度: {result['score']:.1f}%")
        print(f"\n{result['reason']}")
        print("-" * 60)


def example_backtest_details():
    """バックテスト詳細の取得例"""
    print("\n" + "=" * 60)
    print("例2: バックテスト詳細の取得")
    print("=" * 60)
    
    stock_code = "9432"
    
    # データ取得
    fetcher = StockDataFetcher()
    cache = DataCache()
    
    df = cache.get(stock_code)
    if df is None:
        df = fetcher.fetch_stock_data(stock_code)
        if df is not None:
            cache.set(stock_code, df)
    
    if df is None:
        print("データ取得に失敗しました")
        return
    
    df = TechnicalIndicators.calculate_all_indicators(df)
    
    # 手法
    strategy = BreakoutNewHighLong()
    
    # バックテスト実行
    from src.backtest.engine import BacktestEngine
    engine = BacktestEngine()
    result = engine.run_backtest(df, strategy, stock_code)
    
    # 詳細結果表示
    print(f"\n銘柄: {result.stock_code}")
    print(f"手法: {result.strategy_name}")
    print(f"\nパフォーマンス指標:")
    print(f"  総リターン: {result.total_return:.2f}%")
    print(f"  年率リターン: {result.annual_return:.2f}%")
    print(f"  シャープレシオ: {result.sharpe_ratio:.2f}")
    print(f"  最大ドローダウン: {result.max_drawdown:.2f}%")
    print(f"  勝率: {result.win_rate:.2f}%")
    print(f"  プロフィットファクター: {result.profit_factor:.2f}")
    print(f"  取引回数: {result.num_trades}")
    
    # 取引履歴（最初の5件）
    if result.trades:
        print(f"\n取引履歴（最初の5件）:")
        for i, trade in enumerate(result.trades[:5], 1):
            print(f"\n  取引 {i}:")
            print(f"    エントリー: {trade['entry_date'].strftime('%Y-%m-%d')} @ {trade['entry_price']:.2f}")
            print(f"    エグジット: {trade['exit_date'].strftime('%Y-%m-%d')} @ {trade['exit_price']:.2f}")
            print(f"    損益: {trade['profit']:.2f} ({trade['profit_pct']:.2f}%)")
            print(f"    保有日数: {trade['holding_days']}日")


def example_strategy_filtering():
    """手法フィルタリングの例"""
    print("\n" + "=" * 60)
    print("例3: 手法で銘柄をフィルタリング（デモ版）")
    print("=" * 60)
    
    # 銘柄リスト（デモ用に数銘柄のみ）
    stock_codes = ["9432", "6758", "7203"]  # NTT, ソニー、トヨタ
    
    # 手法
    strategy = BreakoutNewHighLong()
    
    print(f"\n手法: {strategy.name()}")
    print(f"対象銘柄: {len(stock_codes)} 銘柄")
    
    # データ取得と分析
    fetcher = StockDataFetcher()
    cache = DataCache()
    analyzer = CompatibilityAnalyzer()
    
    results = []
    for code in stock_codes:
        print(f"\n分析中: {code}")
        
        df = cache.get(code)
        if df is None:
            df = fetcher.fetch_stock_data(code)
            if df is None:
                continue
            cache.set(code, df)
        
        df = TechnicalIndicators.calculate_all_indicators(df)
        
        compatibility = analyzer.calculate_compatibility(code, df, [strategy])
        score = compatibility[strategy.name()]['score']
        
        results.append((code, score))
    
    # ランキング表示
    results.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n{'='*60}")
    print("適合度ランキング:")
    print(f"{'='*60}")
    
    for i, (code, score) in enumerate(results, 1):
        print(f"{i}. {code}: {score:.1f}%")


if __name__ == "__main__":
    # 例1: 単一銘柄の分析
    example_single_stock_analysis()
    
    # 例2: バックテスト詳細
    # example_backtest_details()
    
    # 例3: 手法フィルタリング
    # example_strategy_filtering()
    
    print("\n" + "=" * 60)
    print("サンプル実行完了")
    print("=" * 60)
