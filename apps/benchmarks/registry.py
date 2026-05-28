"""
Shared benchmark registry and Yahoo Finance retrieval helpers.

Benchmark definitions follow the AMFI Tier-1 benchmark sheet (official SEBI
categories). For every benchmark where no direct Yahoo Finance index page could
be confirmed we set fallback="NIFTY 50" so the system transparently displays
"<Requested Index> — using NIFTY 50 as proxy" rather than showing nothing.

Sources
-------
- AMFI Tier-1 benchmark sheet (category-wise official benchmarks)
- Yahoo Finance verified tickers (confirmed direct index quotes)
- NIFTY 50 (^NSEI) — universal fallback for any unresolvable benchmark
"""
from __future__ import annotations

import logging
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import md5
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

logger = logging.getLogger("mfanalysis")

BENCHMARK_TTL = 60 * 60 * 6
NIFTYINDICES_BASE = "https://www.niftyindices.com"
NIFTYINDICES_ASSET_BASE = "https://iislliveblob.niftyindices.com"

# ── Universal fallback ────────────────────────────────────────────────────────
NIFTY50_FALLBACK = "NIFTY 50"
NIFTY50_FALLBACK_NOTE = (
    "No confirmed Yahoo Finance ticker for this benchmark index. "
    "NIFTY 50 (^NSEI) is used as a proxy — comparisons are approximate."
)


@dataclass(frozen=True)
class BenchmarkDefinition:
    name: str
    yahoo_tickers: tuple[str, ...] = ()
    proxy_tickers: tuple[tuple[str, str], ...] = ()
    fallback: str | None = None
    aliases: tuple[str, ...] = ()
    nse_name: str | None = None
    field: str = "Close"


@dataclass(frozen=True)
class BenchmarkCandidate:
    requested_name: str
    benchmark_name: str
    yahoo_ticker: str
    field: str = "Close"
    is_proxy: bool = False
    is_fallback: bool = False
    note: str = ""
    source: str = "yfinance"


@dataclass(frozen=True)
class BenchmarkResolution:
    requested_name: str
    actual_name: str
    yahoo_tickers: tuple[str, ...]
    fallback_used: bool = False
    note: str = ""

    @property
    def primary_ticker(self) -> str:
        return self.yahoo_tickers[0] if self.yahoo_tickers else ""

    @property
    def display_name(self) -> str:
        if self.fallback_used:
            return f"{self.actual_name} (proxy for {self.requested_name})"
        return self.actual_name


# ═══════════════════════════════════════════════════════════════════════════════
# BENCHMARK DEFINITIONS
# ── Key: canonical name (uppercase)
# ── yahoo_tickers: confirmed direct Yahoo Finance index quotes (verified)
# ── fallback: used when yahoo_tickers fails; NIFTY 50 = universal fallback
# ── aliases: alternative names / spellings accepted as input
# ═══════════════════════════════════════════════════════════════════════════════

