"""
GitHub Pages 向け静的HTML生成スクリプト

results/ のバックテスト結果（JSON）を読み取り、
docs/ にHTML + CSS + JS を出力する。

Usage:
    python scripts/generate_static_pages.py
"""
import sys
import os
import shutil
import json
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from jinja2 import Environment, FileSystemLoader
from src.batch.result_cache import ResultCache

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# 設定
RESULTS_DIR = PROJECT_ROOT / 'results'
DOCS_DIR = PROJECT_ROOT / 'docs'
TEMPLATES_DIR = PROJECT_ROOT / 'web' / 'templates'
STATIC_DIR = PROJECT_ROOT / 'web' / 'static'

MIN_SCORE_THRESHOLD = 40.0


def setup_jinja_env() -> Environment:
    """Jinja2 環境を静的サイト用にセットアップ"""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    # カスタムフィルタ: カンマ区切り数値フォーマット
    env.filters['number_format'] = lambda value: f'{value:,.0f}' if value else '-'
    return env


def copy_static_assets():
    """CSS / JS を docs/ にコピー"""
    dest_static = DOCS_DIR / 'static'
    if dest_static.exists():
        shutil.rmtree(dest_static)
    shutil.copytree(STATIC_DIR, dest_static)
    logger.info(f'  静的ファイルをコピー: {dest_static}')


def render_template(env: Environment, template_name: str, output_path: Path, **context):
    """テンプレートをレンダリングしてファイルに書き出す"""
    template = env.get_template(template_name)
    html = template.render(**context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    logger.info(f'  生成: {output_path.relative_to(DOCS_DIR)}')


def generate_base_html():
    """静的サイト用の base.html を生成（url_for を除去）"""
    base_content = '''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>{% block title %}Stock Strategy Analyzer{% endblock %}</title>
    <link rel="stylesheet" href="{{ static_root }}static/css/main.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body>
    <header class="header">
        <div class="container">
            <a href="{{ site_root }}index.html" class="logo">
                📊 Stock Strategy Analyzer
            </a>
        </div>
    </header>

    <main class="main">
        <div class="container">
            {% block content %}{% endblock %}
        </div>
    </main>

    <footer class="footer">
        <div class="container">
            <p>最終更新: {{ last_updated }}</p>
        </div>
    </footer>
</body>
</html>'''
    return base_content


def generate_index_html():
    """トップページ（戦略一覧）のテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}戦略一覧 - Stock Strategy Analyzer{% endblock %}

{% block content %}
<section class="hero">
    <h1>Stock Strategy Analyzer</h1>
    <p class="hero-sub">バックテスト結果に基づく銘柄・戦略の適合度分析</p>

    {% if metadata %}
    <div class="stats-bar">
        <div class="stat">
            <span class="stat-value">{{ metadata.processed_stocks or 0 }}</span>
            <span class="stat-label">処理済み銘柄</span>
        </div>
        <div class="stat">
            <span class="stat-value">{{ metadata.strategies|length }}</span>
            <span class="stat-label">投資戦略</span>
        </div>
        <div class="stat">
            <span class="stat-value">{{ metadata.last_updated[:10] if metadata.last_updated else '-' }}</span>
            <span class="stat-label">最終更新</span>
        </div>
    </div>
    {% endif %}

    <div class="nav-links">
        <a href="{{ site_root }}index.html" class="nav-link active">📊 適合度ランキング</a>
        <a href="{{ site_root }}approaching/index.html" class="nav-link">🎯 シグナル接近中</a>
    </div>
</section>

<section class="criteria-section">
    <details class="criteria-details">
        <summary class="criteria-summary">📋 適合度の評価基準</summary>
        <div class="criteria-content">
            <p class="criteria-intro">適合度は以下の指標を総合的に評価して算出されます（40%以上のみランキングに表示）</p>
            <div class="criteria-grid">
                <div class="criteria-item">
                    <h4>📈 リターン（40%）</h4>
                    <ul>
                        <li><span class="ok">OK</span> +20%以上: 高リターン</li>
                        <li><span class="ok">OK</span> +10%〜20%: 中リターン</li>
                        <li><span class="mid">中</span> 0%〜10%: 小リターン</li>
                        <li><span class="ng">NG</span> マイナス: 損失</li>
                    </ul>
                </div>
                <div class="criteria-item">
                    <h4>🎯 勝率（30%）</h4>
                    <ul>
                        <li><span class="ok">OK</span> 60%以上: 高勝率</li>
                        <li><span class="mid">中</span> 40%〜60%: 中勝率</li>
                        <li><span class="ng">NG</span> 40%未満: 低勝率</li>
                    </ul>
                </div>
                <div class="criteria-item">
                    <h4>🔢 取引回数（30%）</h4>
                    <ul>
                        <li><span class="ok">OK</span> 10回以上: 十分な機会</li>
                        <li><span class="mid">中</span> 5〜9回: 機会あり</li>
                        <li><span class="ng">NG</span> 5回未満: 機会少</li>
                    </ul>
                </div>
                <div class="criteria-item">
                    <h4>📉 最大下落率</h4>
                    <ul>
                        <li><span class="ok">OK</span> 20%未満: 低リスク</li>
                        <li><span class="mid">中</span> 20%〜40%: 中リスク</li>
                        <li><span class="ng">NG</span> 40%以上: 高リスク</li>
                    </ul>
                    <p class="note">※最高値からの最大下落幅</p>
                </div>
            </div>
        </div>
    </details>
</section>

<section class="strategies-section">
    <h2>戦略別ランキング</h2>
    <div class="strategy-grid">
        {% for strategy in strategies %}
        <a href="{{ site_root }}strategy/{{ strategy.name_encoded }}.html" class="strategy-card">
            <h3 class="strategy-name">{{ strategy.name }}</h3>

            {% if strategy.top3 %}
            <div class="top3-preview">
                {% for item in strategy.top3 %}
                <div class="preview-item">
                    <span class="rank">#{{ item.rank }}</span>
                    <span class="code">{{ item.code }}</span>
                    <span class="name">{{ item.name }}</span>
                    <span class="score">{{ "%.1f"|format(item.score) }}%</span>
                </div>
                {% endfor %}
            </div>
            {% endif %}

            <span class="card-arrow">→</span>
        </a>
        {% endfor %}
    </div>
</section>
{% endblock %}'''


def generate_strategy_ranking_html():
    """戦略別ランキングページのテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}{{ strategy_name }} ランキング - Stock Strategy Analyzer{% endblock %}

