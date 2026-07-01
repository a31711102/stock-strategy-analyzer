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
from src.data.market_segments import load_market_map, is_prime

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# 設定
RESULTS_DIR = PROJECT_ROOT / 'results'
DOCS_DIR = PROJECT_ROOT / 'docs'
TEMPLATES_DIR = PROJECT_ROOT / 'web' / 'templates'
STATIC_DIR = PROJECT_ROOT / 'web' / 'static'
STOCK_LIST_PATH = PROJECT_ROOT / 'data_j.xls'

MIN_SCORE_THRESHOLD = 40.0

# 市場フィルタのバリエーション: (ファイル名サフィックス, 表示ラベル)
MARKET_VARIANTS = [('', '全市場'), ('_prime', '東証プライム')]


def filter_prime(items: list, market_map: dict) -> list:
    """東証プライム銘柄のみに絞り込み、順位を振り直す（元リストは変更しない）"""
    filtered = []
    for item in items:
        segment = item.get('market') or market_map.get(str(item.get('code', '')), '')
        if is_prime(segment):
            filtered.append(dict(item))

    for i, item in enumerate(filtered, 1):
        item['rank'] = i

    return filtered


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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body>
    <header class="header">
        <div class="container">
            <a href="{{ site_root }}index.html" class="logo">
                <span class="logo-icon">S</span>
                <span>Stock Strategy Analyzer</span>
            </a>
            <nav class="nav">
                <a href="{{ site_root }}low-hunter/index.html" class="nav-link">📉 黄金の指値ボード</a>
                <a href="{{ site_root }}high-hunter/index.html" class="nav-link">📈 黄金の空売りボード</a>
                <a href="{{ site_root }}pairs-hunter/index.html" class="nav-link">⚖️ ペアトレード・ボード</a>
            </nav>
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

{% block title %}今日のおすすめ候補 - Stock Strategy Analyzer{% endblock %}

{% block content %}
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
    <div style="font-size:12px;font-weight:700;letter-spacing:.14em;color:#4338CA;text-transform:uppercase">COCKPIT · 司令塔</div>
    <div class="market-filter">
        <a href="{{ site_root }}index.html" class="market-tab {{ 'active' if not market_suffix else '' }}">全市場</a>
        <a href="{{ site_root }}index_prime.html" class="market-tab {{ 'active' if market_suffix else '' }}">東証プライム</a>
    </div>
</div>

