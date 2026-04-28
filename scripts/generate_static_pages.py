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
        <a href="{{ site_root }}screener/index.html" class="nav-link">🔥 ボラティリティスクリーナー</a>
        <a href="{{ site_root }}low-hunter/index.html" class="nav-link">📉 黄金の指値ボード</a>
        <a href="{{ site_root }}high-hunter/index.html" class="nav-link">📈 黄金の空売りボード</a>
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
        <a href="{{ site_root }}screener/index.html" class="nav-link">🔥 ボラティリティスクリーナー</a>
        <a href="{{ site_root }}low-hunter/index.html" class="nav-link">📉 黄金の指値ボード</a>
        <a href="{{ site_root }}high-hunter/index.html" class="nav-link">📈 黄金の空売りボード</a>
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
        <a href="{{ site_root }}screener/index.html" class="nav-link">🔥 スクリーナー</a>
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
                <th class="vol-col" colspan="3">ボラティリティ</th>
                <th class="volume-col">平均出来高</th>
                <th class="conditions-col">達成条件</th>
            </tr>
            <tr class="sub-header">
                <th></th><th></th><th></th><th></th><th></th>
                <th class="vol-sub-col">ATR(10)</th>
                <th class="vol-sub-col">ATR(20)</th>
                <th class="vol-sub-col">傾向</th>
                <th></th><th></th>
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
                <td class="vol-sub-col">
                    {% if signal.volatility_category_10 is defined and signal.volatility_category_10 %}
                    <span class="vol-badge vol-{{ signal.volatility_category_10 }}" {% if signal.volatility_pattern is defined and signal.volatility_pattern %}title="{{ signal.volatility_pattern }}"{% endif %}>
                        {% if signal.volatility_category_10 == 'high' %}高{% elif signal.volatility_category_10 == 'mid' %}中{% else %}低{% endif %}
                    </span>
                    {% else %}-{% endif %}
                </td>
                <td class="vol-sub-col">
                    {% if signal.volatility_category_20 is defined and signal.volatility_category_20 %}
                    <span class="vol-badge vol-{{ signal.volatility_category_20 }}">
                        {% if signal.volatility_category_20 == 'high' %}高{% elif signal.volatility_category_20 == 'mid' %}中{% else %}低{% endif %}
                    </span>
                    {% else %}-{% endif %}
                </td>
                <td class="vol-sub-col">
                    {% if signal.volatility_trend is defined and signal.volatility_trend %}
                        {% if signal.volatility_trend == 'expanding' %}
                        <span class="trend-badge trend-expanding">🔺 拡大</span>
                        {% elif signal.volatility_trend == 'contracting' %}
                        <span class="trend-badge trend-contracting">🔻 縮小</span>
                        {% else %}
                        <span class="trend-badge trend-stable">➡️ 横ばい</span>
                        {% endif %}
                    {% else %}-{% endif %}
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
    .approaching-table .score-col,
    .approaching-table .vol-sub-col {
        text-align: center;
    }
    .sub-header th {
        font-size: 0.75rem;
        font-weight: 500;
        color: #9ca3af;
        padding: 0.2rem 0.5rem;
        border-top: none;
    }
    .vol-col {
        text-align: center;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
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
    .vol-badge {
        display: inline-block;
        padding: 0.2rem 0.5rem;
        border-radius: 10px;
        font-size: 0.8rem;
        font-weight: bold;
        min-width: 2rem;
        text-align: center;
        cursor: help;
    }
    .vol-badge.vol-high {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
    }
    .vol-badge.vol-mid {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
    }
    .vol-badge.vol-low {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    .trend-badge {
        font-size: 0.8rem;
        padding: 0.2rem 0.4rem;
        border-radius: 8px;
        white-space: nowrap;
    }
    .trend-badge.trend-expanding {
        background: #fef2f2;
        color: #991b1b;
    }
    .trend-badge.trend-contracting {
        background: #eff6ff;
        color: #1e40af;
    }
    .trend-badge.trend-stable {
        background: #f9fafb;
        color: #6b7280;
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


def generate_screener_html():
    """ボラティリティ乖離スクリーナーページのテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}ボラティリティスクリーナー - Stock Strategy Analyzer{% endblock %}

{% block content %}
<section class="hero screener-hero">
    <h1>🔥 ボラティリティ乖離スクリーナー</h1>
    <p class="hero-sub">ATR急拡大 × 需給健全な銘柄の逆張りエントリー早見表</p>

    <div class="nav-links">
        <a href="{{ site_root }}index.html" class="nav-link">📊 適合度ランキング</a>
        <a href="{{ site_root }}approaching/index.html" class="nav-link">🎯 シグナル接近中</a>
        <a href="{{ site_root }}screener/index.html" class="nav-link active">🔥 ボラティリティスクリーナー</a>
        <a href="{{ site_root }}low-hunter/index.html" class="nav-link">📉 黄金の指値ボード</a>
        <a href="{{ site_root }}high-hunter/index.html" class="nav-link">📈 黄金の空売りボード</a>
    </div>
</section>

<section class="screener-control">
    <div class="risk-input-group">
        <label for="risk-input">許容損失額</label>
        <div class="input-wrapper">
            <input type="number" id="risk-input" value="3" min="0.1" max="100" step="0.1" inputmode="decimal">
            <span class="input-unit">万円</span>
        </div>
        <span class="risk-hint" id="risk-display">3万円</span>
    </div>
    <div style="margin-top:0.5rem; text-align:center;">
        <label style="cursor:pointer; font-size:0.9rem; color:#cbd5e1;">
            <input type="checkbox" id="subunit-checkbox" style="margin-right: 0.5rem;">単元未満株（1株単位）での購入を想定する
        </label>
    </div>
</section>

<section class="screener-info">
    <details class="criteria-details">
        <summary class="criteria-summary">📋 スクリーナーの仕組み</summary>
        <div class="criteria-content">
            <div class="criteria-grid">
                <div class="criteria-item">
                    <h4>🚦 三段階フィルタ</h4>
                    <ul>
                        <li>Stage1: 平均出来高 ≥ 50万株、仕手化排除</li>
                        <li>Stage2: 正規化ATR ≥ {{ screener_params.min_norm_atr }}% → RVR降順ランキング</li>
                        <li>Stage3: ケルトナーターゲット価格 + ポジションサイジング</li>
                    </ul>
                </div>
                <div class="criteria-item">
                    <h4>💰 等リスク配分</h4>
                    <ul>
                        <li>どの銘柄が損切りでも損失が X 万円に収まる株数</li>
                        <li>100株単位で切り捨て</li>
                        <li>「未満株」はリスク額に対してATRが大きすぎる場合</li>
                    </ul>
                </div>
            </div>
        </div>
    </details>
</section>

{% macro render_screener_table(table_stocks, table_id) %}
    {% if table_stocks %}
    <div class="table-scroll">
        <table class="screener-table" id="screener-table-{{ table_id }}">
            <thead>
                <tr>
                    <th class="col-rank sortable" data-sort-key="rank"># <span class="sort-icon"></span></th>
                    <th class="col-ticker sortable" data-sort-key="ticker">コード <span class="sort-icon"></span></th>
                    <th class="col-name">銘柄名</th>
                    <th class="col-rvr sortable" data-sort-key="rvr">相対ボラ(RVR) <span class="sort-icon"></span></th>
                    <th class="col-natr sortable" data-sort-key="natr">標準化ATR <span class="sort-icon"></span></th>
                    <th class="col-price sortable" data-sort-key="price">現在値 <span class="sort-icon"></span></th>
                    <th class="col-target sortable" data-sort-key="target">目標買値 <span class="sort-icon"></span></th>
                    <th class="col-prox sortable" data-sort-key="prox">近接度 <span class="sort-icon"></span></th>
                    <th class="col-qty sortable" data-sort-key="qty">買付株数 <span class="sort-icon"></span></th>
                    <th class="col-stop sortable" data-sort-key="stop">損切価格 <span class="sort-icon"></span></th>
                    <th class="col-cap sortable" data-sort-key="cap">必要資金 <span class="sort-icon"></span></th>
                    <th class="col-status sortable" data-sort-key="status">トレンド <span class="sort-icon"></span></th>
                </tr>
            </thead>
            <tbody id="screener-tbody-{{ table_id }}">
                {% for stock in table_stocks %}
                <tr data-table-id="{{ table_id }}" data-idx="{{ loop.index0 }}">
                    <td class="col-rank">{{ stock.rank }}</td>
                    <td class="col-ticker">{{ stock.ticker }}</td>
                    <td class="col-name">{{ stock.name }}</td>
                    <td class="col-rvr">{{ "%.2f"|format(stock.rvr) }}</td>
                    <td class="col-natr">{{ "%.1f"|format(stock.norm_atr) }}%</td>
                    <td class="col-price">¥{{ stock.current_price|number_format }}</td>
                    <td class="col-target">¥{{ stock.target_buy|number_format }}</td>
                    <td class="col-prox {% if stock.is_proximity_alert %}prox-alert{% endif %}">
                        {{ "%.1f"|format(stock.proximity_pct) }}%
                    </td>
                    <td class="col-qty js-quantity {% if stock.is_sub_unit %}sub-unit{% endif %}">
                        {% if stock.is_sub_unit %}未満株{% else %}{{ stock.quantity|number_format }}{% endif %}
                    </td>
                    <td class="col-stop">¥{{ stock.stop_loss|number_format }}</td>
                    <td class="col-cap js-capital">
                        {% if stock.is_sub_unit %}-{% else %}¥{{ stock.capital|number_format }}{% endif %}
                    </td>
                    {% set status_map = {'Up':'上昇', 'Down':'下落', 'Range':'レンジ', 'Sideways':'横ばい'} %}
                    <td class="col-status">
                        <span class="status-badge status-{{ stock.status|lower }}">{{ status_map.get(stock.status, stock.status) }}</span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <div class="no-data">
        <p>該当する銘柄がありません。</p>
    </div>
    {% endif %}
{% endmacro %}

<section class="screener-results">
    <h3 style="color:white; margin:1rem 0; padding-left:1rem; border-left:4px solid #f97316;">🔥 動態急拡大銘柄（RVR順・中小型メイン）</h3>
    {{ render_screener_table(stocks_dynamic, 'dynamic') }}

    <h3 style="color:white; margin:3rem 0 1rem 0; padding-left:1rem; border-left:4px solid #3b82f6;">🌊 大型ハイボラ銘柄ターゲット（Norm_ATR順・売買代金100億円以上）</h3>
    {{ render_screener_table(stocks_large_cap, 'large_cap') }}
</section>

{% if stocks_dynamic or stocks_large_cap %}
<script>
window.SCREENER_DATA = {{ screener_json|safe }};
</script>
<script src="{{ static_root }}static/js/screener.js"></script>
{% endif %}

<style>
    .screener-hero {
        padding: 3rem 1rem;
    }
    .nav-links {
        margin-top: 1.5rem;
        display: flex;
        gap: 0.75rem;
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
        font-size: 0.9rem;
    }
    .nav-link:hover { background: rgba(255, 255, 255, 0.2); }
    .nav-link.active { background: rgba(255, 255, 255, 0.25); font-weight: bold; }

    /* --- Risk Input --- */
    .screener-control {
        margin: 1.5rem 0;
        display: flex;
        justify-content: center;
    }
    .risk-input-group {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 0.75rem 1.25rem;
    }
    .risk-input-group label {
        color: #94a3b8;
        font-size: 0.9rem;
        white-space: nowrap;
    }
    .input-wrapper {
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }
    #risk-input {
        width: 5rem;
        padding: 0.4rem 0.6rem;
        border: 1px solid #475569;
        border-radius: 8px;
        background: #0f172a;
        color: #f1f5f9;
        font-size: 1.1rem;
        font-weight: 600;
        text-align: right;
    }
    #risk-input:focus {
        outline: none;
        border-color: #f97316;
        box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.3);
    }
    .input-unit { color: #94a3b8; font-size: 0.9rem; }
    .risk-hint {
        color: #f97316;
        font-weight: 600;
        font-size: 0.9rem;
        min-width: 5rem;
    }

    /* --- Table --- */
    .table-scroll {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
    .screener-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }
    .screener-table th,
    .screener-table td {
        padding: 0.6rem 0.5rem;
        text-align: right;
        white-space: nowrap;
        border-bottom: 1px solid #1e293b;
    }
    .screener-table th {
        background: #0f172a;
        color: #94a3b8;
        font-weight: 500;
        position: sticky;
        top: 0;
        z-index: 1;
    }
    .screener-table th.sortable {
        cursor: pointer;
        user-select: none;
        transition: background-color 0.2s;
    }
    .screener-table th.sortable:hover {
        background-color: #1e293b;
        color: #f1f5f9;
    }
    .sort-icon {
        font-size: 0.8rem;
        margin-left: 0.25rem;
        opacity: 0.4;
    }
    th.asc .sort-icon::before { content: "▲"; opacity: 1; color: #38bdf8; }
    th.desc .sort-icon::before { content: "▼"; opacity: 1; color: #38bdf8; }
    th:not(.asc):not(.desc) .sort-icon::before { content: "↕"; }
    .screener-table tbody tr:hover {
        background: #1e293b;
    }
    .col-rank { text-align: center; width: 2.5rem; }
    .col-ticker { text-align: left; font-weight: 600; color: #60a5fa; }
    .col-name { text-align: left; max-width: 10rem; overflow: hidden; text-overflow: ellipsis; }
    .col-rvr { color: #fbbf24; font-weight: 600; }
    .col-natr { color: #a78bfa; }
    .col-target { color: #34d399; }
    .col-stop { color: #f87171; }

    .prox-alert {
        color: #ef4444 !important;
        font-weight: 700;
        animation: pulse-red 1.5s ease-in-out infinite;
    }
    @keyframes pulse-red {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }
    .sub-unit {
        color: #6b7280;
        font-style: italic;
    }

    /* Status badges */
    .status-badge {
        padding: 0.2rem 0.5rem;
        border-radius: 8px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .status-range { background: #065f46; color: #6ee7b7; }
    .status-up { background: #1e40af; color: #93c5fd; }
    .status-down { background: #991b1b; color: #fca5a5; }
    .status-sideways { background: #374151; color: #9ca3af; }

    /* --- Criteria --- */
    .screener-info { margin: 1rem 0; }
    .no-data { text-align: center; padding: 3rem; color: #6b7280; }

    /* --- Mobile --- */
    @media (max-width: 768px) {
        .screener-table { font-size: 0.75rem; }
        .screener-table th, .screener-table td { padding: 0.4rem 0.3rem; }
        .col-name { max-width: 6rem; }
        .risk-input-group { flex-wrap: wrap; justify-content: center; }
    }
</style>
{% endblock %}'''


def generate_low_hunter_html():
    """Low Hunterページのテンプレート"""
    template_path = PROJECT_ROOT / 'web' / 'templates' / 'low_hunter.html'
    if not template_path.exists():
        return ''

    html = template_path.read_text(encoding='utf-8')
    html = html.replace('extends "base.html"', 'extends "static_base.html"')
    import re
    html = re.sub(r"{{ url_for.*?\s*}}", "{{ static_root }}static/js/low_hunter.js", html)
    return html


def generate_high_hunter_html():
    """High Hunterページのテンプレート"""
    template_path = PROJECT_ROOT / 'web' / 'templates' / 'high_hunter.html'
    if not template_path.exists():
        return ''

    html = template_path.read_text(encoding='utf-8')
    html = html.replace('extends "base.html"', 'extends "static_base.html"')
    import re
    html = re.sub(r"{{ url_for.*?\s*}}", "{{ static_root }}static/js/high_hunter.js", html)
    return html

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
    (static_templates_dir / 'static_screener.html').write_text(
        generate_screener_html(), encoding='utf-8'
    )
    (static_templates_dir / 'static_low_hunter.html').write_text(
        generate_low_hunter_html(), encoding='utf-8'
    )
    (static_templates_dir / 'static_high_hunter.html').write_text(
        generate_high_hunter_html(), encoding='utf-8'
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
    logger.info('\n[1/5] トップページ生成')
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
    logger.info('\n[2/5] 戦略別ランキングページ生成')
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
    logger.info('\n[3/5] 接近シグナル一覧ページ生成')
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
    logger.info('\n[4/5] 戦略別接近シグナルページ生成')
    for name in approaching_strategies:
        signals = cache.load_approaching_signals(name, limit=50)

        render_template(env, 'static_approaching_strategy.html',
                        DOCS_DIR / 'approaching' / f'{safe_filename(name)}.html',
                        strategy_name=name,
                        strategy_name_encoded=safe_filename(name),
                        signals=signals, **sub_ctx)

    # === 5. ボラティリティスクリーナーページ ===
    logger.info('\n[5/5] ボラティリティスクリーナーページ生成')
    screener_data = cache.load_screener_result()
    if screener_data and (screener_data.get('stocks') or screener_data.get('stocks_large_cap')):
        stocks_dynamic = screener_data.get('stocks', [])
        stocks_large_cap = screener_data.get('stocks_large_cap', [])
        screener_params = screener_data.get('parameters', {})
        # JS用JSONデータ
        screener_json = json.dumps({
            'stocks_dynamic': stocks_dynamic,
            'stocks_large_cap': stocks_large_cap,
            'keltner_multiplier': screener_params.get('keltner_multiplier', 2.0),
        }, ensure_ascii=False)

        render_template(env, 'static_screener.html',
                        DOCS_DIR / 'screener' / 'index.html',
                        stocks_dynamic=stocks_dynamic,
                        stocks_large_cap=stocks_large_cap,
                        screener_params=screener_params,
                        screener_json=screener_json,
                        **sub_ctx)
    else:
        logger.info('  スクリーナーデータなし（スキップ）')

    # === 6. Low Hunter（黄金の指値ボード）ページ ===
    logger.info('\n[6/7] Low Hunter ページ生成')
    lh_data = cache.load_low_hunter_result()
    if lh_data and lh_data.get('stocks'):
        lh_stocks = lh_data['stocks']
        lh_params = lh_data.get('parameters', {})
        lh_json = json.dumps({
            'stocks': lh_stocks,
        }, ensure_ascii=False)

        render_template(env, 'static_low_hunter.html',
                        DOCS_DIR / 'low-hunter' / 'index.html',
                        stocks=lh_stocks,
                        parameters=lh_params,
                        lh_json=lh_json,
                        **sub_ctx)
    else:
        logger.info('  Low Hunterデータなし（スキップ）')

    # === 7. High Hunter（黄金の空売りボード）ページ ===
    logger.info('\n[7/7] High Hunter ページ生成')
    hh_data = cache.load_high_hunter_result()
    if hh_data and hh_data.get('stocks'):
        hh_stocks = hh_data['stocks']
        hh_params = hh_data.get('parameters', {})
        hh_json = json.dumps({
            'stocks': hh_stocks,
        }, ensure_ascii=False)

        render_template(env, 'static_high_hunter.html',
                        DOCS_DIR / 'high-hunter' / 'index.html',
                        stocks=hh_stocks,
                        parameters=hh_params,
                        hh_json=hh_json,
                        **sub_ctx)
    else:
        logger.info('  High Hunterデータなし（スキップ）')

    # 一時テンプレートを削除
    shutil.rmtree(static_templates_dir)

    # 生成結果サマリ
    generated = list(DOCS_DIR.rglob('*.html'))
    logger.info(f'\n=== 生成完了: {len(generated)}ページ ===')
    for p in sorted(generated):
        logger.info(f'  {p.relative_to(DOCS_DIR)}')


if __name__ == '__main__':
    generate_all()