BENCHMARK_DEFINITIONS: dict[str, BenchmarkDefinition] = {

    # ── Broad Market ──────────────────────────────────────────────────────────
    "NIFTY 50": BenchmarkDefinition(
        "NIFTY 50", ("^NSEI",),
        aliases=("NIFTY50", "NSE NIFTY", "NIFTY50 TRI", "NIFTY 50 INDEX"),
    ),
    "SENSEX": BenchmarkDefinition(
        "SENSEX", ("^BSESN",),
        aliases=("BSE SENSEX", "S&P BSE SENSEX", "BSE 30"),
    ),
    "NIFTY 100": BenchmarkDefinition(
        "NIFTY 100", ("^CNX100",),
        aliases=("NIFTY100", "CNX 100"),
    ),
    "NIFTY 200": BenchmarkDefinition(
        "NIFTY 200", ("^CNX200",),
        aliases=("NIFTY200", "CNX 200"),
    ),
    "NIFTY 500": BenchmarkDefinition(
        "NIFTY 500", ("^CRSLDX",),
        aliases=("NIFTY500", "CNX 500"),
    ),
    "NIFTY NEXT 50": BenchmarkDefinition(
        "NIFTY NEXT 50", ("^NSMIDCP",),
        aliases=("NIFTY NEXT50", "NEXT 50", "CNX NIFTY JUNIOR"),
    ),

    # ── Mid & Small Cap ───────────────────────────────────────────────────────
    "NIFTY MIDCAP 50": BenchmarkDefinition(
        "NIFTY MIDCAP 50", ("^NSEMDCP50",),
        aliases=("MIDCAP 50", "NIFTY MIDCAP50"),
    ),
    "NIFTY MIDCAP 100": BenchmarkDefinition(
        "NIFTY MIDCAP 100", ("NIFTY_MIDCAP_100.NS",),
        aliases=("MIDCAP 100", "NIFTY MIDCAP100"),
    ),
    "NIFTY MIDCAP 150": BenchmarkDefinition(
        "NIFTY MIDCAP 150", ("NIFTYMIDCAP150.NS", "^CRSMID"),
        aliases=("NIFTY MIDCAP150", "MIDCAP 150"),
    ),
    "NIFTY SMALLCAP 50": BenchmarkDefinition(
        "NIFTY SMALLCAP 50", ("^CNXSC", "NIFTYSMLCAP50.NS"),
        aliases=("NIFTY SMLCAP 50", "SMALLCAP 50"),
        nse_name="NIFTY SMLCAP 50",
    ),
    "NIFTY SMALLCAP 100": BenchmarkDefinition(
        "NIFTY SMALLCAP 100", ("^CNXSC",),
        aliases=("NIFTY SMLCAP 100", "SMALLCAP 100"),
        nse_name="NIFTY SMLCAP 100",
    ),
    "NIFTY SMALLCAP 250": BenchmarkDefinition(
        "NIFTY SMALLCAP 250", ("NIFTYSMLCAP250.NS",),
        aliases=("NIFTY SMLCAP 250", "SMALLCAP 250"),
        nse_name="NIFTY SMLCAP 250",
    ),

    # ── Multi/Large&Mid/Flexi ─────────────────────────────────────────────────
    "NIFTY LARGE MIDCAP 250": BenchmarkDefinition(
        "NIFTY LARGE MIDCAP 250", ("NIFTY_LARGEMID250.NS",),
        aliases=("NIFTY LARGEMIDCAP 250", "NIFTY LARGE & MIDCAP 250",
                 "NIFTY LARGE AND MIDCAP 250", "NIFTY LARGEMIDC 250"),
    ),
    "NIFTY500 MULTICAP 50:25:25": BenchmarkDefinition(
        "NIFTY500 MULTICAP 50:25:25", ("NIFTY500_MULTICAP.NS",),
        aliases=("NIFTY 500 MULTICAP", "NIFTY500 MULTICAP", "MULTICAP 50:25:25"),
    ),

    # ── Hybrid indices (no confirmed Yahoo page → NIFTY 50 fallback) ──────────
    "NIFTY 50 HYBRID COMPOSITE DEBT 65:35": BenchmarkDefinition(
        "NIFTY 50 HYBRID COMPOSITE DEBT 65:35", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("HYBRID COMPOSITE DEBT 65:35", "NIFTY HYBRID 65:35",
                 "AGGRESSIVE HYBRID COMPOSITE DEBT INDEX"),
    ),
    "NIFTY 50 HYBRID COMPOSITE DEBT 50:50": BenchmarkDefinition(
        "NIFTY 50 HYBRID COMPOSITE DEBT 50:50", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("HYBRID COMPOSITE DEBT 50:50", "NIFTY HYBRID 50:50",
                 "BALANCED HYBRID COMPOSITE DEBT INDEX"),
    ),
    "NIFTY 50 HYBRID COMPOSITE DEBT 15:85": BenchmarkDefinition(
        "NIFTY 50 HYBRID COMPOSITE DEBT 15:85", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("HYBRID COMPOSITE DEBT 15:85", "NIFTY HYBRID 15:85",
                 "CONSERVATIVE HYBRID COMPOSITE DEBT INDEX"),
    ),
    "NIFTY 50 ARBITRAGE": BenchmarkDefinition(
        "NIFTY 50 ARBITRAGE", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY ARBITRAGE",),
    ),
    "NIFTY EQUITY SAVINGS": BenchmarkDefinition(
        "NIFTY EQUITY SAVINGS", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("EQUITY SAVINGS INDEX",),
    ),

    # ── Gilt & 10-yr G-Sec (confirmed) ───────────────────────────────────────
    "NIFTY 10 YR BENCHMARK G-SEC": BenchmarkDefinition(
        "NIFTY 10 YR BENCHMARK G-SEC", ("NIFTYGS10YR.NS",),
        aliases=("NIFTY 10YR GSEC", "NIFTY 10 YEAR G-SEC", "NIFTY GSEC 10 YEAR"),
    ),

    # ── Dynamic Bond (confirmed closest) ─────────────────────────────────────
    "NIFTY COMPOSITE DEBT INDEX": BenchmarkDefinition(
        "NIFTY COMPOSITE DEBT INDEX", ("NIFTYGSCOMPOSITE.NS",),
        aliases=("NIFTY COMPOSITE DEBT", "NIFTY COMPOSITE DEBT INDEX A-III"),
    ),

    # ── Debt indices without confirmed Yahoo tickers → NIFTY 50 fallback ─────
    "NIFTY LIQUID INDEX": BenchmarkDefinition(
        "NIFTY LIQUID INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY LIQUID", "LIQUID INDEX", "CRISIL LIQUID FUND INDEX"),
    ),
    "NIFTY MONEY MARKET INDEX": BenchmarkDefinition(
        "NIFTY MONEY MARKET INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY MONEY MARKET", "MONEY MARKET INDEX"),
    ),
    "NIFTY ULTRA SHORT DURATION DEBT INDEX": BenchmarkDefinition(
        "NIFTY ULTRA SHORT DURATION DEBT INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY ULTRA SHORT DURATION", "ULTRA SHORT DURATION INDEX"),
    ),
    "NIFTY LOW DURATION DEBT INDEX": BenchmarkDefinition(
        "NIFTY LOW DURATION DEBT INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY LOW DURATION", "LOW DURATION INDEX"),
    ),
    "NIFTY SHORT DURATION DEBT INDEX": BenchmarkDefinition(
        "NIFTY SHORT DURATION DEBT INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY SHORT DURATION", "SHORT DURATION INDEX",
                 "CRISIL SHORT TERM BOND FUND INDEX"),
    ),
    "NIFTY MEDIUM DURATION DEBT INDEX": BenchmarkDefinition(
        "NIFTY MEDIUM DURATION DEBT INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY MEDIUM DURATION", "MEDIUM DURATION INDEX"),
    ),
    "NIFTY MEDIUM TO LONG DURATION DEBT INDEX": BenchmarkDefinition(
        "NIFTY MEDIUM TO LONG DURATION DEBT INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("MEDIUM TO LONG DURATION INDEX",),
    ),
    "NIFTY LONG DURATION DEBT INDEX": BenchmarkDefinition(
        "NIFTY LONG DURATION DEBT INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY LONG DURATION", "LONG DURATION INDEX"),
    ),
    "NIFTY CORPORATE BOND INDEX": BenchmarkDefinition(
        "NIFTY CORPORATE BOND INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("CORPORATE BOND INDEX", "NIFTY CORP BOND"),
    ),
    "NIFTY CREDIT RISK BOND INDEX": BenchmarkDefinition(
        "NIFTY CREDIT RISK BOND INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("CREDIT RISK INDEX", "NIFTY CREDIT RISK"),
    ),
    "NIFTY BANKING & PSU DEBT INDEX": BenchmarkDefinition(
        "NIFTY BANKING & PSU DEBT INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("BANKING PSU DEBT INDEX", "NIFTY BANKING AND PSU DEBT"),
    ),
    "NIFTY ALL DURATION G-SEC INDEX": BenchmarkDefinition(
        "NIFTY ALL DURATION G-SEC INDEX", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY GILT", "ALL DURATION G-SEC", "NIFTY GSEC",
                 "CRISIL GILT INDEX"),
    ),

    # ── Sector / Thematic — confirmed Yahoo tickers ───────────────────────────
    "NIFTY AUTO": BenchmarkDefinition(
        "NIFTY AUTO", ("^CNXAUTO",),
        aliases=("NIFTY AUTOMOBILE", "CNX AUTO"),
    ),
    "NIFTY BANK": BenchmarkDefinition(
        "NIFTY BANK", ("^NSEBANK",),
        aliases=("BANK NIFTY", "NIFTY BANK INDEX", "NIFTY BANKING"),
    ),
    "NIFTY FINANCIAL SERVICES": BenchmarkDefinition(
        "NIFTY FINANCIAL SERVICES", ("NIFTY_FIN_SERVICE.NS",),
        aliases=("NIFTY FINSERV", "NIFTY FIN SERVICES", "NIFTY FINANCIAL SERVICE"),
    ),
    "NIFTY FMCG": BenchmarkDefinition(
        "NIFTY FMCG", ("^CNXFMCG",),
        aliases=("CNX FMCG",),
    ),
    "NIFTY HEALTHCARE": BenchmarkDefinition(
        "NIFTY HEALTHCARE", ("NIFTY_HEALTHCARE.NS",),
        aliases=("NIFTY HEALTH", "NIFTY HEALTHCARE INDEX"),
    ),
    "NIFTY IT": BenchmarkDefinition(
        "NIFTY IT", ("^CNXIT",),
        aliases=("CNX IT", "NIFTY INFORMATION TECHNOLOGY"),
    ),
    "NIFTY MEDIA": BenchmarkDefinition(
        "NIFTY MEDIA", ("^CNXMEDIA",),
        aliases=("CNX MEDIA",),
    ),
    "NIFTY METAL": BenchmarkDefinition(
        "NIFTY METAL", ("^CNXMETAL",),
        aliases=("CNX METAL",),
    ),
    "NIFTY OIL & GAS": BenchmarkDefinition(
        "NIFTY OIL & GAS", ("NIFTY_OIL_AND_GAS.NS",),
        aliases=("NIFTY OIL AND GAS", "NIFTY ENERGY OIL GAS"),
    ),
    "NIFTY PHARMA": BenchmarkDefinition(
        "NIFTY PHARMA", ("^CNXPHARMA",),
        aliases=("CNX PHARMA", "NIFTY PHARMACEUTICAL"),
    ),
    "NIFTY PRIVATE BANK": BenchmarkDefinition(
        "NIFTY PRIVATE BANK", ("NIFTYPVTBANK.NS",),
        aliases=("NIFTY PVT BANK", "PRIVATE BANK INDEX"),
    ),
    "NIFTY PSU BANK": BenchmarkDefinition(
        "NIFTY PSU BANK", ("^CNXPSUBANK",),
        aliases=("PSU BANK", "CNX PSU BANK"),
    ),
    "NIFTY REALTY": BenchmarkDefinition(
        "NIFTY REALTY", ("^CNXREALTY",),
        aliases=("NIFTY REAL ESTATE", "CNX REALTY"),
    ),
    "NIFTY COMMODITIES": BenchmarkDefinition(
        "NIFTY COMMODITIES", ("^CNXCMDT",),
        aliases=("CNX COMMODITIES", "NIFTY COMMODITY"),
    ),
    "NIFTY INDIA CONSUMPTION": BenchmarkDefinition(
        "NIFTY INDIA CONSUMPTION", ("^CNXCONSUM",),
        aliases=("NIFTY CONSUMPTION", "CNX CONSUMPTION", "NIFTY CONSUMER"),
    ),
    "NIFTY CPSE": BenchmarkDefinition(
        "NIFTY CPSE", ("NIFTY_CPSE.NS",),
        aliases=("NIFTY CPSE INDEX",),
    ),
    "NIFTY ENERGY": BenchmarkDefinition(
        "NIFTY ENERGY", ("^CNXENERGY",),
        aliases=("CNX ENERGY",),
    ),
    "NIFTY100 ESG": BenchmarkDefinition(
        "NIFTY100 ESG", ("NIFTY100_ESG.NS",),
        aliases=("NIFTY 100 ESG", "NIFTY ESG", "NIFTY100 ESG INDEX"),
    ),
    "NIFTY INFRASTRUCTURE": BenchmarkDefinition(
        "NIFTY INFRASTRUCTURE", ("^CNXINFRA",),
        aliases=("CNX INFRASTRUCTURE", "NIFTY INFRA"),
    ),
    "NIFTY MNC": BenchmarkDefinition(
        "NIFTY MNC", ("^CNXMNC",),
        aliases=("CNX MNC",),
    ),
    "NIFTY PSE": BenchmarkDefinition(
        "NIFTY PSE", ("^CNXPSE",),
        aliases=("CNX PSE", "NIFTY PUBLIC SECTOR"),
    ),
    "NIFTY SERVICES SECTOR": BenchmarkDefinition(
        "NIFTY SERVICES SECTOR", ("^CNXSERVICE",),
        aliases=("NIFTY SERVICES", "CNX SERVICE"),
    ),
    "NIFTY INDIA MANUFACTURING": BenchmarkDefinition(
        "NIFTY INDIA MANUFACTURING", ("NIFTY_INDIA_MFG.NS",),
        aliases=("NIFTY MANUFACTURING", "NIFTY INDIA MFG"),
    ),

    # ── Sector — unconfirmed → NIFTY 50 fallback ──────────────────────────────
    "NIFTY CONSUMER DURABLES": BenchmarkDefinition(
        "NIFTY CONSUMER DURABLES", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY CONSUMER DURABLE", "CONSUMER DURABLES INDEX"),
    ),
    "NIFTY INDIA DEFENCE": BenchmarkDefinition(
        "NIFTY INDIA DEFENCE", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY DEFENCE", "INDIA DEFENCE INDEX"),
    ),
    "NIFTY TRANSPORTATION & LOGISTICS": BenchmarkDefinition(
        "NIFTY TRANSPORTATION & LOGISTICS", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY TRANSPORT AND LOGISTICS", "NIFTY TRANSPORT LOGISTICS",
                 "TRANSPORTATION LOGISTICS INDEX"),
    ),
    "NIFTY HOUSING": BenchmarkDefinition(
        "NIFTY HOUSING", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY HOUSING INDEX",),
    ),
    "NIFTY RURAL": BenchmarkDefinition(
        "NIFTY RURAL", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY RURAL INDEX",),
    ),
    "NIFTY IPO": BenchmarkDefinition(
        "NIFTY IPO", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY IPO INDEX", "NIFTY NEW LISTING"),
    ),
    "NIFTY200 QUALITY 30": BenchmarkDefinition(
        "NIFTY200 QUALITY 30", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY 200 QUALITY 30", "QUALITY 30"),
    ),
    "NIFTY500 SHARIAH": BenchmarkDefinition(
        "NIFTY500 SHARIAH", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("NIFTY 500 SHARIAH", "SHARIAH INDEX"),
    ),

    # ── Global ────────────────────────────────────────────────────────────────
    "S&P 500": BenchmarkDefinition(
        "S&P 500", ("^GSPC",),
        aliases=("SP500", "SNP 500", "S&P500"),
    ),
    "NASDAQ 100": BenchmarkDefinition(
        "NASDAQ 100", ("^NDX",),
        aliases=("NASDAQ100",),
    ),
    "DOW JONES": BenchmarkDefinition(
        "DOW JONES", ("^DJI",),
        aliases=("DJIA",),
    ),
    "MSCI WORLD": BenchmarkDefinition(
        "MSCI WORLD", (),
        fallback=NIFTY50_FALLBACK,
        aliases=("MSCI ACWI", "MSCI WORLD INDEX"),
    ),

    # ── FX ───────────────────────────────────────────────────────────────────
    "USD/INR": BenchmarkDefinition(
        "USD/INR", ("USDINR=X",),
        aliases=("INR/USD", "USDINR"),
    ),
}

