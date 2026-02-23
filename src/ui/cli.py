"""
CLIインターフェース

コマンドラインから株式分析を実行
"""
import click
import yaml
import logging
from pathlib import Path
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.fetcher import StockDataFetcher
from src.data.cache import DataCache
from src.indicators.technical import TechnicalIndicators
from src.analysis.compatibility import CompatibilityAnalyzer

# 手法のインポート
from src.strategies.breakout_new_high_long import BreakoutNewHighLong
from src.strategies.pullback_buy_long import PullbackBuyLong
from src.strategies.retry_new_high_long import RetryNewHighLong
from src.strategies.trend_reversal_up_long import TrendReversalUpLong
from src.strategies.pullback_short import PullbackShort
from src.strategies.breakout_new_low_short import BreakoutNewLowShort
from src.strategies.trend_reversal_down_short import TrendReversalDownShort
from src.strategies.momentum_short import MomentumShort

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_strategies():
    """有効な手法をロード"""
    strategies = [
        BreakoutNewHighLong(),
        PullbackBuyLong(),
        RetryNewHighLong(),
        TrendReversalUpLong(),
        PullbackShort(),
        BreakoutNewLowShort(),
        TrendReversalDownShort(),
        MomentumShort()
    ]
    return strategies


@click.group()
def cli():
    """株式投資判断支援ツール"""
    pass


@cli.command()
@click.argument('stock_code')
@click.option('--config', default='config.yaml', help='設定ファイルのパス')
def analyze(stock_code, config):
    """
    指定した銘柄を分析
    
    例: python -m src.ui.cli analyze 9432
    """
    click.echo(f"銘柄 {stock_code} を分析中...")
    
    # 設定読み込み
    with open(config, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    
    # データ取得
    fetcher = StockDataFetcher(
        start_date=cfg['data']['start_date'],
        use_fallback=cfg['data']['fallback']
    )
    cache = DataCache(ttl_hours=cfg['data']['cache_ttl_hours'])
    
    # キャッシュチェック
    df = cache.get(stock_code)
    if df is None:
        click.echo("データを取得中...")
        df = fetcher.fetch_stock_data(stock_code)
        if df is None:
            click.echo(f"エラー: 銘柄 {stock_code} のデータを取得できませんでした", err=True)
            return
        cache.set(stock_code, df)
    
    # テクニカル指標計算
    click.echo("テクニカル指標を計算中...")
    df = TechnicalIndicators.calculate_all_indicators(df)
    
    # 手法ロード
    strategies = load_strategies()
    
    # 適合度分析
    click.echo("適合度を計算中...")
    analyzer = CompatibilityAnalyzer(config)
    results = analyzer.calculate_compatibility(stock_code, df, strategies)
    
    # 結果表示
    click.echo("\n" + "="*60)
    click.echo(f"銘柄コード: {stock_code}")
    click.echo("="*60)
    
    for strategy_name, result in sorted(results.items(), key=lambda x: x[1]['score'], reverse=True):
        score = result['score']
        click.echo(f"\n【{strategy_name}】")
        click.echo(f"適合度: {score:.1f}%")
        click.echo(f"\n{result['reason']}")
        click.echo("-"*60)


@cli.command()
@click.argument('strategy_name')
@click.option('--threshold', default=60.0, help='適合度の閾値（%）')
@click.option('--top', default=10, help='表示する銘柄数')
@click.option('--config', default='config.yaml', help='設定ファイルのパス')
def filter_stocks(strategy_name, threshold, top, config):
    """
    手法に適合する銘柄をフィルタリング
    
    例: python -m src.ui.cli filter-stocks 新高値ブレイク --threshold 70 --top 20
    """
    click.echo(f"手法「{strategy_name}」で銘柄をフィルタリング中...")
    
    # 設定読み込み
    with open(config, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    
    # 銘柄リスト読み込み
    fetcher = StockDataFetcher()
    stock_list_path = cfg['data']['stock_list_path']
    
    click.echo(f"銘柄リストを読み込み中: {stock_list_path}")
    stock_codes = fetcher.load_stock_list(stock_list_path)
    
    if not stock_codes:
        click.echo("エラー: 銘柄リストを読み込めませんでした", err=True)
        return
    
    click.echo(f"{len(stock_codes)} 銘柄を読み込みました")
    
    # 手法選択
    strategies = load_strategies()
    strategy = None
    for s in strategies:
        if s.name() == strategy_name:
            strategy = s
            break
    
    if strategy is None:
        click.echo(f"エラー: 手法「{strategy_name}」が見つかりません", err=True)
        click.echo("利用可能な手法:")
        for s in strategies:
            click.echo(f"  - {s.name()}")
        return
    
    # データ取得と分析（簡易版：最初のN銘柄のみ）
    click.echo(f"\n注: デモ版のため、最初の10銘柄のみ分析します")
    
    cache = DataCache(ttl_hours=cfg['data']['cache_ttl_hours'])
    analyzer = CompatibilityAnalyzer(config)
    
    results = []
    for i, code in enumerate(stock_codes[:10]):  # デモ版は10銘柄のみ
        click.echo(f"分析中: {code} ({i+1}/10)")
        
        df = cache.get(code)
        if df is None:
            df = fetcher.fetch_stock_data(code)
            if df is None:
                continue
            cache.set(code, df)
        
        df = TechnicalIndicators.calculate_all_indicators(df)
        
        compatibility = analyzer.calculate_compatibility(code, df, [strategy])
        score = compatibility[strategy.name()]['score']
        reason = compatibility[strategy.name()]['reason']
        
        if score >= threshold:
            results.append((code, score, reason))
    
    # 結果表示
    results.sort(key=lambda x: x[1], reverse=True)
    results = results[:top]
    
    click.echo("\n" + "="*60)
    click.echo(f"手法: {strategy_name}")
    click.echo(f"閾値: {threshold}%以上")
    click.echo(f"該当銘柄数: {len(results)}")
    click.echo("="*60)
    
    for i, (code, score, reason) in enumerate(results, 1):
        click.echo(f"\n{i}. 銘柄コード: {code}")
        click.echo(f"   適合度: {score:.1f}%")
        click.echo(f"   {reason.split(chr(10))[0]}")  # 最初の行のみ表示


@cli.command()
def list_strategies():
    """利用可能な手法一覧を表示"""
    strategies = load_strategies()
    
    click.echo("利用可能な投資手法:")
    click.echo("="*60)
    
    for strategy in strategies:
        click.echo(f"\n【{strategy.name()}】")
        click.echo(f"タイプ: {'買い' if strategy.strategy_type() == 'long' else '空売り'}")
        click.echo(f"説明: {strategy.get_description()}")


if __name__ == '__main__':
    cli()