<div style="background:#F4F5F7; padding: 26px 28px 28px; border-radius: 14px; border: 1px solid var(--border);">
    <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:4px">
        <h2 style="font-size:22px;font-weight:700;letter-spacing:-.01em">今日のおすすめ候補</h2>
        <span style="font-size:12.5px;color:#7A828F">全機能を横断したエントリー候補（{{ last_updated }} 時点）</span>
    </div>
    <div style="height:1px;background:#E4E7EC;margin:14px 0 20px"></div>

    <div class="cockpit-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:22px">
        <!-- DAYTRADE column -->
        <div>
            <div style="display:flex;align-items:center;gap:9px;margin-bottom:13px">
                <span style="width:9px;height:9px;border-radius:50%;background:#D97706"></span>
                <span style="font-weight:700;font-size:15px">デイトレ・当日</span>
                <span style="font-size:11.5px;color:#C2740A;background:#FBF0DF;border:1px solid #F0DCBE;padding:1.5px 8px;border-radius:20px;font-weight:600">本日の指値で仕込む</span>
            </div>

            <!-- 指値ボード(買い) -->
            <div style="background:#fff;border:1px solid #E4E7EC;border-radius:12px;padding:14px 16px;margin-bottom:14px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <span style="font-weight:700;font-size:13.5px">黄金の指値ボード <span style="color:#15803D">▲買い</span></span>
                    <a href="{{ site_root }}low-hunter/index.html" style="font-size:12px;color:#5A6172;text-decoration:none">全件を見る →</a>
                </div>
                <div style="display:grid;grid-template-columns:20px 44px minmax(0,1fr) 54px 82px;gap:8px;font-size:10.5px;color:#98A0AE;font-weight:600;padding:0 2px 5px;border-bottom:1px solid #E4E7EC">
                    <span></span><span>コード</span><span>銘柄名</span><span style="text-align:right">勝率</span><span style="text-align:right">指値</span>
                </div>
                {% if low_hunter_top3 %}
                    {% for r in low_hunter_top3 %}
                    <div style="display:grid;grid-template-columns:20px 44px minmax(0,1fr) 54px 82px;gap:8px;align-items:center;font-size:13px;padding:8px 2px;border-bottom:1px solid #F1F3F5">
                        <span style="color:#B58A1B;font-weight:700;font-variant-numeric:tabular-nums">{{ loop.index }}</span>
                        <a href="https://finance.yahoo.co.jp/quote/{{ r.ticker }}.T" target="_blank" style="font-family:Inter,sans-serif;color:#C2740A;font-weight:600;font-variant-numeric:tabular-nums;text-decoration:none;">{{ r.ticker }}</a>
                        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ r.name }}</span>
                        <span style="text-align:right;color:#15803D;font-weight:600;font-variant-numeric:tabular-nums">{{ "%.1f"|format(r.win_rate) if r.win_rate is not none else '-' }}%</span>
                        <span style="text-align:right;font-weight:600;font-variant-numeric:tabular-nums">¥{{ "{:,.0f}".format(r.target_price|int) if r.target_price is not none else '-' }}</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div style="font-size:12px;color:#98A0AE;text-align:center;padding:10px 0;">候補がありません</div>
                {% endif %}
            </div>

            <!-- 空売りボード(売り) -->
            <div style="background:#fff;border:1px solid #E4E7EC;border-radius:12px;padding:14px 16px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <span style="font-weight:700;font-size:13.5px">黄金の空売りボード <span style="color:#C03434">▼売り</span></span>
                    <a href="{{ site_root }}high-hunter/index.html" style="font-size:12px;color:#5A6172;text-decoration:none">全件を見る →</a>
                </div>
                <div style="display:grid;grid-template-columns:20px 44px minmax(0,1fr) 54px 82px;gap:8px;font-size:10.5px;color:#98A0AE;font-weight:600;padding:0 2px 5px;border-bottom:1px solid #E4E7EC">
                    <span></span><span>コード</span><span>銘柄名</span><span style="text-align:right">勝率</span><span style="text-align:right">空売り</span>
                </div>
                {% if high_hunter_top3 %}
                    {% for r in high_hunter_top3 %}
                    <div style="display:grid;grid-template-columns:20px 44px minmax(0,1fr) 54px 82px;gap:8px;align-items:center;font-size:13px;padding:8px 2px;border-bottom:1px solid #F1F3F5">
                        <span style="color:#B58A1B;font-weight:700;font-variant-numeric:tabular-nums">{{ loop.index }}</span>
                        <a href="https://finance.yahoo.co.jp/quote/{{ r.ticker }}.T" target="_blank" style="font-family:Inter,sans-serif;color:#C2740A;font-weight:600;font-variant-numeric:tabular-nums;text-decoration:none;">{{ r.ticker }}</a>
                        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ r.name }}</span>
                        <span style="text-align:right;color:#15803D;font-weight:600;font-variant-numeric:tabular-nums">{{ "%.1f"|format(r.win_rate) if r.win_rate is not none else '-' }}%</span>
                        <span style="text-align:right;font-weight:600;font-variant-numeric:tabular-nums">¥{{ "{:,.0f}".format(r.target_price|int) if r.target_price is not none else '-' }}</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div style="font-size:12px;color:#98A0AE;text-align:center;padding:10px 0;">候補がありません</div>
                {% endif %}
            </div>
        </div>

        <!-- SWING column -->
        <div>
            <div style="display:flex;align-items:center;gap:9px;margin-bottom:13px">
                <span style="width:9px;height:9px;border-radius:50%;background:#4338CA"></span>
                <span style="font-weight:700;font-size:15px">スイング・中長期</span>
                <span style="font-size:11.5px;color:#4338CA;background:#EEF0FB;border:1px solid #D9DCF6;padding:1.5px 8px;border-radius:20px;font-weight:600">数日〜数週で狙う</span>
            </div>

            <!-- シグナル接近中 -->
            <div style="background:#fff;border:1px solid #E4E7EC;border-radius:12px;padding:14px 16px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <span style="font-weight:700;font-size:13.5px">シグナル接近中</span>
                    <a href="{{ site_root }}approaching/index{{ market_suffix }}.html" style="font-size:12px;color:#5A6172;text-decoration:none">全件を見る →</a>
                </div>
                <div style="display:grid;grid-template-columns:minmax(0,108px) 44px minmax(0,1fr) 72px;gap:8px;font-size:10.5px;color:#98A0AE;font-weight:600;padding:0 2px 5px;border-bottom:1px solid #E4E7EC">
                    <span>戦略</span><span>コード</span><span>銘柄名</span><span style="text-align:right">発生まで</span>
                </div>
                {% if approaching_top %}
                    {% for r in approaching_top %}
                    <div style="display:grid;grid-template-columns:minmax(0,108px) 44px minmax(0,1fr) 72px;gap:8px;align-items:center;font-size:13px;padding:8px 2px;border-bottom:1px solid #F1F3F5">
                        <span style="color:#4338CA;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px">{{ r.strat }}</span>
                        <a href="https://finance.yahoo.co.jp/quote/{{ r.code }}.T" target="_blank" style="font-family:Inter,sans-serif;color:#5A6172;font-weight:600;font-variant-numeric:tabular-nums;text-decoration:none;">{{ r.code }}</a>
                        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ r.name }}</span>
                        <span style="text-align:right;color:#C2740A;font-weight:600;font-size:12px">約{{ r.estimated_days or '?' }}日後</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div style="font-size:12px;color:#98A0AE;text-align:center;padding:10px 0;">接近中の銘柄はありません</div>
                {% endif %}
            </div>
        </div>
    </div>

    <!-- secondary nav -->
    <div style="display:flex;align-items:center;gap:10px;margin-top:22px;padding-top:16px;border-top:1px solid #E4E7EC;flex-wrap:wrap">
        <span style="font-size:12px;color:#98A0AE">その他:</span>
        <a href="{{ site_root }}pairs-hunter/index.html" style="font-size:12.5px;color:#5A6172;background:#fff;border:1px solid #E4E7EC;padding:5px 12px;border-radius:8px;text-decoration:none;">⚖️ ペアトレード・ボード</a>
        {% if strategies %}
            {% set first_strat = strategies[0].name_encoded %}
            <a href="{{ site_root }}strategy/{{ first_strat }}{{ market_suffix }}.html" style="font-size:12.5px;color:#5A6172;background:#fff;border:1px solid #E4E7EC;padding:5px 12px;border-radius:8px;text-decoration:none;">適合度ランキング</a>
        {% endif %}
    </div>

