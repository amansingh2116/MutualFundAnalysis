"""
Peer discovery for Indian mutual fund schemes.

The matcher intentionally works from the fields available on ``Scheme`` because
the local AMFI-derived registry often has an empty ``scheme_category``.  It
builds a lightweight fingerprint from the scheme name and metadata, then ranks
same-plan/same-direct candidates by match quality before AUM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from apps.funds.models import Scheme


class FundKind(str, Enum):
    ACTIVE_EQUITY = "active_equity"
    ACTIVE_DEBT = "active_debt"
    ACTIVE_HYBRID = "active_hybrid"
    INDEX_FUND = "index_fund"
    ETF = "etf"
    FOF_DOMESTIC = "fof_domestic"
    FOF_OVERSEAS = "fof_overseas"
    COMMODITY = "commodity"
    SOLUTION = "solution"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FundFingerprint:
    raw_name: str
    norm_name: str
    norm_category: str
    norm_type: str
    kind: FundKind
    cat_key: str
    sector: str
    index_group: str
    commodity_group: str
    fof_region: str
    fof_asset: str
    solution_type: str
    plan: str
    is_direct: bool
    fund_house: str


@dataclass(frozen=True)
class PeerMatch:
    scheme: Scheme
    score: int
    match_reason: str
    match_group: str


EQUITY_CATEGORY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("large_mid_cap", ("large and mid cap", "large mid cap", "large & mid cap")),
    ("small_cap", ("small cap", "smallcap", "small-cap")),
    ("mid_cap", ("mid cap", "midcap", "mid-cap")),
    ("large_cap", ("large cap", "largecap", "large-cap", "bluechip", "blue chip")),
    ("multi_cap", ("multi cap", "multicap", "multi-cap")),
    ("flexi_cap", ("flexi cap", "flexicap", "flexi-cap")),
    ("focused", ("focused fund", "focus fund", "focused equity")),
    ("elss", ("elss", "tax saver", "tax saving", "equity linked saving", "long term equity")),
    ("value", ("value fund", "value and contra", "value advantage")),
    ("contra", ("contra fund", "contra")),
    ("dividend_yield", ("dividend yield",)),
    ("sectoral", ("sectoral", "sector fund", "sectoral fund")),
    ("thematic", ("thematic", "theme fund", "opportunities fund")),
]

DEBT_CATEGORY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("overnight", ("overnight",)),
    ("liquid", ("liquid fund", "liquid plan", "liquid")),
    ("ultra_short_duration", ("ultra short duration", "ultra short", "ultrashort")),
    ("low_duration", ("low duration",)),
    ("money_market", ("money market",)),
    ("short_duration", ("short duration", "short term")),
    ("medium_long_duration", ("medium to long duration", "medium and long duration", "medium long duration")),
    ("medium_duration", ("medium duration",)),
    ("long_duration", ("long duration", "long term")),
    ("dynamic_bond", ("dynamic bond", "dynamic debt")),
    ("corporate_bond", ("corporate bond", "corp bond")),
    ("credit_risk", ("credit risk", "credit opportunities")),
    ("banking_psu", ("banking and psu", "banking psu", "banking & psu")),
    ("gilt_10yr", ("gilt with 10 year", "gilt 10 year", "constant duration")),
    ("gilt", ("gilt", "g-sec", "gsec")),
    ("floater", ("floater", "floating rate")),
]

HYBRID_CATEGORY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("conservative_hybrid", ("conservative hybrid",)),
    ("balanced_hybrid", ("balanced hybrid",)),
    ("aggressive_hybrid", ("aggressive hybrid", "equity hybrid")),
    ("multi_asset", ("multi asset allocation", "multi asset", "multi-asset")),
    ("balanced_advantage", ("balanced advantage", "dynamic asset allocation")),
    ("arbitrage", ("arbitrage",)),
    ("equity_savings", ("equity savings",)),
]

SECTOR_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("banking_finance", ("banking", "financial services", "financial", "finserv", "bfsi", "bank nifty")),
    ("pharma_health", ("pharma", "pharmaceutical", "healthcare", "health care", "hospital", "medic")),
    ("technology", ("technology", "information technology", "software", "digital india", " it ")),
    ("infrastructure", ("infrastructure", "infra")),
    ("fmcg_consumption", ("fmcg", "consumption", "consumer goods", "consumer")),
    ("auto", ("auto", "automobile", "mobility", "transportation", "logistics")),
    ("energy_power", ("energy", "power", "utilities", "oil and gas", "oil & gas")),
    ("psu", ("psu", "public sector", "cpse", "bharat 22")),
    ("metals_mining", ("metal", "mining", "commodities", "steel")),
    ("defence", ("defence", "defense", "aerospace")),
    ("manufacturing", ("manufacturing", "make in india", "industrial")),
    ("realty", ("realty", "real estate")),
    ("mnc", ("mnc", "multinational")),
    ("esg", ("esg", "sustainable", "responsible investing")),
    ("business_cycle", ("business cycle",)),
    ("quant_factor", ("quant fund", "momentum", "alpha", "low volatility", "quality")),
    ("services", ("services sector", "service industry")),
]

INDEX_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("nifty_next_50", ("nifty next 50", "next 50")),
    ("nifty_50_equal_weight", ("nifty 50 equal weight", "nifty50 equal weight")),
    ("nifty_50", ("nifty 50", "nifty50")),
    ("sensex", ("bse sensex", "sensex")),
    ("nifty_100_equal_weight", ("nifty 100 equal weight", "nifty100 equal weight")),
    ("nifty_100", ("nifty 100", "nifty100")),
    ("nifty_200", ("nifty 200", "nifty200")),
    ("nifty_500", ("nifty 500", "nifty500")),
    ("nifty_midcap_50", ("nifty midcap 50", "midcap 50")),
    ("nifty_midcap_100", ("nifty midcap 100", "midcap 100")),
    ("nifty_midcap_150", ("nifty midcap 150", "midcap 150")),
    ("nifty_smallcap_50", ("nifty smallcap 50", "smallcap 50")),
    ("nifty_smallcap_250", ("nifty smallcap 250", "smallcap 250")),
    ("nifty_midsmallcap_400", ("midsmallcap 400", "mid small cap 400")),
    ("nifty_microcap_250", ("microcap 250",)),
    ("nifty_multicap_503020", ("multicap 50 30 20", "multicap 50:30:20")),
    ("nifty_alpha_50", ("alpha 50",)),
    ("nifty_quality_30", ("quality 30",)),
    ("nifty_momentum_30", ("momentum 30",)),
    ("nifty_low_vol_50", ("low volatility 50", "low vol 50")),
    ("nifty_value_20", ("value 20",)),
    ("nasdaq_100", ("nasdaq 100", "nasdaq100")),
    ("us_tech", ("nyse fang", "fang", "us tech")),
    ("sp_500", ("s and p 500", "s p 500", "s&p 500", "sp 500")),
    ("msci_world", ("msci world",)),
    ("msci_emerging", ("msci emerging", "msci em", "emerging markets")),
    ("hang_seng", ("hang seng",)),
]

COMMODITY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("gold", ("gold",)),
    ("silver", ("silver",)),
]

FOF_OVERSEAS_MARKERS = (
    "nasdaq", "s and p", "s&p", "sp 500", "usa", "us ", "united states",
    "international", "overseas", "global", "world", "china", "europe",
    "japan", "hang seng", "taiwan", "korea", "brazil", "latin america",
    "msci", "emerging market", "fang", "nyse",
)

FOF_REGION_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("us", ("usa", "us ", "united states", "nasdaq", "s and p", "s&p", "sp 500", "fang", "nyse")),
    ("china", ("china", "hang seng")),
    ("europe", ("europe",)),
    ("japan", ("japan",)),
    ("emerging_markets", ("emerging market", "msci em")),
    ("global", ("global", "world", "international", "overseas")),
]

FOF_DEBT_MARKERS = ("treasury", "bond", "debt", "gilt", "income")
FOF_EQUITY_MARKERS = ("equity", "nasdaq", "fang", "eqqq", "s and p", "s&p", "sp 500", "index", "passive")

BROAD_CATEGORY_NAMES = (
    "sectoral", "thematic", "index", "etf", "fund of fund", "fof", "other scheme",
)


def _norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _has(source: str, pattern: str) -> bool:
    pattern = _norm(pattern)
    if not pattern:
        return False
    return f" {pattern} " in f" {source} "


def _first_match(source: str, patterns: Iterable[tuple[str, tuple[str, ...]]]) -> str:
    for key, aliases in patterns:
        if any(_has(source, alias) for alias in aliases):
            return key
    return ""


def _combined(*parts: object) -> str:
    return _norm(" ".join(str(p or "") for p in parts))


def _is_fof(source: str) -> bool:
    return any(_has(source, marker) for marker in ("fund of fund", "fund of funds", "fof", "feeder fund"))


def _is_etf(source: str) -> bool:
    return _has(source, "etf") or _has(source, "exchange traded")


def _is_index_fund(source: str) -> bool:
    return _has(source, "index fund") or _has(source, "index")


def _is_overseas_fof(source: str) -> bool:
    return any(_has(source, marker) for marker in FOF_OVERSEAS_MARKERS)


def _is_broad_category(category: str) -> bool:
    return any(_has(category, marker) for marker in BROAD_CATEGORY_NAMES)


def _category_key(source: str, kind: FundKind) -> str:
    if kind == FundKind.ACTIVE_DEBT:
        return _first_match(source, DEBT_CATEGORY_PATTERNS)
    if kind == FundKind.ACTIVE_HYBRID:
        return _first_match(source, HYBRID_CATEGORY_PATTERNS)
    if kind == FundKind.ACTIVE_EQUITY:
        return _first_match(source, EQUITY_CATEGORY_PATTERNS)
    return ""


def _detect_kind(norm_name: str, norm_category: str, norm_type: str) -> FundKind:
    source = _combined(norm_name, norm_category, norm_type)

    if any(_has(source, marker) for marker in ("elss", "tax saver", "tax saving", "equity linked saving")):
        return FundKind.ACTIVE_EQUITY
    if _is_fof(source):
        return FundKind.FOF_OVERSEAS if _is_overseas_fof(source) else FundKind.FOF_DOMESTIC
    if _is_etf(source):
        return FundKind.ETF
    if _is_index_fund(source):
        return FundKind.INDEX_FUND
    if _first_match(source, COMMODITY_PATTERNS):
        return FundKind.COMMODITY
    if _has(source, "retirement") or _has(source, "children") or _has(source, "childrens") or _has(source, "child"):
        return FundKind.SOLUTION

    # Debt first prevents "Banking & PSU Debt" from becoming banking-sector equity.
    if _first_match(source, DEBT_CATEGORY_PATTERNS) or _has(source, "debt") or _has(source, "bond"):
        return FundKind.ACTIVE_DEBT
    if _first_match(source, HYBRID_CATEGORY_PATTERNS) or _has(source, "hybrid"):
        return FundKind.ACTIVE_HYBRID
    if _first_match(source, EQUITY_CATEGORY_PATTERNS) or _first_match(source, SECTOR_PATTERNS) or _has(source, "equity"):
        return FundKind.ACTIVE_EQUITY

    if _has(norm_type, "debt"):
        return FundKind.ACTIVE_DEBT
    if _has(norm_type, "hybrid"):
        return FundKind.ACTIVE_HYBRID
    if _has(norm_type, "equity"):
        return FundKind.ACTIVE_EQUITY
    return FundKind.UNKNOWN


def build_fingerprint(scheme: Scheme) -> FundFingerprint:
    norm_name = _norm(scheme.scheme_name)
    norm_category = _norm(scheme.scheme_category)
    norm_type = _norm(scheme.scheme_type)
    source = _combined(norm_category, norm_name, norm_type)
    kind = _detect_kind(norm_name, norm_category, norm_type)
    cat_key = _category_key(source, kind)
    sector = _first_match(source, SECTOR_PATTERNS) if kind == FundKind.ACTIVE_EQUITY else ""
    index_group = _first_match(source, INDEX_PATTERNS)
    commodity_group = _first_match(source, COMMODITY_PATTERNS)
    fof_region = _first_match(source, FOF_REGION_PATTERNS) if kind in (FundKind.FOF_DOMESTIC, FundKind.FOF_OVERSEAS) else ""
    fof_asset = ""
    if kind in (FundKind.FOF_DOMESTIC, FundKind.FOF_OVERSEAS):
        if any(_has(source, marker) for marker in FOF_DEBT_MARKERS):
            fof_asset = "debt"
        elif any(_has(source, marker) for marker in FOF_EQUITY_MARKERS):
            fof_asset = "equity"
    solution_type = ""
    if kind == FundKind.SOLUTION:
        solution_type = "retirement" if _has(source, "retirement") else "children"

    return FundFingerprint(
        raw_name=scheme.scheme_name or "",
        norm_name=norm_name,
        norm_category=norm_category,
        norm_type=norm_type,
        kind=kind,
        cat_key=cat_key,
        sector=sector,
        index_group=index_group,
        commodity_group=commodity_group,
        fof_region=fof_region,
        fof_asset=fof_asset,
        solution_type=solution_type,
        plan=(scheme.plan or "GROWTH").upper(),
        is_direct=bool(scheme.is_direct),
        fund_house=_norm(scheme.fund_house),
    )


def _score_match(base: FundFingerprint, candidate: FundFingerprint) -> tuple[int, str, str] | None:
    if base.norm_category and base.norm_category == candidate.norm_category and not _is_broad_category(base.norm_category):
        return 1000, f"Same SEBI category: {base.norm_category}", f"category:{base.norm_category}"

    if base.cat_key == "elss" and candidate.cat_key == "elss":
        return 980, "Both are ELSS tax-saving equity funds", "equity:elss"

    if base.cat_key in {"value", "contra"} and candidate.cat_key in {"value", "contra"}:
        return 960, "Same Value/Contra peer family", "equity:value_contra"

    if base.kind == FundKind.SOLUTION and candidate.kind == FundKind.SOLUTION and base.solution_type == candidate.solution_type:
        return 950, f"Same solution-oriented type: {base.solution_type}", f"solution:{base.solution_type}"

    if base.commodity_group and base.commodity_group == candidate.commodity_group:
        return 930, f"Same commodity exposure: {base.commodity_group}", f"commodity:{base.commodity_group}"

    passive_kinds = {FundKind.ETF, FundKind.INDEX_FUND}
    if base.kind in passive_kinds and candidate.kind in passive_kinds:
        if base.index_group and base.index_group == candidate.index_group:
            return 920, f"Both track the same index group: {base.index_group}", f"index:{base.index_group}"
        return None

    fof_kinds = {FundKind.FOF_DOMESTIC, FundKind.FOF_OVERSEAS}
    if base.kind in fof_kinds and candidate.kind in fof_kinds:
        if base.kind != candidate.kind:
            return None
        if base.fof_asset and candidate.fof_asset and base.fof_asset != candidate.fof_asset:
            return None
        if base.index_group and base.index_group == candidate.index_group:
            return 900, f"Same FoF index exposure: {base.index_group}", f"fof_index:{base.index_group}"
        if base.fof_region and base.fof_region == candidate.fof_region:
            return 850, f"Same FoF geography: {base.fof_region}", f"fof_region:{base.fof_region}"
        return 500, f"Same FoF type: {base.kind.value}", f"fof:{base.kind.value}"

    if base.kind == FundKind.ACTIVE_EQUITY and candidate.kind == FundKind.ACTIVE_EQUITY:
        sectoral_base = base.cat_key in {"sectoral", "thematic"} or bool(base.sector)
        sectoral_candidate = candidate.cat_key in {"sectoral", "thematic"} or bool(candidate.sector)
        if sectoral_base or sectoral_candidate:
            if base.sector and base.sector == candidate.sector:
                return 880, f"Same sector/theme: {base.sector}", f"sector:{base.sector}"
            return None

    if base.kind == candidate.kind and base.cat_key and base.cat_key == candidate.cat_key:
        return 800, f"Same fund category from name: {base.cat_key}", f"{base.kind.value}:{base.cat_key}"

    has_specific_signal = any((
        base.cat_key,
        base.sector,
        base.index_group,
        base.commodity_group,
        base.fof_region,
        base.solution_type,
    ))
    if has_specific_signal:
        return None

    if base.kind == candidate.kind and base.kind != FundKind.UNKNOWN:
        return 150, f"Same broad fund type: {base.kind.value}", f"kind:{base.kind.value}"

    if base.norm_type and base.norm_type == candidate.norm_type:
        return 150, f"Same broad scheme type: {base.norm_type}", f"type:{base.norm_type}"

    return None


def _aum_rank_value(scheme: Scheme) -> float:
    if scheme.aum_cr is None:
        return -1.0
    return float(scheme.aum_cr)


def get_peer_matches(scheme: Scheme, max_peers: int = 5) -> list[PeerMatch]:
    max_peers = max(0, min(int(max_peers), 8))
    if max_peers == 0:
        return []

    base_fp = build_fingerprint(scheme)
    candidates = (
        Scheme.objects
        .filter(plan=base_fp.plan, is_direct=base_fp.is_direct, is_active=True)
        .exclude(amfi_code=scheme.amfi_code)
        .exclude(fund_house__iexact=(scheme.fund_house or "").strip())
    )

    best_by_house: dict[str, tuple[PeerMatch, float, str]] = {}
    for candidate in candidates:
        candidate_fp = build_fingerprint(candidate)
        scored = _score_match(base_fp, candidate_fp)
        if scored is None:
            continue
        score, reason, group = scored
        aum_value = _aum_rank_value(candidate)
        name_key = candidate.scheme_name or ""
        match = PeerMatch(candidate, score, reason, group)
        house_key = candidate_fp.fund_house or candidate.amfi_code
        current = best_by_house.get(house_key)
        sort_tuple = (score, aum_value, _reverse_name_key(name_key))
        if current is None or sort_tuple > (current[0].score, current[1], _reverse_name_key(current[2])):
            best_by_house[house_key] = (match, aum_value, name_key)

    ranked = sorted(
        (item[0] for item in best_by_house.values()),
        key=lambda match: (-match.score, -_aum_rank_value(match.scheme), match.scheme.scheme_name or ""),
    )
    return ranked[:max_peers]


def _reverse_name_key(name: str) -> tuple[int, ...]:
    # Used only for "is this candidate better than the current same-house pick?"
    # Lower alphabetical names should win, so invert code points for max().
    return tuple(-ord(ch) for ch in name)


def explain_peer_match(scheme: Scheme, peer: Scheme) -> str:
    base_fp = build_fingerprint(scheme)
    peer_fp = build_fingerprint(peer)
    scored = _score_match(base_fp, peer_fp)
    return scored[1] if scored else "No peer match"