{% block content %}
<nav class="breadcrumb">
    <a href="{{ site_root }}index.html">トップ</a>
    <span>›</span>
    <span>{{ strategy_name }}</span>
</nav>

<section class="ranking-section">
    <header class="section-header">
        <h1>{{ strategy_name }}</h1>
        <p class="subtitle">適合度ランキング Top {{ rankings|length }}</p>
    </header>

    <div class="strategy-nav">
        {% for s in strategies %}
        <a href="{{ site_root }}strategy/{{ s.encoded }}.html"
            class="strategy-tab {{ 'active' if s.name == strategy_name else '' }}">
            {{ s.name }}
        </a>
        {% endfor %}
    </div>

    <div class="ranking-table-wrapper">
        <table class="ranking-table">
            <thead>
                <tr>
                    <th class="col-rank">順位</th>
                    <th class="col-code">コード</th>
                    <th class="col-name">銘柄名</th>
                    <th class="col-score">スコア</th>
                    <th class="col-reason">評価</th>
                </tr>
            </thead>
            <tbody>
                {% for item in rankings %}
                <tr>
                    <td class="col-rank">
                        <span class="rank-badge rank-{{ item.rank }}">{{ item.rank }}</span>
                    </td>
                    <td class="col-code">{{ item.code }}</td>
                    <td class="col-name">{{ item.name }}</td>
                    <td class="col-score">
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ item.score }}%"></div>
                            <span class="score-value">{{ "%.1f"|format(item.score) }}%</span>
                        </div>
                    </td>
                    <td class="col-reason">
                        <span class="reason-short">{{ item.reason.split('\\n')[0] if item.reason else '' }}</span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</section>
{% endblock %}'''


def generate_approaching_index_html():
    """接近シグナル一覧ページのテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}シグナル接近中 - Stock Strategy Analyzer{% endblock %}

{% block content %}
<section class="hero approaching-hero">
    <h1>🎯 シグナル接近中の銘柄</h1>
    <p class="hero-sub">直近1〜3ヶ月のデータから、近日中にシグナル発生が予想される銘柄</p>

    {% if metadata %}
    <div class="stats-bar">
        <div class="stat">
            <span class="stat-value">{{ strategies|length }}</span>
            <span class="stat-label">戦略</span>
        </div>
        <div class="stat">
            <span class="stat-value">{{ metadata.last_updated[:10] if metadata.last_updated else '-' }}</span>
            <span class="stat-label">最終更新</span>
        </div>
    </div>
    {% endif %}

    <div class="nav-links">
        <a href="{{ site_root }}index.html" class="nav-link">📊 適合度ランキング</a>
        <a href="{{ site_root }}approaching/index.html" class="nav-link active">🎯 シグナル接近中</a>
    </div>
</section>

<section class="criteria-section">
    <details class="criteria-details">
        <summary class="criteria-summary">📋 シグナル接近の判定基準</summary>
        <div class="criteria-content">
            <p class="criteria-intro">各戦略のエントリー条件にどれだけ近づいているかを分析し、残り日数を推定しています。</p>
            <div class="criteria-grid">
                <div class="criteria-item">
                    <h4>🎯 接近スコア</h4>
                    <ul>
                        <li><span class="ok">OK</span> 80%以上: 1日以内</li>
                        <li><span class="ok">OK</span> 60%〜80%: 3日以内</li>
                        <li><span class="mid">中</span> 40%〜60%: 1週間以内</li>
                    </ul>
                </div>
                <div class="criteria-item">
                    <h4>📅 推定日数</h4>
                    <p>条件の達成度合いから、シグナル発生までの推定日数を算出</p>
                </div>
            </div>
        </div>
    </details>
</section>

<section class="strategies-section">
    <h2>戦略別 接近銘柄</h2>

    {% if strategies %}
    <div class="strategy-grid">
        {% for strategy in strategies %}
        <a href="{{ site_root }}approaching/{{ strategy.name_encoded }}.html" class="strategy-card approaching-card">
            <h3 class="strategy-name">{{ strategy.name }}</h3>

            {% if strategy.top3 %}
            <div class="top3-preview">
                {% for item in strategy.top3 %}
                <div class="preview-item approaching-item">
                    <span class="rank">#{{ item.rank }}</span>
                    <span class="code">{{ item.code }}</span>
                    <span class="name">{{ item.name }}</span>
                    <span class="days-badge">約{{ item.estimated_days or '?' }}日後</span>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="no-signals">
                <p>接近中の銘柄はありません</p>
            </div>
            {% endif %}

            <span class="card-arrow">→</span>
        </a>
        {% endfor %}
    </div>
    {% else %}
    <div class="no-data">
        <p>接近シグナルのデータがありません。</p>
    </div>
    {% endif %}
</section>

<style>
    .approaching-hero {
        background: linear-gradient(135deg, #1a365d 0%, #2d4a73 100%);
    }
    .nav-links {
        margin-top: 1.5rem;
        display: flex;
        gap: 1rem;
        justify-content: center;
        flex-wrap: wrap;
    }
    .nav-link {
        padding: 0.5rem 1rem;
        background: rgba(255, 255, 255, 0.1);
        color: white;
        text-decoration: none;
        border-radius: 20px;
        transition: all 0.2s;
    }
    .nav-link:hover {
        background: rgba(255, 255, 255, 0.2);
    }
    .nav-link.active {
        background: rgba(255, 255, 255, 0.25);
        font-weight: bold;
    }
    .approaching-card {
        border-left: 4px solid #f59e0b;
    }
    .approaching-item .days-badge {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
        white-space: nowrap;
    }
    .no-signals {
        padding: 1rem;
        color: #6b7280;
        text-align: center;
    }
    .no-data {
        text-align: center;
        padding: 3rem;
        color: #6b7280;
    }
</style>
{% endblock %}'''