BENCHMARKS = BENCHMARK_DEFINITIONS


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY → BENCHMARK MAP
# Follows AMFI Tier-1 benchmark sheet exactly.
# Unresolvable → mapped to NIFTY 50 so UI always shows something.
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_BENCHMARK_MAP: dict[str, str] = {
    # Core equity
    "Equity Scheme - Large Cap Fund":            "NIFTY 100",
    "Equity Scheme - Large & Mid Cap Fund":      "NIFTY LARGE MIDCAP 250",
    "Equity Scheme - Mid Cap Fund":              "NIFTY MIDCAP 150",
    "Equity Scheme - Small Cap Fund":            "NIFTY SMALLCAP 250",
    "Equity Scheme - Multi Cap Fund":            "NIFTY500 MULTICAP 50:25:25",
    "Equity Scheme - Flexi Cap Fund":            "NIFTY 500",
    "Equity Scheme - ELSS":                      "NIFTY 500",
    "Equity Scheme - Value Fund":                "NIFTY 500",
    "Equity Scheme - Contra Fund":               "NIFTY 500",
    "Equity Scheme - Focused Fund":              "NIFTY 500",
    "Equity Scheme - Dividend Yield Fund":       "NIFTY 500",
    "Equity Scheme - Index Funds":               "NIFTY 50",
    "Equity Scheme - ETFs":                      "NIFTY 50",

    # Hybrid
    "Hybrid Scheme - Aggressive Hybrid Fund":    "NIFTY 50 HYBRID COMPOSITE DEBT 65:35",
    "Hybrid Scheme - Balanced Hybrid Fund":      "NIFTY 50 HYBRID COMPOSITE DEBT 50:50",
    "Hybrid Scheme - Conservative Hybrid Fund":  "NIFTY 50 HYBRID COMPOSITE DEBT 15:85",
    "Hybrid Scheme - Dynamic Asset Allocation":  "NIFTY 50 HYBRID COMPOSITE DEBT 50:50",
    "Hybrid Scheme - Balanced Advantage Fund":   "NIFTY 50 HYBRID COMPOSITE DEBT 50:50",
    "Hybrid Scheme - Multi Asset Allocation":    "NIFTY 50",   # no single universal benchmark
    "Hybrid Scheme - Arbitrage Fund":            "NIFTY 50 ARBITRAGE",
    "Hybrid Scheme - Equity Savings":            "NIFTY EQUITY SAVINGS",

    # Debt
    "Debt Scheme - Overnight Fund":              "NIFTY LIQUID INDEX",
    "Debt Scheme - Liquid Fund":                 "NIFTY LIQUID INDEX",
    "Debt Scheme - Money Market Fund":           "NIFTY MONEY MARKET INDEX",
    "Debt Scheme - Ultra Short Duration Fund":   "NIFTY ULTRA SHORT DURATION DEBT INDEX",
    "Debt Scheme - Low Duration Fund":           "NIFTY LOW DURATION DEBT INDEX",
    "Debt Scheme - Short Duration Fund":         "NIFTY SHORT DURATION DEBT INDEX",
    "Debt Scheme - Medium Duration Fund":        "NIFTY MEDIUM DURATION DEBT INDEX",
    "Debt Scheme - Medium to Long Duration Fund":"NIFTY MEDIUM TO LONG DURATION DEBT INDEX",
    "Debt Scheme - Long Duration Fund":          "NIFTY LONG DURATION DEBT INDEX",
    "Debt Scheme - Dynamic Bond":                "NIFTY COMPOSITE DEBT INDEX",
    "Debt Scheme - Corporate Bond Fund":         "NIFTY CORPORATE BOND INDEX",
    "Debt Scheme - Credit Risk Fund":            "NIFTY CREDIT RISK BOND INDEX",
    "Debt Scheme - Banking and PSU Fund":        "NIFTY BANKING & PSU DEBT INDEX",
    "Debt Scheme - Banking & PSU Fund":          "NIFTY BANKING & PSU DEBT INDEX",
    "Debt Scheme - Gilt Fund":                   "NIFTY ALL DURATION G-SEC INDEX",
    "Debt Scheme - Gilt Fund with 10 year constant duration": "NIFTY 10 YR BENCHMARK G-SEC",
    "Debt Scheme - Floater Fund":                "NIFTY SHORT DURATION DEBT INDEX",

    # Solution-oriented
    "Solution Oriented Scheme - Retirement Fund":  "NIFTY 500",
    "Solution Oriented Scheme - Childrens Fund":   "NIFTY 500",
    "Solution Oriented Scheme - Children's Fund":  "NIFTY 500",

    # Other
    "Other Scheme - FoF Domestic":   "NIFTY 50",
    "Other Scheme - FoF Overseas":   "NIFTY 50",
    "Other Scheme - Index Funds":    "NIFTY 50",
    "Other Scheme - ETFs":           "NIFTY 50",
}