</div>

<style>
    @media (max-width: 768px) {
        .cockpit-grid {
            grid-template-columns: 1fr !important;
        }
    }
</style>
{% endblock %}'''


def generate_strategy_ranking_html():
    """戦略別ランキングページのテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}{{ strategy_name }} ランキング - Stock Strategy Analyzer{% endblock %}

{% block content %}
<nav class="breadcrumb">
    <a href="{{ site_root }}index{{ market_suffix }}.html">SSA</a>
    <span class="sep">/</span>
    <span>スイング</span>
    <span class="sep">/</span>
    <span>適合度ランキング</span>
    <span class="sep">/</span>
    <span class="current">{{ strategy_name }}</span>
</nav>

<section class="ranking-section">
    <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:18px; flex-wrap:wrap; gap:12px;">
        <div>
            <h2 style="font-size:21px; font-weight:700;">{{ strategy_name }}</h2>
            <div style="font-size:13px; color:#5A6172; margin-top:2px;">適合度ランキング Top {{ rankings|length }}{{ '（東証プライム）' if market_suffix else '' }}</div>
        </div>
        <div class="market-filter">
            <a href="{{ site_root }}strategy/{{ strategy_name_encoded }}.html" class="market-tab {{ 'active' if not market_suffix else '' }}">全市場</a>
            <a href="{{ site_root }}strategy/{{ strategy_name_encoded }}_prime.html" class="market-tab {{ 'active' if market_suffix else '' }}">東証プライム</a>
        </div>
    </div>

    <div class="strategy-nav">
        {% for s in strategies %}
        <a href="{{ site_root }}strategy/{{ s.encoded }}{{ market_suffix }}.html"
            class="strategy-tab {{ 'active' if s.name == strategy_name else '' }}">
            {{ s.name }}
        </a>
        {% endfor %}
    </div>

    {% if rankings %}
    <div style="background:#fff; border:1px solid #E4E7EC; border-radius:12px; overflow:hidden;">
        <div style="overflow-x:auto;">
            <table style="font-size:13px;">
                <thead>
                    <tr style="background:#FAFBFC; color:#5A6172; font-size:11.5px;">
                        <th style="padding:9px 12px; text-align:center; font-weight:600; width:80px;">順位</th>
                        <th style="padding:9px 12px; text-align:left; font-weight:600; width:100px;">コード</th>
                        <th style="padding:9px 12px; text-align:left; font-weight:600;">銘柄名</th>
                        <th style="padding:9px 12px; text-align:right; font-weight:600; width:180px;">スコア</th>
                        <th style="padding:9px 12px; text-align:left; font-weight:600;">主要条件</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in rankings %}
                    <tr style="background: {{ '#FFFFFF' if loop.index0 % 2 == 0 else '#FBFBFC' }};">
                        <td style="padding:11px 12px; text-align:center;">
                            <span style="display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:50%; font-weight:700; font-size:11px;
                                {% if item.rank == 1 %}background:#FBF3DC; color:#B58A1B; border:1px solid #F0DCBE;
                                {% elif item.rank == 2 %}background:#F1F2F4; color:#5A6172; border:1px solid #E4E7EC;
                                {% elif item.rank == 3 %}background:#EEF0FB; color:#4338CA; border:1px solid #D9DCF6;
                                {% else %}background:transparent; color:#98A0AE;{% endif %}">
                                {{ item.rank }}
                            </span>
                        </td>
                        <td style="padding:11px 12px;">
                            <a href="https://finance.yahoo.co.jp/quote/{{ item.code }}.T" target="_blank" style="font-family:Inter,sans-serif; color:#C2740A; font-weight:600; text-decoration:none;">
                                {{ item.code }}
                            </a>
                        </td>
                        <td style="padding:11px 12px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{{ item.name }}</td>
                        <td style="padding:11px 12px; text-align:right;">
                            <div style="display:flex; align-items:center; gap:8px; justify-content:flex-end;">
                                <div style="width:70px; height:6px; background:#EEF0FB; border-radius:3px; overflow:hidden; display:inline-block;">
                                    <div style="height:100%; background:var(--accent-primary); width: {{ item.score }}%"></div>
                                </div>
                                <span style="font-weight:700; font-variant-numeric:tabular-nums; color:var(--accent-primary);">{{ "%.1f"|format(item.score) }}%</span>
                            </div>
                        </td>
                        <td style="padding:11px 12px; color:#5A6172;">
                            <span style="font-size:12px;">{{ item.reason.split('\\n')[0] if item.reason else '' }}</span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% else %}
    <div style="text-align: center; padding: 4rem; color: var(--text-secondary); background: var(--bg-card); border-radius: 12px; border: 1px dashed var(--border);">
        <p>該当する適合銘柄がありませんでした。</p>
    </div>
    {% endif %}
</section>
{% endblock %}'''


