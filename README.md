# Stock Strategy Analyzer

> A personal fintech tool built to solve a real investor problem: systematically evaluating 3,800+ Tokyo Stock Exchange stocks against 8 quantitative strategies — so investment decisions are driven by data, not intuition.

🔗 **[Live Demo](https://a31711102.github.io/stock-strategy-analyzer/index.html)**

![Python](https://img.shields.io/badge/Python-3.x-blue)
![Flask](https://img.shields.io/badge/Web-Flask-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🎯 Why I Built This

As an active investor in Japanese equities, I faced a recurring problem: evaluating whether a specific stock fits a specific trading strategy required manually checking multiple technical indicators — a process that was slow, inconsistent, and impossible to scale across thousands of stocks.

**The core problem:** No existing tool could score J-stocks against multiple custom strategies and surface which stocks were approaching an entry signal.

Existing screeners (e.g., TradingView, Kabutan) offer filters, but not multi-strategy compatibility scoring with signal timing for the Tokyo Stock Exchange.

So I defined the requirements, designed the architecture, and built it — using AI-assisted development to move from concept to working product efficiently.

---

## ✅ What It Does

| Feature | Detail |
|---|---|
| **Multi-strategy scoring** | Scores every TSE stock (3,800+) across 8 quantitative strategies (4 long, 4 short) |
| **Compatibility score** | Outputs a 0–100% score per strategy per stock, combining multiple technical indicators |
| **Signal approach detection** | Surfaces stocks where an entry signal is estimated to trigger within 1–3 months |
| **Automated daily scanning** | Batch processing runs at 22:00 on weekdays via task scheduler — zero manual effort |
| **Web UI** | Strategy-based ranking, per-stock detail view, approaching-signal watchlist |
| **CLI** | For quick single-stock analysis or strategy filtering |

---

## 🖥️ Demo

**[→ Open Live App](https://a31711102.github.io/stock-strategy-analyzer/index.html)**

The web interface shows:
- Strategy compatibility rankings across all scanned stocks
- Per-stock detail: score breakdown, signal status, estimated approach date
- Watchlist of stocks with approaching entry signals

---

## 🏗️ Key Design Decisions

These are the product and architectural choices I made — and why.

**Why a compatibility score (0–100%) instead of a binary buy/sell signal?**
Binary signals create false precision. A gradient score lets me prioritize stocks at 85% over those at 60%, and supports position sizing decisions. It also makes it easier to spot when a stock is "almost ready."

**Why 8 strategies covering both long and short?**
I wanted the tool to work across different market conditions — trending markets favor breakout/momentum strategies; ranging markets suit mean-reversion. Covering both directions means the tool surfaces opportunities regardless of the broader market environment.

**Why vectorized backtesting?**
Scanning 3,800+ TSE stocks nightly is a real performance constraint. The vectorized engine completes a full scan in 1.5–2 hours, making overnight batch processing practical. Performance wasn't an afterthought — it was a requirement baked into the design from the start.

**Why build a fallback data source (Stooq → yfinance)?**
Data availability for Japanese stocks on free APIs is inconsistent. A single source creates fragile pipelines. The fallback ensures the daily batch completes reliably without manual intervention.

**Why automated scheduling instead of manual runs?**
A tool you have to remember to run is a tool you stop using. Automating the 22:00 daily scan removed the friction and made the data always fresh when I need it in the morning.

---

## 📊 How I Use It (Results & Validation)

- Daily scans cover the full TSE universe (~3,800 stocks) automatically, completing in 1.5–2 hours overnight
- I use the signal approach list each morning to identify stocks worth monitoring
- The compatibility score helps me avoid low-fit trades and concentrate on high-conviction setups
- Running as my primary pre-screening layer before any fundamental research

---

## 🔧 Tech Stack

| Layer | Technology | Decision rationale |
|---|---|---|
| Language | Python | Rich ecosystem for financial data and numerical computing |
| Data | Stooq (primary) + yfinance (fallback) | Reliability through redundancy |
| Web UI | Flask | Lightweight; sufficient for personal tool, no over-engineering |
| Backtesting | Custom vectorized engine | Performance requirement for 4,000-stock scale |
| Scheduling | Windows Task Scheduler | Zero-dependency automation for local deployment |
| Deployment | GitHub Pages | Static export for shareable demo |
| AI Collaboration | Claude (Anthropic) | Architecture review, code generation, optimization — I defined requirements and made all design decisions |
| Testing | pytest (unit × 7, integration × 4, performance × 3) | Confidence when modifying strategies or indicators |

---

## 🧠 What I Learned as a Product Owner

**Scope discipline matters.** I initially designed 12 strategies. After testing, I cut to 8 — the added complexity wasn't improving signal quality, and it made the UI harder to navigate. Fewer, better strategies beat more, noisier ones.

**Performance is a product requirement.** Scanning 3,800 stocks needs to complete overnight to be useful. Treating processing time (target: under 2 hours) as a first-class product constraint shaped the architecture from the start.

**Real usage reveals what specs miss.** Running the tool in my actual investment workflow exposed edge cases — suspended stocks, data gaps, extreme outliers — that weren't in the original requirements. Iteration from real use is irreplaceable.

**AI-assisted development changes the build/buy calculus.** With AI collaboration, I could build a custom solution at a fraction of the traditional cost. The key was staying in the product owner role: defining what to build, evaluating output, and making judgment calls — not delegating those decisions.

---

## 🚀 Roadmap

- [ ] Cloud deployment (currently local-only; GitHub Pages serves static export only)
- [ ] Push notifications (LINE / email) when a tracked stock hits signal threshold
- [ ] Strategy performance dashboard — backtest win rate, average return by strategy over time
- [ ] Watchlist feature — persistent tracking of specific stocks across sessions
- [ ] Mobile-responsive UI

---

## ⚙️ Setup & Usage

<details>
<summary>Click to expand setup instructions</summary>

### Install dependencies

```bash
pip install -r requirements.txt
```

### Get stock list

Download `data_j.xls` from [JPX](https://www.jpx.co.jp/markets/statistics-equities/misc/01.html) and place in project root.

### Run Web UI

```bash
python -m src.web.app
# Open http://localhost:5000
```

### Run CLI

```bash
# Analyze a single stock (e.g., NTT: 9432)
python -m src.ui.cli analyze 9432

# Filter by strategy with threshold
python -m src.ui.cli filter-stocks 新高値ブレイク --threshold 70 --top 20
```

### Run daily batch

```bash
python -m src.batch.daily_batch
```

</details>

---

## ⚠️ Disclaimer

This tool is for personal research and educational purposes only. It does not constitute investment advice. Past performance does not guarantee future results. All investment decisions are made at the user's own risk.

---

## 📄 License

MIT License

---

*Built by a J-stock investor, for J-stock investors.*  
*Product design and requirements by the author. Implementation via AI-assisted development (Claude, Anthropic).*