# ── Sector/thematic keyword → benchmark ───────────────────────────────────────
# Applied when CATEGORY_BENCHMARK_MAP has no exact match.
CATEGORY_BENCHMARK_RULES: tuple[tuple[str, str], ...] = (
    # Broad equity
    ("large & mid",          "NIFTY LARGE MIDCAP 250"),
    ("large and mid",        "NIFTY LARGE MIDCAP 250"),
    ("large midcap",         "NIFTY LARGE MIDCAP 250"),
    ("small cap",            "NIFTY SMALLCAP 250"),
    ("smallcap",             "NIFTY SMALLCAP 250"),
    ("mid cap",              "NIFTY MIDCAP 150"),
    ("midcap",               "NIFTY MIDCAP 150"),
    ("large cap",            "NIFTY 100"),
    ("multicap",             "NIFTY500 MULTICAP 50:25:25"),
    ("multi cap",            "NIFTY500 MULTICAP 50:25:25"),
    ("flexi cap",            "NIFTY 500"),
    ("flexicap",             "NIFTY 500"),
    ("elss",                 "NIFTY 500"),
    ("tax saver",            "NIFTY 500"),
    ("tax saving",           "NIFTY 500"),
    ("value",                "NIFTY 500"),
    ("contra",               "NIFTY 500"),
    ("focused",              "NIFTY 500"),
    ("dividend yield",       "NIFTY 500"),

    # Hybrid
    ("aggressive hybrid",    "NIFTY 50 HYBRID COMPOSITE DEBT 65:35"),
    ("balanced hybrid",      "NIFTY 50 HYBRID COMPOSITE DEBT 50:50"),
    ("conservative hybrid",  "NIFTY 50 HYBRID COMPOSITE DEBT 15:85"),
    ("dynamic asset",        "NIFTY 50 HYBRID COMPOSITE DEBT 50:50"),
    ("balanced advantage",   "NIFTY 50 HYBRID COMPOSITE DEBT 50:50"),
    ("multi asset",          "NIFTY 50"),
    ("arbitrage",            "NIFTY 50 ARBITRAGE"),
    ("equity savings",       "NIFTY EQUITY SAVINGS"),

    # Debt (order: most specific first)
    ("overnight",            "NIFTY LIQUID INDEX"),
    ("liquid",               "NIFTY LIQUID INDEX"),
    ("money market",         "NIFTY MONEY MARKET INDEX"),
    ("ultra short",          "NIFTY ULTRA SHORT DURATION DEBT INDEX"),
    ("low duration",         "NIFTY LOW DURATION DEBT INDEX"),
    ("short duration",       "NIFTY SHORT DURATION DEBT INDEX"),
    ("medium to long",       "NIFTY MEDIUM TO LONG DURATION DEBT INDEX"),
    ("medium duration",      "NIFTY MEDIUM DURATION DEBT INDEX"),
    ("long duration",        "NIFTY LONG DURATION DEBT INDEX"),
    ("dynamic bond",         "NIFTY COMPOSITE DEBT INDEX"),
    ("corporate bond",       "NIFTY CORPORATE BOND INDEX"),
    ("credit risk",          "NIFTY CREDIT RISK BOND INDEX"),
    ("banking & psu",        "NIFTY BANKING & PSU DEBT INDEX"),
    ("banking and psu",      "NIFTY BANKING & PSU DEBT INDEX"),
    ("banking psu",          "NIFTY BANKING & PSU DEBT INDEX"),
    ("gilt",                 "NIFTY ALL DURATION G-SEC INDEX"),
    ("floater",              "NIFTY SHORT DURATION DEBT INDEX"),
    ("floating rate",        "NIFTY SHORT DURATION DEBT INDEX"),

    # Sector / Thematic — confirmed Yahoo tickers
    ("auto",                 "NIFTY AUTO"),
    ("automobile",           "NIFTY AUTO"),
    ("banking",              "NIFTY BANK"),
    ("bank",                 "NIFTY BANK"),
    ("financial services",   "NIFTY FINANCIAL SERVICES"),
    ("finserv",              "NIFTY FINANCIAL SERVICES"),
    ("fmcg",                 "NIFTY FMCG"),
    ("healthcare",           "NIFTY HEALTHCARE"),
    ("health care",          "NIFTY HEALTHCARE"),
    ("information technology", "NIFTY IT"),
    ("technology",           "NIFTY IT"),
    (" it ",                 "NIFTY IT"),
    ("media",                "NIFTY MEDIA"),
    ("metal",                "NIFTY METAL"),
    ("oil & gas",            "NIFTY OIL & GAS"),
    ("oil and gas",          "NIFTY OIL & GAS"),
    ("pharma",               "NIFTY PHARMA"),
    ("pharmaceutical",       "NIFTY PHARMA"),
    ("private bank",         "NIFTY PRIVATE BANK"),
    ("pvt bank",             "NIFTY PRIVATE BANK"),
    ("psu bank",             "NIFTY PSU BANK"),
    ("real estate",          "NIFTY REALTY"),
    ("realty",               "NIFTY REALTY"),
    ("commodities",          "NIFTY COMMODITIES"),
    ("commodity",            "NIFTY COMMODITIES"),
    ("consumption",          "NIFTY INDIA CONSUMPTION"),
    ("consumer",             "NIFTY INDIA CONSUMPTION"),
    ("cpse",                 "NIFTY CPSE"),
    ("energy",               "NIFTY ENERGY"),
    ("esg",                  "NIFTY100 ESG"),
    ("infrastructure",       "NIFTY INFRASTRUCTURE"),
    ("infra",                "NIFTY INFRASTRUCTURE"),
    ("mnc",                  "NIFTY MNC"),
    ("pse",                  "NIFTY PSE"),
    ("services sector",      "NIFTY SERVICES SECTOR"),
    ("manufacturing",        "NIFTY INDIA MANUFACTURING"),

    # Sector / Thematic — unconfirmed, will fall back to NIFTY 50
    ("consumer durable",     "NIFTY CONSUMER DURABLES"),
    ("defence",              "NIFTY INDIA DEFENCE"),
    ("defense",              "NIFTY INDIA DEFENCE"),
    ("transport",            "NIFTY TRANSPORTATION & LOGISTICS"),
    ("logistics",            "NIFTY TRANSPORTATION & LOGISTICS"),
    ("housing",              "NIFTY HOUSING"),
    ("rural",                "NIFTY RURAL"),
    ("ipo",                  "NIFTY IPO"),
    ("quality",              "NIFTY200 QUALITY 30"),
    ("shariah",              "NIFTY500 SHARIAH"),

    # Catch-all for index/ETF schemes
    ("index",                "NIFTY 50"),
    ("etf",                  "NIFTY 50"),
)


