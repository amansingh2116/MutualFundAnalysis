"""
Benchmark configuration: the single source of truth for which benchmark
indices this application ingests and displays.

HOW TO ADD A NEW BENCHMARK
───────────────────────────
Option A — add an entry to BENCHMARK_CONFIG below:
    "YOUR INDEX NAME": BenchmarkConfig(
        nse_name="YOUR INDEX NAME",        # exact NSE name
        yahoo_ticker="TICKER.NS",          # Yahoo Finance ticker (optional)
        description="What this tracks",
    ),

Option B — add a row to documentation/index_benchmark_tickers_available.xlsx
    (col A = index name, col B = Yahoo Finance ticker).
    The pipeline picks it up automatically on the next run.

HOW TO REMOVE A BENCHMARK
───────────────────────────
Delete the entry from BENCHMARK_CONFIG, then run:
    python manage.py ingest_benchmarks --cleanup

DATA SOURCES (priority order per benchmark)
────────────────────────────────────────────
1. NSE Direct API  (nseindia.com/api/historical/indicesHistory)
2. Yahoo Finance   (ticker from Excel sheet or nse_name match)
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class BenchmarkConfig:
    """Configuration for a single benchmark index."""
    nse_name: str = ""          # Exact name for NSE historical API
    yahoo_ticker: str = ""      # Yahoo Finance ticker (leave blank if unavailable)
    description: str = ""       # Human-readable description for the monitor UI


# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED BENCHMARKS — only these will be ingested and shown in the monitor.
# ─────────────────────────────────────────────────────────────────────────────
BENCHMARK_CONFIG: dict[str, BenchmarkConfig] = {

    # ── Broad Market ─────────────────────────────────────────────────────────
    "NIFTY 50": BenchmarkConfig(
        nse_name="NIFTY 50",
        description="NSE flagship large-cap index of 50 blue-chip companies",
    ),
    "NIFTY 100": BenchmarkConfig(
        nse_name="NIFTY 100",
        description="Top 100 companies by free-float market cap on NSE",
    ),
    "NIFTY 200": BenchmarkConfig(
        nse_name="NIFTY 200",
        description="Top 200 companies by free-float market cap on NSE",
    ),
    "NIFTY 500": BenchmarkConfig(
        nse_name="NIFTY 500",
        description="Top 500 companies covering ~96% of free-float market cap",
    ),
    "NIFTY NEXT 50": BenchmarkConfig(
        nse_name="NIFTY NEXT 50",
        description="50 companies next in line after NIFTY 50",
    ),
    "NIFTY MIDCAP 50": BenchmarkConfig(
        nse_name="NIFTY MIDCAP 50",
        description="Top 50 mid-cap companies on NSE",
    ),
    "NIFTY MIDCAP 150": BenchmarkConfig(
        nse_name="NIFTY MIDCAP 150",
        description="Top 150 mid-cap companies on NSE",
    ),
    "NIFTY SMALLCAP 50": BenchmarkConfig(
        nse_name="NIFTY SMALLCAP 50",
        description="Top 50 small-cap companies on NSE",
    ),
    "NIFTY SMALLCAP 250": BenchmarkConfig(
        nse_name="NIFTY SMALLCAP 250",
        description="Top 250 small-cap companies on NSE",
    ),
    "NIFTY LARGE MIDCAP 250": BenchmarkConfig(
        nse_name="NIFTY LARGE MIDCAP 250",
        description="Top 250 large and mid-cap companies on NSE",
    ),
    "NIFTY500 MULTICAP 50:25:25": BenchmarkConfig(
        nse_name="NIFTY500 MULTICAP 50:25:25",
        description="NIFTY 500 split 50:25:25 across large/mid/small cap",
    ),
    "SENSEX": BenchmarkConfig(
        nse_name="SENSEX",
        yahoo_ticker="^BSESN",
        description="BSE Sensex — 30 large-cap companies on BSE",
    ),

    # ── Sectoral ─────────────────────────────────────────────────────────────
    "NIFTY AUTO": BenchmarkConfig(nse_name="NIFTY AUTO", description="Automobile and auto ancillary companies"),
    "NIFTY BANK": BenchmarkConfig(nse_name="NIFTY BANK", description="Most liquid and large-cap banking stocks"),
    "NIFTY COMMODITIES": BenchmarkConfig(nse_name="NIFTY COMMODITIES", description="Commodity-linked companies"),
    "NIFTY CPSE": BenchmarkConfig(nse_name="NIFTY CPSE", description="Central Public Sector Enterprises"),
    "NIFTY ENERGY": BenchmarkConfig(nse_name="NIFTY ENERGY", description="Energy sector (oil, gas, power)"),
    "NIFTY FINANCIAL SERVICES": BenchmarkConfig(nse_name="NIFTY FINANCIAL SERVICES", description="Financial services sector"),
    "NIFTY FMCG": BenchmarkConfig(nse_name="NIFTY FMCG", description="Fast Moving Consumer Goods"),
    "NIFTY HEALTHCARE": BenchmarkConfig(nse_name="NIFTY HEALTHCARE", description="Healthcare sector companies"),
    "NIFTY HOUSING": BenchmarkConfig(nse_name="NIFTY HOUSING", description="Housing and real estate finance"),
    "NIFTY INDIA CONSUMPTION": BenchmarkConfig(nse_name="NIFTY INDIA CONSUMPTION", description="Domestic consumption-driven companies"),
    "NIFTY INDIA DEFENCE": BenchmarkConfig(nse_name="NIFTY INDIA DEFENCE", description="Defence sector companies"),
    "NIFTY INDIA MANUFACTURING": BenchmarkConfig(nse_name="NIFTY INDIA MANUFACTURING", description="Manufacturing sector companies"),
    "NIFTY INFRASTRUCTURE": BenchmarkConfig(nse_name="NIFTY INFRASTRUCTURE", description="Infrastructure sector companies"),
    "NIFTY IPO": BenchmarkConfig(nse_name="NIFTY IPO", description="Recent IPO companies"),
    "NIFTY IT": BenchmarkConfig(nse_name="NIFTY IT", description="Information technology companies"),
    "NIFTY MNC": BenchmarkConfig(nse_name="NIFTY MNC", description="Multinational companies listed on NSE"),
    "NIFTY PHARMA": BenchmarkConfig(nse_name="NIFTY PHARMA", description="Pharmaceutical companies"),
    "NIFTY REALTY": BenchmarkConfig(nse_name="NIFTY REALTY", description="Real estate companies"),
    "NIFTY RURAL": BenchmarkConfig(nse_name="NIFTY RURAL", description="Companies with significant rural exposure"),
    "NIFTY TRANSPORTATION & LOGISTICS": BenchmarkConfig(nse_name="NIFTY TRANSPORTATION & LOGISTICS", description="Transportation and logistics companies"),

    # ── Hybrid / Composite ────────────────────────────────────────────────────
    "NIFTY 50 ARBITRAGE": BenchmarkConfig(nse_name="NIFTY 50 ARBITRAGE", description="Arbitrage strategy on NIFTY 50"),
    "NIFTY 50 HYBRID COMPOSITE DEBT 15:85": BenchmarkConfig(nse_name="NIFTY 50 HYBRID COMPOSITE DEBT 15:85", description="15% equity + 85% debt composite"),
    "NIFTY 50 HYBRID COMPOSITE DEBT 50:50": BenchmarkConfig(nse_name="NIFTY 50 HYBRID COMPOSITE DEBT 50:50", description="50% equity + 50% debt composite"),
    "NIFTY 50 HYBRID COMPOSITE DEBT 65:35": BenchmarkConfig(nse_name="NIFTY 50 HYBRID COMPOSITE DEBT 65:35", description="65% equity + 35% debt composite"),
    "NIFTY EQUITY SAVINGS": BenchmarkConfig(nse_name="NIFTY EQUITY SAVINGS", description="Equity savings multi-asset index"),

    # ── Factor / Smart Beta ───────────────────────────────────────────────────
    "NIFTY100 ESG": BenchmarkConfig(nse_name="NIFTY100 ESG", description="NIFTY 100 screened for ESG criteria"),
    "NIFTY200 QUALITY 30": BenchmarkConfig(nse_name="NIFTY200 QUALITY 30", description="Top 30 quality companies from NIFTY 200"),

    # ── Fixed Income / Debt (NSE API accessible) ──────────────────────────────
    "NIFTY 10 YR BENCHMARK G-SEC": BenchmarkConfig(
        nse_name="NIFTY 10 YR BENCHMARK G-SEC",
        description="10-year government securities benchmark",
    ),
    "NIFTY ALL DURATION G-SEC INDEX": BenchmarkConfig(
        nse_name="NIFTY ALL DURATION G-SEC INDEX",
        description="All-duration government securities index",
    ),
    "NIFTY LIQUID INDEX": BenchmarkConfig(
        nse_name="NIFTY LIQUID INDEX",
        description="Liquid fund benchmark — overnight/T+1 instruments",
    ),
}

# Fast lookup set (uppercase) used by ingest_benchmarks
REQUIRED_BENCHMARK_NAMES: frozenset[str] = frozenset(
    k.upper() for k in BENCHMARK_CONFIG
)
