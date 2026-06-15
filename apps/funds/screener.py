"""Derived data helpers for the mutual fund screener."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

from django.utils import timezone

from apps.benchmarks.registry import BENCHMARK_DEFINITIONS, benchmark_for, infer_category


CATEGORY_GROUPS = ("Debt", "Equity", "Hybrid", "Other", "Solution Oriented")

SUB_CATEGORY_PATTERNS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Banking and PSU Fund", ("banking and psu", "banking & psu"), "Debt"),
    ("Corporate Bond Fund", ("corporate bond",), "Debt"),
    ("Credit Risk Fund", ("credit risk",), "Debt"),
    ("Dynamic Bond", ("dynamic bond",), "Debt"),
    ("Floater Fund", ("floater",), "Debt"),
    ("Gilt Fund with 10 year constant duration", ("10 year constant", "10 yr constant"), "Debt"),
    ("Gilt Fund", ("gilt", "g-sec", "gsec"), "Debt"),
    ("Liquid Fund", ("liquid fund", "liquid plan"), "Debt"),
    ("Long Duration Fund", ("long duration",), "Debt"),
    ("Low Duration Fund", ("low duration",), "Debt"),
    ("Medium to Long Duration Fund", ("medium to long", "medium and long"), "Debt"),
    ("Medium Duration Fund", ("medium duration",), "Debt"),
    ("Money Market Fund", ("money market",), "Debt"),
    ("Overnight Fund", ("overnight",), "Debt"),
    ("Short Duration Fund", ("short duration", "short term"), "Debt"),
    ("Ultra Short Duration Fund", ("ultra short", "ultrashort"), "Debt"),
    ("Contra Fund", ("contra fund",), "Equity"),
    ("Dividend Yield Fund", ("dividend yield",), "Equity"),
    ("ELSS", ("elss", "tax saver", "tax saving"), "Equity"),
    ("Flexi Cap Fund", ("flexi cap", "flexicap"), "Equity"),
    ("Focused Fund", ("focused fund", "focus fund"), "Equity"),
    ("Large & Mid Cap Fund", ("large & mid", "large and mid"), "Equity"),
    ("Large Cap Fund", ("large cap", "largecap", "bluechip", "blue chip"), "Equity"),
    ("Mid Cap Fund", ("mid cap", "midcap", "mid-cap"), "Equity"),
    ("Multi Cap Fund", ("multi cap", "multicap"), "Equity"),
    ("Sectoral/ Thematic", ("sectoral", "thematic", "theme"), "Equity"),
    ("Small Cap Fund", ("small cap", "smallcap", "small-cap"), "Equity"),
    ("Value Fund", ("value fund", "value and contra"), "Equity"),
    ("Aggressive Hybrid Fund", ("aggressive hybrid", "equity hybrid"), "Hybrid"),
    ("Arbitrage Fund", ("arbitrage",), "Hybrid"),
    ("Conservative Hybrid Fund", ("conservative hybrid",), "Hybrid"),
    ("Dynamic Asset Allocation or Balanced Advantage", ("balanced advantage", "dynamic asset allocation"), "Hybrid"),
    ("Equity Savings", ("equity savings",), "Hybrid"),
    ("Multi Asset Allocation", ("multi asset", "multi-asset"), "Hybrid"),
    ("FoF Domestic", ("fof domestic", "fund of fund domestic"), "Other"),
    ("FoF Overseas", ("fof overseas", "overseas", "international", "global", "nasdaq", "s&p 500"), "Other"),
    ("Gold ETF", ("gold etf", "gold exchange traded"), "Other"),
    ("Index Funds", ("index fund", "index funds"), "Other"),
    ("Other ETFs", ("etf",), "Other"),
    ("Children's Fund", ("children", "child"), "Solution Oriented"),
    ("Retirement Fund", ("retirement",), "Solution Oriented"),
)


def refresh_snapshot_for_scheme(scheme):
    """Build and persist a screener snapshot for one scheme."""
    from apps.analytics.models import RiskMetrics, RollingReturn, TrailingReturn
    from apps.funds.models import FundScreenerSnapshot, NAVHistory

    latest_trailing = _latest_rows_by_key(
        TrailingReturn.objects.filter(scheme=scheme).order_by("period", "-as_of"),
        "period",
    )
    latest_rolling = _latest_rows_by_key(
        RollingReturn.objects.filter(scheme=scheme).order_by("window", "-as_of"),
        "window",
    )
    latest_risk = _latest_rows_by_key(
        RiskMetrics.objects.filter(scheme=scheme).order_by("period", "-as_of"),
        "period",
    )

    meta = getattr(scheme, "meta", None)
    first_nav_date = (
        NAVHistory.objects.filter(scheme=scheme).order_by("date").values_list("date", flat=True).first()
    )
    latest_nav_date = scheme.nav_date or (
        NAVHistory.objects.filter(scheme=scheme).order_by("-date").values_list("date", flat=True).first()
    )

    category_text = _category_text(scheme, meta)
    category_group, sub_category = classify_scheme(category_text, scheme.scheme_name)
    benchmark_name = benchmark_for(category_text, scheme.scheme_name) or benchmark_for(sub_category, scheme.scheme_name) or ""
    benchmark_type = classify_benchmark(benchmark_name)
    fund_age_years = _fund_age_years(
        getattr(meta, "start_date", None) or first_nav_date,
        latest_nav_date or timezone.localdate(),
    )

    trailing_1y = latest_trailing.get("1Y")
    trailing_3y = latest_trailing.get("3Y")
    trailing_5y = latest_trailing.get("5Y")
    rolling_3y = latest_rolling.get("3Y")
    risk_3y = latest_risk.get("3Y")

    volatility = _decimal(getattr(risk_3y, "std_dev_ann", None))
    if volatility is None:
        volatility = _decimal(getattr(meta, "volatility", None))

    analytics_dates = [
        getattr(row, "as_of", None)
        for row in [trailing_1y, trailing_3y, trailing_5y, rolling_3y, risk_3y]
        if row is not None
    ]
    data_as_of = max([d for d in [latest_nav_date, *analytics_dates] if d], default=timezone.localdate())

    snapshot, _ = FundScreenerSnapshot.objects.update_or_create(
        scheme=scheme,
        defaults={
            "fund_name": scheme.scheme_name,
            "fund_house": clean_fund_house(scheme.fund_house),
            "category_group": category_group,
            "scheme_sub_category": sub_category,
            "income_type": infer_income_type(scheme.scheme_name, scheme.plan),
            "plan_type": infer_plan_type(scheme.scheme_name, scheme.is_direct),
            "is_direct": scheme.is_direct,
            "is_etf": is_etf(scheme.scheme_name),
            "benchmark_type": benchmark_type,
            "benchmark_name": benchmark_name,
            "risk_label": risk_label(volatility),
            "aum_cr": _decimal(scheme.aum_cr or getattr(meta, "aum", None)),
            "expense_ratio": _decimal(scheme.expense_ratio or getattr(meta, "expense_ratio", None)),
            "fund_age_years": fund_age_years,
            "returns_1y_pct": _decimal(getattr(trailing_1y, "cagr_pct", None) or getattr(meta, "returns_1y", None)),
            "returns_3y_pct": _decimal(getattr(trailing_3y, "cagr_pct", None) or getattr(meta, "returns_3y", None)),
            "returns_5y_pct": _decimal(getattr(trailing_5y, "cagr_pct", None) or getattr(meta, "returns_5y", None)),
            "cagr_3y_pct": _decimal(getattr(trailing_3y, "cagr_pct", None) or getattr(meta, "returns_3y", None)),
            "rolling_return_3y_pct": _decimal(getattr(rolling_3y, "mean_pct", None)),
            "volatility_3y_pct": volatility,
            "data_as_of": data_as_of,
            "nav_as_of": latest_nav_date,
            "analytics_as_of": max([d for d in analytics_dates if d], default=None),
            "metadata_as_of": getattr(meta, "last_fetched", None),
            "source_notes": "Scheme + SchemeMeta + latest analytics tables",
        },
    )
    return snapshot


def classify_scheme(category: str, scheme_name: str) -> tuple[str, str]:
    text = f"{category} {scheme_name}".lower()
    for label, patterns, group in SUB_CATEGORY_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return group, label
    if "solution" in text:
        return "Solution Oriented", "Solution Oriented"
    for group in CATEGORY_GROUPS:
        if group.lower() in text:
            return group, _clean_sub_category(category, group) or group
    inferred = infer_category(scheme_name)
    if inferred:
        return classify_scheme(inferred, "")
    return "Other", _clean_sub_category(category, "Other") or "Other"


def classify_benchmark(benchmark_name: str) -> str:
    value = (benchmark_name or "").lower()
    if not value:
        return "Misc"
    if any(term in value for term in ("gold", "silver", "commodity", "commodities")):
        return "Commodity"
    if any(term in value for term in ("nasdaq", "s&p", "msci", "world", "global", "international")):
        return "International"
    if any(term in value for term in ("quality", "momentum", "value", "low volatility", "alpha", "equal weight")):
        return "Strategy based"
    if any(term in value for term in ("bank", "it", "auto", "pharma", "healthcare", "metal", "realty", "energy", "defence", "consumption", "manufacturing", "infra")):
        return "Sectoral"
    if any(term in value for term in ("thematic", "tourism", "digital", "internet", "ev", "new age")):
        return "Thematic"
    if any(term in value for term in ("nifty", "sensex", "bse", "crisil", "g-sec", "sdl", "liquid", "debt")):
        return "Broad based"
    return "Misc"


def benchmark_options() -> list[str]:
    return sorted({definition.name for definition in BENCHMARK_DEFINITIONS.values()})


def clean_fund_house(value: str) -> str:
    return re.sub(r"\s+Mutual\s+Fund\s*$", "", value or "", flags=re.I).strip()


def infer_plan_type(scheme_name: str, is_direct_scheme: bool) -> str:
    if is_etf(scheme_name):
        return "ETF"
    return "Direct" if is_direct_scheme else "Regular"


def infer_income_type(scheme_name: str, plan: str) -> str:
    name = (scheme_name or "").lower()
    if "income" in name:
        return "Income"
    if "idcw" in name or "dividend" in name or plan == "IDCW":
        return "IDCW"
    return "Growth"


def is_etf(scheme_name: str) -> bool:
    return bool(re.search(r"\betf\b|exchange traded", scheme_name or "", flags=re.I))


def risk_label(volatility: Decimal | None) -> str:
    if volatility is None:
        return ""
    if volatility < Decimal("8"):
        return "Low"
    if volatility < Decimal("15"):
        return "Moderate"
    if volatility < Decimal("25"):
        return "High"
    return "Very High"


def _latest_rows_by_key(rows, key: str) -> dict[str, object]:
    result = {}
    for row in rows:
        value = getattr(row, key)
        if value not in result:
            result[value] = row
    return result


def _category_text(scheme, meta) -> str:
    return (
        getattr(meta, "ms_category", "")
        or scheme.scheme_category
        or infer_category(scheme.scheme_name)
        or ""
    )


def _clean_sub_category(category: str, group: str) -> str:
    value = (category or "").strip()
    value = re.sub(r"\s+Scheme\s*$", "", value, flags=re.I)
    value = re.sub(rf"^{re.escape(group)}\s*[-:]\s*", "", value, flags=re.I)
    return value.strip()


def _fund_age_years(start: date | None, end: date | None) -> Decimal | None:
    if not start or not end or end <= start:
        return None
    return Decimal(str(round((end - start).days / 365.25, 1)))


def _decimal(value) -> Decimal | None:
    if value in ("", None):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