# ── Explicit regex rules (applied before category-map & keyword rules) ─────────
EXPLICIT_INDEX_RULES: tuple[tuple[str, str], ...] = (
    # Exact large-midcap references
    (r"\bnifty\s+large\s*(mid|&|and)\s*cap\s+250\b",   "NIFTY LARGE MIDCAP 250"),
    # Multi cap
    (r"\bnifty\s*500\s+multicap\b",                     "NIFTY500 MULTICAP 50:25:25"),
    # Small cap (most specific first)
    (r"\bnifty\s+small\s*cap\s+250\b|\bsmall\s*cap\s+250\b",  "NIFTY SMALLCAP 250"),
    (r"\bnifty\s+small\s*cap\s+100\b|\bsmall\s*cap\s+100\b",  "NIFTY SMALLCAP 100"),
    (r"\bnifty\s+small\s*cap\s+50\b|\bsmall\s*cap\s+50\b",    "NIFTY SMALLCAP 50"),
    # Mid cap
    (r"\bnifty\s+mid\s*cap\s+150\b|\bmid\s*cap\s+150\b",      "NIFTY MIDCAP 150"),
    (r"\bnifty\s+mid\s*cap\s+100\b|\bmid\s*cap\s+100\b",      "NIFTY MIDCAP 100"),
    (r"\bnifty\s+mid\s*cap\s+50\b|\bmid\s*cap\s+50\b",        "NIFTY MIDCAP 50"),
    # Broad
    (r"\bnifty\s+next\s+50\b|\bnext\s+50\b",           "NIFTY NEXT 50"),
    (r"\bnifty\s+bank\b|\bbank\s+nifty\b",             "NIFTY BANK"),
    (r"\bsensex\b",                                    "SENSEX"),
    (r"\bnifty\s*500\b",                               "NIFTY 500"),
    (r"\bnifty\s*200\b",                               "NIFTY 200"),
    (r"\bnifty\s*100\b",                               "NIFTY 100"),
    (r"\bnifty\s*50\b",                                "NIFTY 50"),
    # G-Sec
    (r"\b10\s*yr?\b.*\bg.?sec\b|\bg.?sec\b.*\b10\s*yr?\b",   "NIFTY 10 YR BENCHMARK G-SEC"),
    # Hybrid composites
    (r"65\s*:\s*35",                                   "NIFTY 50 HYBRID COMPOSITE DEBT 65:35"),
    (r"50\s*:\s*50",                                   "NIFTY 50 HYBRID COMPOSITE DEBT 50:50"),
    (r"15\s*:\s*85",                                   "NIFTY 50 HYBRID COMPOSITE DEBT 15:85"),
)