def generate_approaching_strategy_html():
    """戦略別接近シグナルページのテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}{{ strategy_name }} 接近シグナル - Stock Strategy Analyzer{% endblock %}

{% block content %}
<section class="hero strategy-hero approaching-hero">
    <h1>🎯 {{ strategy_name }}</h1>
    <p class="hero-sub">シグナル接近中の銘柄（Top 50・出来高50万以上）</p>

    <div class="nav-links">
        <a href="{{ site_root }}approaching/index.html" class="nav-link">← 戦略一覧へ戻る</a>
        <a href="{{ site_root }}strategy/{{ strategy_name_encoded }}.html" class="nav-link">📊 適合度ランキング</a>
    </div>
</section>

<section class="ranking-section">
    {% if signals %}
    <table class="ranking-table approaching-table">
        <thead>
            <tr>
                <th class="rank-col">順位</th>
                <th class="code-col">コード</th>
                <th class="name-col">銘柄名</th>
                <th class="days-col">推定日数</th>
                <th class="score-col">接近度</th>
                <th class="volume-col">平均出来高</th>
                <th class="conditions-col">達成条件</th>
            </tr>
        </thead>
        <tbody>
            {% for signal in signals %}
            <tr>
                <td class="rank-col">{{ signal.rank }}</td>
                <td class="code-col">{{ signal.code }}</td>
                <td class="name-col">{{ signal.name }}</td>
                <td class="days-col">
                    <span
                        class="days-badge {% if signal.estimated_days <= 1 %}imminent{% elif signal.estimated_days <= 3 %}soon{% else %}later{% endif %}">
                        約{{ signal.estimated_days or '?' }}日後
                    </span>
                </td>
                <td class="score-col">
                    <span
                        class="score-badge {% if signal.score >= 80 %}high{% elif signal.score >= 60 %}medium{% else %}low{% endif %}">
                        {{ "%.0f"|format(signal.score) }}%
                    </span>
                </td>
                <td class="volume-col">
                    {% if signal.avg_volume is defined and signal.avg_volume %}
                    {{ signal.avg_volume|number_format }}
                    {% else %}
                    -
                    {% endif %}
                </td>
                <td class="conditions-col">
                    <div class="conditions-summary">
                        {% for cond in signal.conditions_met %}
                        <span class="condition-tag met">✓ {{ cond }}</span>
                        {% endfor %}
                        {% for cond in signal.conditions_pending %}
                        <span class="condition-tag pending">⏳ {{ cond }}</span>
                        {% endfor %}
                    </div>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="no-data">
        <p>{{ strategy_name }}で接近中の銘柄はありません。</p>
    </div>
    {% endif %}
</section>

<style>
    .approaching-hero {
        background: linear-gradient(135deg, #1a365d 0%, #2d4a73 100%);
    }
    .nav-links {
        margin-top: 1.5rem;
        display: flex;
        gap: 1rem;
        justify-content: center;
        flex-wrap: wrap;
    }
    .nav-link {
        padding: 0.5rem 1rem;
        background: rgba(255, 255, 255, 0.1);
        color: white;
        text-decoration: none;
        border-radius: 20px;
        transition: all 0.2s;
    }
    .nav-link:hover {
        background: rgba(255, 255, 255, 0.2);
    }
    .approaching-table .days-col,
    .approaching-table .score-col {
        text-align: center;
    }
    .days-badge {
        display: inline-block;
        padding: 0.3rem 0.6rem;
        border-radius: 15px;
        font-size: 0.85rem;
        font-weight: bold;
    }
    .days-badge.imminent {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
    }
    .days-badge.soon {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
    }
    .days-badge.later {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    .score-badge {
        display: inline-block;
        padding: 0.3rem 0.6rem;
        border-radius: 15px;
        font-size: 0.85rem;
        font-weight: bold;
    }
    .score-badge.high {
        background: #10b981;
        color: white;
    }
    .score-badge.medium {
        background: #f59e0b;
        color: white;
    }
    .score-badge.low {
        background: #6b7280;
        color: white;
    }
    .conditions-summary {
        display: flex;
        flex-wrap: wrap;
        gap: 0.3rem;
    }
    .condition-tag {
        font-size: 0.75rem;
        padding: 0.2rem 0.4rem;
        border-radius: 8px;
        white-space: nowrap;
    }
    .condition-tag.met {
        background: #d1fae5;
        color: #065f46;
    }
    .condition-tag.pending {
        background: #fef3c7;
        color: #92400e;
    }
    .no-data {
        text-align: center;
        padding: 3rem;
        color: #6b7280;
    }
</style>
{% endblock %}'''


def safe_filename(name: str) -> str:
    """戦略名をファイル名として安全な形に変換"""
    return name


def generate_all():
    """全ページを生成"""
    logger.info('=== 静的HTML生成開始 ===')

    if not RESULTS_DIR.exists():
        logger.error(f'結果ディレクトリが見つかりません: {RESULTS_DIR}')
        sys.exit(1)

    # docs/ を初期化
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True)

    # 静的ファイルをコピー
    copy_static_assets()

    # ResultCache でデータ読み込み
    cache = ResultCache(str(RESULTS_DIR))
    metadata = cache.get_metadata()

    last_updated = '-'
    if metadata and metadata.get('last_updated'):
        last_updated = metadata['last_updated'][:10]

    # 静的テンプレートを一時ディレクトリに書き出し
    static_templates_dir = DOCS_DIR / '_templates'
    static_templates_dir.mkdir()

    (static_templates_dir / 'static_base.html').write_text(
        generate_base_html(), encoding='utf-8'
    )
    (static_templates_dir / 'static_index.html').write_text(
        generate_index_html(), encoding='utf-8'
    )
    (static_templates_dir / 'static_strategy_ranking.html').write_text(
        generate_strategy_ranking_html(), encoding='utf-8'
    )
    (static_templates_dir / 'static_approaching_index.html').write_text(
        generate_approaching_index_html(), encoding='utf-8'
    )
    (static_templates_dir / 'static_approaching_strategy.html').write_text(
        generate_approaching_strategy_html(), encoding='utf-8'
    )

    env = Environment(
        loader=FileSystemLoader(str(static_templates_dir)),
        autoescape=True,
    )
    # カスタムフィルタを追加
    env.filters['number_format'] = lambda value: f'{value:,.0f}' if value else '-'

    # 共通コンテキスト（ルート用）
    base_ctx = {
        'last_updated': last_updated,
        'site_root': './',
        'static_root': './',
    }

    # === 1. トップページ ===
    logger.info('\n[1/4] トップページ生成')
    ranking_strategies = cache.get_available_strategies()
    strategy_info = []
    for name in ranking_strategies:
        raw = cache.load_ranking(name, limit=10)
        filtered = [r for r in raw if r.get('score', 0) >= MIN_SCORE_THRESHOLD]
        strategy_info.append({
            'name': name,
            'name_encoded': safe_filename(name),
            'top3': filtered[:3],
        })

    render_template(env, 'static_index.html', DOCS_DIR / 'index.html',
                    strategies=strategy_info, metadata=metadata, **base_ctx)

    # === 2. 戦略別ランキングページ ===
    logger.info('\n[2/4] 戦略別ランキングページ生成')
    strategy_nav = [{'name': n, 'encoded': safe_filename(n)} for n in ranking_strategies]
    sub_ctx = {**base_ctx, 'site_root': '../', 'static_root': '../'}

    for name in ranking_strategies:
        raw = cache.load_ranking(name, limit=100)
        rankings = [r for r in raw if r.get('score', 0) >= MIN_SCORE_THRESHOLD][:30]

        render_template(env, 'static_strategy_ranking.html',
                        DOCS_DIR / 'strategy' / f'{safe_filename(name)}.html',
                        strategy_name=name, rankings=rankings,
                        strategies=strategy_nav, **sub_ctx)

    # === 3. 接近シグナル トップページ ===
    logger.info('\n[3/4] 接近シグナル一覧ページ生成')
    approaching_strategies = cache.get_available_approaching_strategies()
    approaching_info = []
    for name in approaching_strategies:
        signals = cache.load_approaching_signals(name, limit=3)
        approaching_info.append({
            'name': name,
            'name_encoded': safe_filename(name),
            'top3': signals,
        })

    render_template(env, 'static_approaching_index.html',
                    DOCS_DIR / 'approaching' / 'index.html',
                    strategies=approaching_info, metadata=metadata, **sub_ctx)

    # === 4. 戦略別接近シグナルページ ===
    logger.info('\n[4/4] 戦略別接近シグナルページ生成')
    for name in approaching_strategies:
        signals = cache.load_approaching_signals(name, limit=50)

        render_template(env, 'static_approaching_strategy.html',
                        DOCS_DIR / 'approaching' / f'{safe_filename(name)}.html',
                        strategy_name=name,
                        strategy_name_encoded=safe_filename(name),
                        signals=signals, **sub_ctx)

    # 一時テンプレートを削除
    shutil.rmtree(static_templates_dir)

    # 生成結果サマリ
    generated = list(DOCS_DIR.rglob('*.html'))
    logger.info(f'\n=== 生成完了: {len(generated)}ページ ===')
    for p in sorted(generated):
        logger.info(f'  {p.relative_to(DOCS_DIR)}')


if __name__ == '__main__':
    generate_all()