def generate_approaching_index_html():
    """接近シグナル一覧ページのテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}シグナル接近中 - Stock Strategy Analyzer{% endblock %}

{% block content %}
<nav class="breadcrumb">
    <a href="{{ site_root }}index{{ market_suffix }}.html">SSA</a>
    <span class="sep">/</span>
    <span>スイング</span>
    <span class="sep">/</span>
    <span class="current">シグナル接近中</span>
</nav>

<section class="approaching-section">
    <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:18px; flex-wrap:wrap; gap:12px;">
        <div>
            <h2 style="font-size:21px; font-weight:700;">🎯 シグナル接近中の銘柄</h2>
            <div style="font-size:13px; color:#5A6172; margin-top:2px;">近日中にエントリー条件を満たすと予想される銘柄</div>
        </div>
        <div class="market-filter">
            <a href="{{ site_root }}approaching/index.html" class="market-tab {{ 'active' if not market_suffix else '' }}">全市場</a>
            <a href="{{ site_root }}approaching/index_prime.html" class="market-tab {{ 'active' if market_suffix else '' }}">東証プライム</a>
        </div>
    </div>

    {% if strategies %}
    <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap:18px;">
        {% for strategy in strategies %}
        <div style="background:#fff; border:1px solid #E4E7EC; border-radius:12px; padding:16px 18px; border-left:4px solid var(--accent-primary); display:flex; flex-direction:column; justify-content:space-between; min-height:160px; position:relative;">
            <div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <h3 style="font-size:15px; font-weight:700; color:var(--text-primary);">{{ strategy.name }}</h3>
                </div>

                {% if strategy.top3 %}
                <div style="display:flex; flex-direction:column; gap:8px;">
                    {% for item in strategy.top3 %}
                    <div style="display:grid; grid-template-columns: 24px 44px minmax(0, 1fr) auto; gap:8px; align-items:center; font-size:13px; padding-bottom:6px; border-bottom:1px solid #F1F3F5;">
                        <span style="color:#98A0AE; font-weight:600; font-size:11px;">#{{ loop.index }}</span>
                        <span style="font-family:Inter,sans-serif; color:#5A6172; font-weight:600; font-variant-numeric:tabular-nums;">{{ item.code }}</span>
                        <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{{ item.name }}</span>
                        <span style="font-size:11px; font-weight:700; color:#C2740A; background:#FBF0DF; border:1px solid #F0DCBE; padding:1px 6px; border-radius:10px; font-variant-numeric:tabular-nums;">
                            約{{ item.estimated_days or '?' }}日後
                        </span>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <div style="color:#98A0AE; font-size:12.5px; text-align:center; padding:20px 0;">接近中の銘柄はありません</div>
                {% endif %}
            </div>
            
            <div style="margin-top:14px; text-align:right;">
                <a href="{{ site_root }}approaching/{{ strategy.name_encoded }}{{ market_suffix }}.html" style="font-size:12px; color:var(--accent-primary); text-decoration:none; font-weight:600;">
                    すべての接近銘柄を見る →
                </a>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div style="text-align: center; padding: 4rem; color: var(--text-secondary); background: var(--bg-card); border-radius: 12px; border: 1px dashed var(--border);">
        <p>接近シグナルのデータがありません。</p>
    </div>
    {% endif %}
</section>
{% endblock %}'''


def generate_approaching_strategy_html():
    """戦略別接近シグナルページのテンプレート"""
    return '''{% extends "static_base.html" %}

{% block title %}{{ strategy_name }} 接近シグナル - Stock Strategy Analyzer{% endblock %}

{% block content %}
<nav class="breadcrumb">
    <a href="{{ site_root }}index{{ market_suffix }}.html">SSA</a>
    <span class="sep">/</span>
    <a href="{{ site_root }}approaching/index{{ market_suffix }}.html">シグナル接近中</a>
    <span class="sep">/</span>
    <span class="current">{{ strategy_name }}</span>
</nav>

<section class="ranking-section">
    <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:18px; flex-wrap:wrap; gap:12px;">
        <div>
            <h2 style="font-size:21px; font-weight:700;">🎯 {{ strategy_name }}</h2>
            <div style="font-size:13px; color:#5A6172; margin-top:2px;">シグナル接近中の銘柄（Top 50・出来高50万以上{{ '・東証プライム' if market_suffix else '' }}）</div>
        </div>
        <div class="market-filter">
            <a href="{{ site_root }}approaching/{{ strategy_name_encoded }}.html" class="market-tab {{ 'active' if not market_suffix else '' }}">全市場</a>
            <a href="{{ site_root }}approaching/{{ strategy_name_encoded }}_prime.html" class="market-tab {{ 'active' if market_suffix else '' }}">東証プライム</a>
        </div>
    </div>

    {% if signals %}
    <div style="background:#fff; border:1px solid #E4E7EC; border-radius:12px; overflow:hidden;">
        <div style="overflow-x:auto;">
            <table style="font-size:13px;">
                <thead>
                    <tr style="background:#FAFBFC; color:#5A6172; font-size:11.5px;">
                        <th style="padding:9px 12px; text-align:center; font-weight:600; width:60px;">順位</th>
                        <th style="padding:9px 12px; text-align:left; font-weight:600; width:90px;">コード</th>
                        <th style="padding:9px 12px; text-align:left; font-weight:600;">銘柄名</th>
                        <th style="padding:9px 12px; text-align:center; font-weight:600; width:100px;">推定日数</th>
                        <th style="padding:9px 12px; text-align:center; font-weight:600; width:90px;">接近度</th>
                        <th style="padding:9px 12px; text-align:center; font-weight:600; width:80px;">ATR(10)</th>
                        <th style="padding:9px 12px; text-align:center; font-weight:600; width:80px;">ATR(20)</th>
                        <th style="padding:9px 12px; text-align:center; font-weight:600; width:90px;">ボラ傾向</th>
                        <th style="padding:9px 12px; text-align:right; font-weight:600; width:120px;">平均出来高</th>
                        <th style="padding:9px 12px; text-align:left; font-weight:600; min-width:180px;">達成条件</th>
                    </tr>
                </thead>
                <tbody>
                    {% for signal in signals %}
                    <tr style="background: {{ '#FFFFFF' if loop.index0 % 2 == 0 else '#FBFBFC' }};">
                        <td style="padding:11px 12px; text-align:center; color:#98A0AE; font-weight:600;">{{ signal.rank }}</td>
                        <td style="padding:11px 12px;">
                            <a href="https://finance.yahoo.co.jp/quote/{{ signal.code }}.T" target="_blank" style="font-family:Inter,sans-serif; color:#C2740A; font-weight:600; text-decoration:none;">
                                {{ signal.code }}
                            </a>
                        </td>
                        <td style="padding:11px 12px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{{ signal.name }}</td>
                        <td style="padding:11px 12px; text-align:center;">
                            {% set is_imminent = signal.estimated_days <= 1 %}
                            {% set is_soon = signal.estimated_days <= 3 and signal.estimated_days > 1 %}
                            <span style="font-size:11.5px; font-weight:700; padding:2.5px 8px; border-radius:12px; font-variant-numeric:tabular-nums;
                                {% if is_imminent %}background:#FBEBEB; color:#C03434;
                                {% elif is_soon %}background:#FBF0DF; color:#C2740A;
                                {% else %}background:#EEF0FB; color:#4338CA;{% endif %}">
                                約{{ signal.estimated_days or '?' }}日後
                            </span>
                        </td>
                        <td style="padding:11px 12px; text-align:center;">
                            {% set is_high = signal.score >= 80 %}
                            {% set is_medium = signal.score >= 60 and signal.score < 80 %}
                            <span style="font-size:11px; font-weight:700; padding:2px 6px; border-radius:6px; font-variant-numeric:tabular-nums;
                                {% if is_high %}background:#E7F4EC; color:#15803D;
                                {% elif is_medium %}background:#FBF0DF; color:#C2740A;
                                {% else %}background:#F1F2F4; color:#5A6172;{% endif %}">
                                {{ "%.0f"|format(signal.score) }}%
                            </span>
                        </td>
                        <td style="padding:11px 12px; text-align:center;">
                            {% if signal.volatility_category_10 is defined and signal.volatility_category_10 %}
                            <span style="font-size:11px; font-weight:700; padding:2px 6px; border-radius:6px;
                                {% if signal.volatility_category_10 == 'high' %}background:#FBEBEB; color:#C03434;
                                {% elif signal.volatility_category_10 == 'mid' %}background:#FBF0DF; color:#C2740A;
                                {% else %}background:#EEF0FB; color:#4338CA;{% endif %}"
                                {% if signal.volatility_pattern is defined and signal.volatility_pattern %}title="{{ signal.volatility_pattern }}"{% endif %}>
                                {% if signal.volatility_category_10 == 'high' %}高{% elif signal.volatility_category_10 == 'mid' %}中{% else %}低{% endif %}
                            </span>
                            {% else %}-{% endif %}
                        </td>
                        <td style="padding:11px 12px; text-align:center;">
                            {% if signal.volatility_category_20 is defined and signal.volatility_category_20 %}
                            <span style="font-size:11px; font-weight:700; padding:2px 6px; border-radius:6px;
                                {% if signal.volatility_category_20 == 'high' %}background:#FBEBEB; color:#C03434;
                                {% elif signal.volatility_category_20 == 'mid' %}background:#FBF0DF; color:#C2740A;
                                {% else %}background:#EEF0FB; color:#4338CA;{% endif %}">
                                {% if signal.volatility_category_20 == 'high' %}高{% elif signal.volatility_category_20 == 'mid' %}中{% else %}低{% endif %}
                            </span>
                            {% else %}-{% endif %}
                        </td>
                        <td style="padding:11px 12px; text-align:center;">
                            {% if signal.volatility_trend is defined and signal.volatility_trend %}
                                {% if signal.volatility_trend == 'expanding' %}
                                <span style="font-size:11px; padding:2px 6px; border-radius:6px; background:#FBEBEB; color:#C03434; font-weight:600;">🔺 拡大</span>
                                {% elif signal.volatility_trend == 'contracting' %}
                                <span style="font-size:11px; padding:2px 6px; border-radius:6px; background:#EEF0FB; color:#4338CA; font-weight:600;">🔻 縮小</span>
                                {% else %}
                                <span style="font-size:11px; padding:2px 6px; border-radius:6px; background:#F1F2F4; color:#5A6172; font-weight:600;">➡️ 横ばい</span>
                                {% endif %}
                            {% else %}-{% endif %}
                        </td>
                        <td style="padding:11px 12px; text-align:right; font-variant-numeric:tabular-nums;" class="tabular-nums">
                            {{ "{:,.0f}".format(signal.avg_volume | default(0)) }}
                        </td>
                        <td style="padding:11px 12px;">
                            <div style="display:flex; flex-wrap:wrap; gap:4px;">
                                {% for cond in signal.conditions_met %}
                                <span style="font-size:11px; padding:2px 6px; border-radius:6px; background:#E7F4EC; color:#15803D; font-weight:600; white-space:nowrap;">✓ {{ cond }}</span>
                                {% endfor %}
                                {% for cond in signal.conditions_pending %}
                                <span style="font-size:11px; padding:2px 6px; border-radius:6px; background:#FBF0DF; color:#C2740A; font-weight:600; white-space:nowrap;">⏳ {{ cond }}</span>
                                {% endfor %}
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% else %}
    <div style="text-align: center; padding: 4rem; color: var(--text-secondary); background: var(--bg-card); border-radius: 12px; border: 1px dashed var(--border);">
        <p>{{ strategy_name }}で接近中の銘柄はありません。</p>
    </div>
    {% endif %}
</section>
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
    # 適切な置換処理
    html = html.replace("{{ url_for('index') }}", "{{ site_root }}index.html")
    html = html.replace("{{ url_for('stock_detail', code=stock.ticker) }}", "https://finance.yahoo.co.jp/quote/{{ stock.ticker }}.T")
    html = html.replace("{{ url_for('static', filename='js/low_hunter.js') }}", "{{ static_root }}static/js/low_hunter.js")
    return html


def generate_high_hunter_html():
    """High Hunterページのテンプレート"""
    template_path = PROJECT_ROOT / 'web' / 'templates' / 'high_hunter.html'
    if not template_path.exists():
        return ''

    html = template_path.read_text(encoding='utf-8')
    html = html.replace('extends "base.html"', 'extends "static_base.html"')
    # 適切な置換処理
    html = html.replace("{{ url_for('index') }}", "{{ site_root }}index.html")
    html = html.replace("{{ url_for('stock_detail', code=stock.ticker) }}", "https://finance.yahoo.co.jp/quote/{{ stock.ticker }}.T")
    html = html.replace("{{ url_for('static', filename='js/high_hunter.js') }}", "{{ static_root }}static/js/high_hunter.js")
    return html


def generate_pairs_hunter_html():
    """Pairs Hunterページのテンプレート"""
    template_path = PROJECT_ROOT / 'web' / 'templates' / 'pairs_hunter.html'
    if not template_path.exists():
        return ''

    html = template_path.read_text(encoding='utf-8')
    html = html.replace('extends "base.html"', 'extends "static_base.html"')
    # 適切な置換処理
    html = html.replace("{{ url_for('index') }}", "{{ site_root }}index.html")
    html = html.replace("{{ url_for('static', filename='js/pairs_hunter.js') }}", "{{ static_root }}static/js/pairs_hunter.js")
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
    (static_templates_dir / 'static_pairs_hunter.html').write_text(
        generate_pairs_hunter_html(), encoding='utf-8'
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

    # 市場区分マップ（東証プライム絞込用）
    market_map = load_market_map(str(STOCK_LIST_PATH))

    # === 1. トップページ ===
    logger.info('\n[1/5] トップページ生成')
    ranking_strategies = cache.get_available_strategies()
    
    # 黄金の指値ボード（Low Hunter）のロード
    lh_data = cache.load_low_hunter_result()
    lh_stocks_all = lh_data.get('stocks', []) if lh_data else []
    
    # 黄金の空売りボード（High Hunter）のロード
    hh_data = cache.load_high_hunter_result()
    hh_stocks_all = hh_data.get('stocks', []) if hh_data else []

    # 接近シグナルのロード（全戦略からマージ用）
    approaching_strategies = cache.get_available_approaching_strategies()

    for suffix, label in MARKET_VARIANTS:
        strategy_info = []
        for name in ranking_strategies:
            raw = cache.load_ranking(name, limit=None if suffix else 10)
            if suffix:
                raw = filter_prime(raw, market_map)
            filtered = [r for r in raw if r.get('score', 0) >= MIN_SCORE_THRESHOLD]
            strategy_info.append({
                'name': name,
                'name_encoded': safe_filename(name),
                'top3': filtered[:3],
            })

        # 指値ボード（市場フィルタは適用しない）
        low_hunter_top3 = lh_stocks_all[:3]

        # 空売りボード（市場フィルタは適用しない）
        high_hunter_top3 = hh_stocks_all[:3]

        # 接近シグナル（東証プライムフィルタ適用＆マージ＆ソート）
        approaching_signals = []
        for name in approaching_strategies:
            signals = cache.load_approaching_signals(name)
            if suffix:
                signals = filter_prime(signals, market_map)
            for s in signals:
                s_copy = s.copy()
                s_copy['strat'] = name
                approaching_signals.append(s_copy)

        def get_days(x):
            try:
                val = x.get('estimated_days')
                return int(val) if val is not None else 999
            except:
                return 999
        
        approaching_signals.sort(key=get_days)
        approaching_top6 = approaching_signals[:6]

        render_template(env, 'static_index.html', DOCS_DIR / f'index{suffix}.html',
                        strategies=strategy_info, metadata=metadata,
                        market_suffix=suffix,
                        low_hunter_top3=low_hunter_top3,
                        high_hunter_top3=high_hunter_top3,
                        approaching_top=approaching_top6,
                        **base_ctx)

    # === 2. 戦略別ランキングページ ===
    logger.info('\n[2/5] 戦略別ランキングページ生成')
    strategy_nav = [{'name': n, 'encoded': safe_filename(n)} for n in ranking_strategies]
    sub_ctx = {**base_ctx, 'site_root': '../', 'static_root': '../'}

    for suffix, label in MARKET_VARIANTS:
        for name in ranking_strategies:
            raw = cache.load_ranking(name, limit=None if suffix else 100)
            if suffix:
                raw = filter_prime(raw, market_map)
            rankings = [r for r in raw if r.get('score', 0) >= MIN_SCORE_THRESHOLD][:30]

            render_template(env, 'static_strategy_ranking.html',
                            DOCS_DIR / 'strategy' / f'{safe_filename(name)}{suffix}.html',
                            strategy_name=name,
                            strategy_name_encoded=safe_filename(name),
                            rankings=rankings,
                            strategies=strategy_nav,
                            market_suffix=suffix, **sub_ctx)

    # === 3. 接近シグナル トップページ ===
    logger.info('\n[3/5] 接近シグナル一覧ページ生成')
    approaching_strategies = cache.get_available_approaching_strategies()
    for suffix, label in MARKET_VARIANTS:
        approaching_info = []
        for name in approaching_strategies:
            signals = cache.load_approaching_signals(name, limit=None if suffix else 3)
            if suffix:
                signals = filter_prime(signals, market_map)
            approaching_info.append({
                'name': name,
                'name_encoded': safe_filename(name),
                'top3': signals[:3],
            })

        render_template(env, 'static_approaching_index.html',
                        DOCS_DIR / 'approaching' / f'index{suffix}.html',
                        strategies=approaching_info, metadata=metadata,
                        market_suffix=suffix, **sub_ctx)

    # === 4. 戦略別接近シグナルページ ===
    logger.info('\n[4/5] 戦略別接近シグナルページ生成')
    for suffix, label in MARKET_VARIANTS:
        for name in approaching_strategies:
            signals = cache.load_approaching_signals(name, limit=None if suffix else 50)
            if suffix:
                signals = filter_prime(signals, market_map)
            signals = signals[:50]

            render_template(env, 'static_approaching_strategy.html',
                            DOCS_DIR / 'approaching' / f'{safe_filename(name)}{suffix}.html',
                            strategy_name=name,
                            strategy_name_encoded=safe_filename(name),
                            signals=signals,
                            market_suffix=suffix, **sub_ctx)

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

    # === 8. Pairs Hunter（ペアトレード・ボード）ページ ===
    logger.info('\n[8/8] Pairs Hunter ページ生成')
    pairs_data = cache.load_pairs_result()
    if pairs_data:
        pairs_list = pairs_data.get('pairs', [])
        pairs_json = json.dumps({
            'pairs': pairs_list,
        }, ensure_ascii=False)

        pairs_dir = DOCS_DIR / 'pairs-hunter'
        pairs_dir.mkdir(parents=True, exist_ok=True)

        render_template(env, 'static_pairs_hunter.html',
                        pairs_dir / 'index.html',
                        pairs=pairs_list,
                        pairs_json=pairs_json,
                        **sub_ctx)
    else:
        logger.info('  Pairs Hunterデータなし（スキップ）')


    # 一時テンプレートを削除
    shutil.rmtree(static_templates_dir)


    # 生成結果サマリ
    generated = list(DOCS_DIR.rglob('*.html'))
    logger.info(f'\n=== 生成完了: {len(generated)}ページ ===')
    for p in sorted(generated):
        logger.info(f'  {p.relative_to(DOCS_DIR)}')


if __name__ == '__main__':
    generate_all()