MARKET_INDICES: tuple[dict[str, str], ...] = (
    {"key": "nifty50",   "ticker": "^NSEI",             "label": "NIFTY 50"},
    {"key": "sensex",    "ticker": "^BSESN",            "label": "SENSEX"},
    {"key": "nifty200",  "ticker": "^CNX200",           "label": "NIFTY 200"},
    {"key": "midcap",    "ticker": "NIFTYMIDCAP150.NS", "label": "NIFTY MIDCAP 150"},
    {"key": "smallcap",  "ticker": "NIFTYSMLCAP250.NS", "label": "NIFTY SMLCAP 250"},
    {"key": "usdinr",    "ticker": "USDINR=X",          "label": "USD/INR"},
)


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def configure_yfinance_cache(yf_module=None) -> None:
    try:
        cache_dir = Path(tempfile.gettempdir()) / "mfanalysis-yfinance-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if yf_module is not None and hasattr(yf_module, "set_tz_cache_location"):
            yf_module.set_tz_cache_location(str(cache_dir))
        try:
            import yfinance.cache as yf_cache
            yf_cache.set_cache_location(str(cache_dir))
        except Exception:
            pass
    except Exception as exc:
        logger.info("Could not configure yfinance cache directory: %s", exc)


def normalize_benchmark_name(value: str | None) -> str | None:
    """Return the canonical BENCHMARK_DEFINITIONS key for any input string."""
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", str(value).strip().upper())
    if cleaned in BENCHMARK_DEFINITIONS:
        return cleaned
    for name, definition in BENCHMARK_DEFINITIONS.items():
        aliases = (definition.name, *definition.aliases)
        if cleaned in {re.sub(r"\s+", " ", alias.upper()) for alias in aliases}:
            return name
    # Partial match on canonical name
    for name in BENCHMARK_DEFINITIONS:
        if cleaned in name or name in cleaned:
            return name
    return None


def benchmark_for(category: str | None, scheme_name: str = "") -> str:
    """
    Return the canonical benchmark name for a fund category / scheme name.

    Priority:
      1. Exact regex match on combined text
      2. Exact category map lookup
      3. Keyword rules on combined text
      4. NIFTY 50 (universal fallback — always returns something)
    """
    text = f"{category or ''} {scheme_name or ''}".lower()

    # 1. Regex rules (most specific)
    for pattern, benchmark in EXPLICIT_INDEX_RULES:
        if re.search(pattern, text):
            return benchmark

    # 2. Exact category map
    if category and category in CATEGORY_BENCHMARK_MAP:
        return CATEGORY_BENCHMARK_MAP[category]

    # 3. Keyword rules
    for marker, benchmark in CATEGORY_BENCHMARK_RULES:
        if marker in text:
            return benchmark

    # 4. Universal fallback
    return NIFTY50_FALLBACK


def benchmark_display_note(requested: str | None, resolved: "BenchmarkResolution | None") -> str:
    """
    Return a short transparency note for display in the UI.
    Returns empty string when the benchmark resolved cleanly.
    """
    if resolved is None:
        return NIFTY50_FALLBACK_NOTE
    if resolved.fallback_used:
        if resolved.actual_name == NIFTY50_FALLBACK:
            return (
                f"No confirmed Yahoo Finance ticker for '{requested}'. "
                f"NIFTY 50 is used as a proxy — comparisons are approximate."
            )
        return (
            f"'{requested}' resolved via '{resolved.actual_name}' — "
            "comparisons may be approximate."
        )
    return ""


def infer_category(name: str) -> str:
    lower = (name or "").lower()
    for marker, _benchmark in CATEGORY_BENCHMARK_RULES:
        if marker in lower:
            return marker.title()
    return ""


def iter_benchmark_candidates(name: str | None) -> Iterable[BenchmarkCandidate]:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return []
    return list(_iter_benchmark_candidates(canonical, canonical, set(), False))


def _iter_benchmark_candidates(
    requested_name: str,
    current_name: str,
    seen: set[str],
    is_fallback: bool,
) -> Iterable[BenchmarkCandidate]:
    if current_name in seen:
        return
    seen.add(current_name)
    definition = BENCHMARK_DEFINITIONS.get(current_name)
    if not definition:
        return
    for ticker in definition.yahoo_tickers:
        note = ""
        if is_fallback:
            note = (
                f"'{requested_name}' has no reliable Yahoo Finance ticker; "
                f"using '{current_name}' (NIFTY 50) as proxy."
            )
        yield BenchmarkCandidate(
            requested_name, current_name, ticker, definition.field,
            False, is_fallback, note,
        )
    for ticker, note in definition.proxy_tickers:
        yield BenchmarkCandidate(
            requested_name, current_name, ticker, definition.field,
            True, is_fallback, note,
        )
    if definition.fallback:
        fallback = normalize_benchmark_name(definition.fallback)
        if fallback:
            yield from _iter_benchmark_candidates(requested_name, fallback, seen, True)


def primary_yahoo_ticker(name: str | None) -> str:
    for candidate in iter_benchmark_candidates(name):
        return candidate.yahoo_ticker
    return ""


def benchmark_ticker_map() -> dict[str, tuple[str, str]]:
    return {
        name: (ticker, definition.field)
        for name, definition in BENCHMARK_DEFINITIONS.items()
        if (ticker := primary_yahoo_ticker(name))
    }


