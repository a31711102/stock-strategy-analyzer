# Stock Strategy Analyzer

日本株（東証）の銘柄に対して8つの投資手法でバックテストを実行し、**適合度**をスコア化するツールです。  
Web UIから銘柄ごとの適合度ランキングやシグナル接近情報を確認できます。

## 主な機能

### 適合度分析
- 8つの投資手法（買い4 + 空売り4）でバックテストを実行
- 複数指標を統合して適合度スコア（0〜100%）を算出
- 適合理由を自動生成

### シグナル接近検出
- 直近1〜3ヶ月のデータから、エントリーシグナル発生が近い銘柄を検出
- 推定到達日数を表示

### Web UI
- 戦略別の適合度ランキング一覧
- 銘柄別の詳細分析ページ
- シグナル接近中の銘柄一覧

### バッチ処理
- 東証全銘柄（約4,000銘柄）を自動スキャン
- 低負荷モード（CPU使用率制御）でバックグラウンド実行
- 中断・再開機能付き
- タスクスケジューラで平日22:00に自動実行

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 銘柄リストの配置

[JPX](https://www.jpx.co.jp/markets/statistics-equities/misc/01.html) から `data_j.xls` をダウンロードし、プロジェクトルートに配置してください。

### 3. 設定ファイルの確認

`config.yaml` で以下を設定できます：

| 項目 | 説明 | デフォルト |
|---|---|---|
| `data.source` | データソース | `stooq` |
| `data.fallback` | yfinance フォールバック | `true` |
| `backtest.max_years` | バックテスト期間（年） | `null`（全期間） |
| `backtest.holding_period.target_days` | 原則保有日数 | `14` |
| `backtest.holding_period.max_days` | 最大保有日数（強制決済） | `30` |
| `backtest.use_vectorized` | ベクトル化版エンジン使用 | `true` |
| `web.port` | Web UIポート | `5000` |

## 使い方

### Web UI

```bash
python -m src.web.app
```

ブラウザで `http://localhost:5000` にアクセスすると、適合度ランキングとシグナル接近銘柄を確認できます。

### CLI

```bash
# 銘柄を分析（例: NTT）
python -m src.ui.cli analyze 9432

# 手法でフィルタリング
python -m src.ui.cli filter-stocks 新高値ブレイク --threshold 70 --top 20

# 利用可能な手法一覧
python -m src.ui.cli list-strategies
```

### バッチ処理

```bash
# 手動実行
python -m src.batch.daily_batch

# タスクスケジューラへの登録（Windows）
powershell -ExecutionPolicy Bypass -File scripts/register_task.ps1
```

### Pythonスクリプトから使用

```python
from src.data.fetcher import StockDataFetcher
from src.indicators.technical import TechnicalIndicators
from src.analysis.compatibility import CompatibilityAnalyzer
from src.strategies.breakout_new_high_long import BreakoutNewHighLong

# データ取得
fetcher = StockDataFetcher()
df = fetcher.fetch_stock_data("9432")

# テクニカル指標計算
df = TechnicalIndicators.calculate_all_indicators(df)

# 適合度分析
analyzer = CompatibilityAnalyzer()
results = analyzer.calculate_compatibility("9432", df, [BreakoutNewHighLong()])

print(f"適合度: {results['新高値ブレイク']['score']:.1f}%")
```

## 投資手法

### 買い手法（ロング）

| 手法 | エントリー条件の概要 |
|---|---|
| 新高値ブレイク | 新高値接近、出来高増加、移動平均順行配列 |
| 押し目買い | 5日MA乖離率-10%、長期上昇トレンド、日足下降 |
| 新高値リトライ | 陽線、前日比5%以上、ボリンジャーバンド3σ抜け |
| 下降トレンド反転 | ゴールデンクロス、RCI反転、連続陽線 |

### 空売り手法（ショート）

| 手法 | エントリー条件の概要 |
|---|---|
| 押し目空売り | 陰線、上ヒゲ長い、移動平均逆行配列 |
| 新安値ブレイク | 新安値接近、陰線、出来高増加 |
| 上昇トレンド反転 | 3日連続陰線、デッドクロス、RCI反転 |
| 順張り空売り | デッドクロス、陰線、移動平均逆行配列 |

## プロジェクト構造

```
stock-strategy-analyzer/
├── config.yaml                # アプリケーション設定
├── requirements.txt           # Python 依存パッケージ
├── src/
│   ├── data/                  # データ取得（yfinance / Stooq）・キャッシュ
│   ├── indicators/            # テクニカル指標計算
│   ├── strategies/            # 投資手法（8つ）
│   ├── backtest/              # バックテストエンジン（ベクトル化版）
│   ├── analysis/              # 適合度分析・シグナル接近検出
│   ├── batch/                 # バッチ処理・結果キャッシュ
│   ├── web/                   # Flask Web アプリケーション
│   └── ui/                    # CLI インターフェース
├── web/                       # テンプレート・静的ファイル
├── scripts/                   # 運用スクリプト（バッチ実行・スケジューラ登録）
└── tests/
    ├── unit/                  # ユニットテスト（7ファイル）
    ├── integration/           # 結合テスト（4ファイル）
    └── performance/           # 性能テスト（3ファイル）
```

## 開発者向け

### テスト実行

```bash
# 全テスト
python -m pytest tests/ -v

# 種別ごと
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v
python -m pytest tests/performance/ -v
```

### 新しい手法の追加

1. `src/strategies/base.py` の `StrategyBase` を継承
2. `generate_signals()` と `check_conditions()` を実装
3. `src/strategies/utils.py` の `get_all_strategies()` に追加
4. `config.yaml` の `strategies.enabled` に追加

### キャッシュクリア

```python
from src.data.cache import DataCache
cache = DataCache()
cache.clear()        # 全キャッシュクリア
cache.clear("9432")  # 特定銘柄のみ
```

## トラブルシューティング

| 症状 | 対処法 |
|---|---|
| データ取得エラー | yfinance → Stooq の順で自動フォールバックします |
| バッチ処理が遅い | `config.yaml` の `backtest.max_years` を設定して期間を限定 |
| Web UIが表示されない | `python -m src.web.app` で起動後、`http://localhost:5000` を確認 |

## 注意事項

- このツールは**教育・研究目的**です
- 投資判断は自己責任で行ってください
- 過去のパフォーマンスは将来の結果を保証しません

## ライセンス

MIT License