def resolve_benchmark(name: str | None) -> BenchmarkResolution | None:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return None
    candidates = list(iter_benchmark_candidates(canonical))
    if candidates:
        first = candidates[0]
        tickers = tuple(
            c.yahoo_ticker for c in candidates
            if c.benchmark_name == first.benchmark_name
        )
        fallback_used = first.is_fallback or first.benchmark_name != canonical
        note = first.note
        if fallback_used and not note:
            note = (
                f"'{canonical}' has no reliable Yahoo ticker; "
                f"using '{first.benchmark_name}' as proxy."
            )
        return BenchmarkResolution(canonical, first.benchmark_name, tickers, fallback_used, note)

    definition = BENCHMARK_DEFINITIONS.get(canonical)
    if definition and definition.fallback:
        fallback = normalize_benchmark_name(definition.fallback)
        fallback_candidates = list(iter_benchmark_candidates(fallback))
        if fallback and fallback_candidates:
            tickers = tuple(c.yahoo_ticker for c in fallback_candidates)
            return BenchmarkResolution(
                canonical, fallback, tickers, True,
                f"'{canonical}' has no reliable Yahoo ticker; using '{fallback}' as proxy.",
            )
    return BenchmarkResolution(canonical, canonical, ())


def yahoo_ticker_map() -> dict[str, tuple[str, str]]:
    return benchmark_ticker_map()


def market_strip_indices() -> list[dict[str, str]]:
    items = []
    for item in MARKET_INDICES:
        benchmark = "USD/INR" if item["ticker"] == "USDINR=X" else item["label"]
        items.append({
            "key": item["key"],
            "benchmark": benchmark,
            "label": item["label"],
            "ticker": item["ticker"],
        })
    return items


BENCHMARK_TICKERS = benchmark_ticker_map()


# ── Yahoo Finance fetch ───────────────────────────────────────────────────────

def fetch_yahoo_history_for_benchmark(
    name: str | None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    period: str = "max",
    min_rows: int = 2,
    deadline: "float | None" = None,
) -> "tuple[pd.Series, BenchmarkCandidate | None]":
    import time
    if deadline is None:
        deadline = time.monotonic() + 10

    for candidate in iter_benchmark_candidates(name):
        series = fetch_yahoo_history_for_candidate(
            candidate,
            start_date=start_date, end_date=end_date, period=period, min_rows=min_rows,
        )
        if not series.empty:
            series.attrs["benchmark_candidate"] = candidate
            return series, candidate

    import time as _time
    if _time.monotonic() >= deadline:
        logger.info("Benchmark fetch deadline exceeded for %s (skipping niftyindices+nse)", name)
        return pd.Series(dtype=float), None

    series, candidate = fetch_niftyindices_history_for_benchmark(
        name, start_date=start_date, end_date=end_date, min_rows=min_rows, deadline=deadline,
    )
    if not series.empty:
        series.attrs["benchmark_candidate"] = candidate
        return series, candidate

    if _time.monotonic() >= deadline:
        logger.info("Benchmark fetch deadline exceeded for %s (skipping nse)", name)
        return pd.Series(dtype=float), None

    series, candidate = fetch_nse_history_for_benchmark(
        name, start_date=start_date, end_date=end_date, min_rows=min_rows,
    )
    if not series.empty:
        series.attrs["benchmark_candidate"] = candidate
        return series, candidate
    return pd.Series(dtype=float), None


def fetch_yahoo_history_for_candidate(
    candidate: BenchmarkCandidate,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    period: str = "max",
    min_rows: int = 2,
) -> pd.Series:
    cache_key = _cache_key("benchmark:yahoo:v7", candidate.yahoo_ticker, start_date or period, end_date or "")
    try:
        from django.core.cache import cache
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        cache = None

    try:
        import yfinance as yf
        configure_yfinance_cache(yf)
        ticker = yf.Ticker(candidate.yahoo_ticker)
        kwargs = {"auto_adjust": False}
        if start_date:
            kwargs["start"] = start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date)
            if end_date:
                parsed_end = pd.Timestamp(end_date).date()
                kwargs["end"] = (parsed_end + timedelta(days=1)).isoformat()
        else:
            kwargs["period"] = period
        try:
            hist = ticker.history(**kwargs, raise_errors=False)
        except TypeError:
            hist = ticker.history(**kwargs)
        field = "Adj Close" if candidate.is_proxy and hist is not None and "Adj Close" in hist else candidate.field
        series = _extract_close_series(hist, field)
        if len(series) < min_rows:
            logger.info(
                "Benchmark candidate %s/%s skipped: only %s rows",
                candidate.benchmark_name, candidate.yahoo_ticker, len(series),
            )
            return pd.Series(dtype=float)
        series.attrs["benchmark_candidate"] = candidate
        try:
            cache.set(cache_key, series, BENCHMARK_TTL)
        except Exception:
            pass
        return series
    except Exception as exc:
        logger.info(
            "Benchmark candidate fetch failed for %s/%s: %s",
            candidate.benchmark_name, candidate.yahoo_ticker, exc,
        )
        return pd.Series(dtype=float)


def fetch_nse_history_for_benchmark(
    name: str | None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    min_rows: int = 2,
) -> tuple[pd.Series, BenchmarkCandidate | None]:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return pd.Series(dtype=float), None
    definition = BENCHMARK_DEFINITIONS.get(canonical)
    if not definition:
        return pd.Series(dtype=float), None
    nse_name = definition.nse_name or definition.name
    candidate = BenchmarkCandidate(canonical, canonical, f"NSE:{nse_name}", definition.field, source="nse")
    cache_key = _cache_key("benchmark:nse:v4", nse_name, start_date or "max", end_date or "")
    try:
        from django.core.cache import cache
        cached = cache.get(cache_key)
        if cached is not None:
            return cached, candidate
    except Exception:
        cache = None

    try:
        start = pd.Timestamp(start_date).date() if start_date else date(2000, 1, 1)
    except Exception:
        start = date(2000, 1, 1)
    try:
        end = pd.Timestamp(end_date).date() if end_date else date.today()
    except Exception:
        end = date.today()
    rows = []
    try:
        session = _make_nse_session()
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=365), end)
            url = (
                "https://www.nseindia.com/api/historical/indicesHistory"
                f"?indexType={requests.utils.quote(nse_name)}"
                f"&from={chunk_start.strftime('%d-%m-%Y')}"
                f"&to={chunk_end.strftime('%d-%m-%Y')}"
            )
            response = session.get(url, timeout=20)
            response.raise_for_status()
            raw = response.json().get("data", {}).get("indexCloseOnlineRecords", [])
            for row in raw:
                try:
                    rows.append((
                        datetime.strptime(row["EOD_TIMESTAMP"], "%d-%b-%Y").date(),
                        float(row["EOD_CLOSE_INDEX_VAL"]),
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
            chunk_start = chunk_end + timedelta(days=1)
    except Exception as exc:
        logger.info("NSE benchmark fetch failed for %s: %s", nse_name, exc)
        return pd.Series(dtype=float), candidate

    if len(rows) < min_rows:
        logger.info("NSE benchmark %s skipped: only %s rows", nse_name, len(rows))
        return pd.Series(dtype=float), candidate
    series = pd.Series({pd.Timestamp(d): v for d, v in rows}).sort_index()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    try:
        cache.set(cache_key, series, BENCHMARK_TTL)
    except Exception:
        pass
    return series, candidate


def fetch_niftyindices_history_for_benchmark(
    name: str | None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    min_rows: int = 2,
    deadline: "float | None" = None,
) -> tuple[pd.Series, BenchmarkCandidate | None]:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return pd.Series(dtype=float), None
    definition = BENCHMARK_DEFINITIONS.get(canonical)
    if not definition:
        return pd.Series(dtype=float), None

    requested_index = definition.nse_name or definition.name
    candidate = BenchmarkCandidate(
        canonical, canonical, f"NIFTYINDICES:{requested_index}", definition.field, source="niftyindices",
    )
    cache_key = _cache_key("benchmark:niftyindices:v2", requested_index, start_date or "max", end_date or "")
    try:
        from django.core.cache import cache
        cached = cache.get(cache_key)
        if cached is not None:
            return cached, candidate
    except Exception:
        cache = None

    try:
        start = pd.Timestamp(start_date).date() if start_date else date(2000, 1, 1)
    except Exception:
        start = date(2000, 1, 1)
    try:
        end = pd.Timestamp(end_date).date() if end_date else date.today()
    except Exception:
        end = date.today()
    if start > end:
        return pd.Series(dtype=float), candidate

    rows = []
    try:
        import time as _time
        session = _make_niftyindices_session()
        index_name = _niftyindices_trading_name(session, requested_index)
        chunk_start = start
        while chunk_start <= end:
            if deadline is not None and _time.monotonic() >= deadline:
                logger.info("Nifty Indices deadline exceeded for %s, aborting chunk loop", requested_index)
                break
            chunk_end = min(chunk_start + timedelta(days=365), end)
            rows.extend(_fetch_niftyindices_rows(session, index_name, requested_index, chunk_start, chunk_end))
            chunk_start = chunk_end + timedelta(days=1)
    except Exception as exc:
        logger.info("Nifty Indices benchmark fetch failed for %s: %s", requested_index, exc)
        return pd.Series(dtype=float), candidate

    if len(rows) < min_rows:
        logger.info("Nifty Indices benchmark %s skipped: only %s rows", requested_index, len(rows))
        return pd.Series(dtype=float), candidate
    latest_row_date = max(d for d, _ in rows)
    if (end - latest_row_date).days > 45:
        logger.info("Nifty Indices benchmark %s skipped: latest row is %s", requested_index, latest_row_date)
        return pd.Series(dtype=float), candidate
    series = pd.Series({pd.Timestamp(d): v for d, v in rows}).sort_index()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    series = series[~series.index.duplicated(keep="last")]
    try:
        cache.set(cache_key, series, BENCHMARK_TTL)
    except Exception:
        pass
    return series, candidate


def _fetch_niftyindices_rows(
    session: requests.Session,
    index_name: str,
    requested_index: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    try:
        return _fetch_niftyindices_rows_once(session, index_name, requested_index, start, end)
    except Exception as exc:
        span = (end - start).days
        if span <= 92:
            logger.info("Nifty Indices chunk skipped for %s %s..%s: %s", requested_index, start, end, exc)
            return []
        mid = start + timedelta(days=span // 2)
        return (
            _fetch_niftyindices_rows(session, index_name, requested_index, start, mid)
            + _fetch_niftyindices_rows(session, index_name, requested_index, mid + timedelta(days=1), end)
        )


def _fetch_niftyindices_rows_once(
    session: requests.Session,
    index_name: str,
    requested_index: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    payload = {
        "cinfo": (
            "{'name':'" + index_name.upper().strip() +
            "','startDate':'" + start.strftime("%d-%b-%Y") +
            "','endDate':'" + end.strftime("%d-%b-%Y") +
            "','indexName':'" + requested_index + "'}"
        )
    }
    last_exc: Exception | None = None
    for timeout in (5, 8):
        try:
            response = session.post(
                f"{NIFTYINDICES_BASE}/Backpage.aspx/getHistoricaldatatabletoString",
                data=json.dumps(payload),
                timeout=timeout,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Origin": NIFTYINDICES_BASE,
                    "Referer": f"{NIFTYINDICES_BASE}/reports/historical-data",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            response.raise_for_status()
            raw = response.json().get("d") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            rows = []
            for row in raw:
                try:
                    rows.append((
                        datetime.strptime(row["HistoricalDate"], "%d %b %Y").date(),
                        float(str(row["CLOSE"]).replace(",", "")),
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
            return rows
        except Exception as exc:
            last_exc = exc
    raise last_exc or RuntimeError("Nifty Indices returned no response")


def _make_niftyindices_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        session.get(f"{NIFTYINDICES_BASE}/reports/historical-data", timeout=5)
    except Exception as exc:
        logger.info("Nifty Indices warmup warning: %s", exc)
    return session


def _niftyindices_trading_name(session: requests.Session, index_name: str) -> str:
    try:
        response = session.get(f"{NIFTYINDICES_ASSET_BASE}/assets/json/IndexMapping.json", timeout=15)
        response.raise_for_status()
        data = json.loads(response.content.decode("utf-8-sig"))
        target = _compact_index_name(index_name)
        for row in data:
            long_name = _compact_index_name(row.get("Index_long_name"))
            trading_name = _compact_index_name(row.get("Trading_Index_Name"))
            if target in {long_name, trading_name}:
                return str(row.get("Trading_Index_Name") or index_name)
    except Exception as exc:
        logger.info("Nifty Indices mapping fetch failed for %s: %s", index_name, exc)
    return index_name


def _compact_index_name(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def _make_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com/", timeout=10)
        session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)
    except Exception as exc:
        logger.info("NSE warmup warning: %s", exc)
    return session


def _cache_key(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}:{md5(raw.encode('utf-8')).hexdigest()}"


def _extract_close_series(hist, field: str) -> pd.Series:
    if hist is None or getattr(hist, "empty", True):
        return pd.Series(dtype=float)
    close_field = field if field in hist else "Close"
    if close_field not in hist:
        return pd.Series(dtype=float)
    series = pd.to_numeric(hist[close_field], errors="coerce").dropna()
    if series.empty:
        return pd.Series(dtype=float)
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    series = series[~series.index.duplicated(keep="last")]
    return series.sort_index()
