"""HTML report generation for top screener funds."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.utils import timezone

from apps.funds.models import FundScreenerSnapshot, NAVHistory


@dataclass(frozen=True)
class ScreenerReportResult:
    output_dir: Path
    csv_path: Path
    report_paths: list[Path]


TOP_REPORT_SORTS = {
    "cagr_3y": "-cagr_3y_pct",
    "rolling_3y": "-rolling_return_3y_pct",
    "return_1y": "-returns_1y_pct",
    "aum": "-aum_cr",
}


def generate_top_screener_reports(*, top: int = 10, sort: str = "cagr_3y", output_dir: Path | None = None) -> ScreenerReportResult:
    """Export the top screener rows and one HTML report per selected fund."""
    output_dir = output_dir or default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    order_by = TOP_REPORT_SORTS.get(sort, "-cagr_3y_pct")
    metric_field = order_by.lstrip("-")
    qs = (
        FundScreenerSnapshot.objects.select_related("scheme")
        .exclude(**{f"{metric_field}__isnull": True})
        .order_by(order_by, "fund_name")[:top]
    )
    rows = list(qs)
    if not rows:
        rows = list(
            FundScreenerSnapshot.objects.select_related("scheme")
            .order_by("-updated_at", "fund_name")[:top]
        )

    csv_path = output_dir / f"{timezone.localdate().isoformat()}_top_{len(rows)}_mutual_funds.csv"
    _write_top_csv(rows, csv_path)

    report_paths = []
    for snapshot in rows:
        path = output_dir / f"{snapshot.scheme.amfi_code}_performance_report.html"
        _write_fund_report(snapshot, path)
        report_paths.append(path)

    return ScreenerReportResult(output_dir=output_dir, csv_path=csv_path, report_paths=report_paths)


def default_output_dir() -> Path:
    return Path(settings.MEDIA_ROOT) / "reports" / "fund_screener" / timezone.localdate().isoformat()


def _write_top_csv(rows: list[FundScreenerSnapshot], path: Path) -> None:
    columns = [
        "amfi_code", "fund_name", "fund_house", "category_group", "scheme_sub_category",
        "plan_type", "benchmark_name", "aum_cr", "expense_ratio", "fund_age_years",
        "returns_1y_pct", "cagr_3y_pct", "rolling_return_3y_pct", "volatility_3y_pct",
        "risk_label", "data_as_of",
    ]
    data = []
    for row in rows:
        data.append({
            "amfi_code": row.scheme.amfi_code,
            "fund_name": row.fund_name,
            "fund_house": row.fund_house,
            "category_group": row.category_group,
            "scheme_sub_category": row.scheme_sub_category,
            "plan_type": row.plan_type,
            "benchmark_name": row.benchmark_name,
            "aum_cr": row.aum_cr,
            "expense_ratio": row.expense_ratio,
            "fund_age_years": row.fund_age_years,
            "returns_1y_pct": row.returns_1y_pct,
            "cagr_3y_pct": row.cagr_3y_pct,
            "rolling_return_3y_pct": row.rolling_return_3y_pct,
            "volatility_3y_pct": row.volatility_3y_pct,
            "risk_label": row.risk_label,
            "data_as_of": row.data_as_of,
        })
    pd.DataFrame(data, columns=columns).to_csv(path, index=False)


def _write_fund_report(snapshot: FundScreenerSnapshot, path: Path) -> None:
    path.write_text(render_fund_report_html(snapshot), encoding="utf-8")


def render_fund_report_html(snapshot: FundScreenerSnapshot) -> str:
    """Render a standalone HTML performance report for one snapshot."""
    nav = _load_nav(snapshot)
    benchmark = _load_benchmark(snapshot, nav)
    metrics = _report_metrics(snapshot, nav, benchmark)
    chart_svg = _line_chart_svg(nav, benchmark)
    rows = "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in metrics
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(snapshot.fund_name)} Performance Report</title>
  <style>
    body {{ margin: 0; background: #0a0e1a; color: #e5e7eb; font-family: Inter, system-ui, sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px; }}
    header {{ border-bottom: 1px solid rgba(255,255,255,.12); padding-bottom: 20px; margin-bottom: 24px; }}
    h1 {{ font-size: 28px; line-height: 1.2; margin: 0 0 8px; }}
    .muted {{ color: #94a3b8; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 360px; gap: 24px; align-items: start; }}
    .panel {{ background: #141929; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid rgba(255,255,255,.08); padding: 10px 0; text-align: left; vertical-align: top; }}
    th {{ color: #94a3b8; font-weight: 600; width: 45%; }}
    td {{ color: #f8fafc; font-weight: 600; }}
    svg {{ width: 100%; height: auto; display: block; }}
    .legend {{ display: flex; gap: 16px; margin-top: 12px; color: #94a3b8; font-size: 12px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 6px; }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 18px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(snapshot.fund_name)}</h1>
      <div class="muted">{escape(snapshot.fund_house)} · {escape(snapshot.scheme_sub_category or snapshot.category_group)} · Data as of {escape(_fmt_date(snapshot.data_as_of))}</div>
    </header>
    <div class="grid">
      <section class="panel">
        <h2 style="margin:0 0 16px;font-size:16px">Growth of NAV</h2>
        {chart_svg}
        <div class="legend">
          <span><i class="dot" style="background:#38bdf8"></i>Fund NAV</span>
          <span><i class="dot" style="background:#fbbf24"></i>Benchmark</span>
        </div>
      </section>
      <aside class="panel">
        <h2 style="margin:0 0 10px;font-size:16px">Performance Summary</h2>
        <table>{rows}</table>
      </aside>
    </div>
    <p class="muted" style="margin-top:20px">Generated from MutualFundAnalysis screener snapshots and stored NAV history. This is research output, not financial advice.</p>
  </main>
</body>
</html>
"""


def _load_nav(snapshot: FundScreenerSnapshot) -> pd.Series:
    rows = NAVHistory.objects.filter(scheme=snapshot.scheme).order_by("date").values("date", "nav")
    series = pd.Series({pd.Timestamp(row["date"]): float(row["nav"]) for row in rows})
    if series.empty:
        return pd.Series(dtype=float)
    return series.sort_index()


def _load_benchmark(snapshot: FundScreenerSnapshot, nav: pd.Series) -> pd.Series:
    if nav.empty or not snapshot.benchmark_name:
        return pd.Series(dtype=float)
    try:
        from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV

        index = BenchmarkIndex.objects.filter(name__iexact=snapshot.benchmark_name).first()
        if not index:
            return pd.Series(dtype=float)
        rows = (
            BenchmarkNAV.objects.filter(index=index, date__gte=nav.index[0].date())
            .order_by("date")
            .values("date", "close")
        )
        series = pd.Series({pd.Timestamp(row["date"]): float(row["close"]) for row in rows})
        return series.sort_index() if not series.empty else pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)


def _report_metrics(snapshot: FundScreenerSnapshot, nav: pd.Series, benchmark: pd.Series) -> list[tuple[str, str]]:
    return [
        ("AUM", _money(snapshot.aum_cr, " Cr")),
        ("Expense Ratio", _pct(snapshot.expense_ratio)),
        ("Fund Age", f"{snapshot.fund_age_years} years" if snapshot.fund_age_years else "-"),
        ("1-Year Return", _pct(snapshot.returns_1y_pct)),
        ("3-Year CAGR", _pct(snapshot.cagr_3y_pct)),
        ("3-Year Rolling Return", _pct(snapshot.rolling_return_3y_pct)),
        ("3-Year Volatility", _pct(snapshot.volatility_3y_pct)),
        ("Max Drawdown", _pct(_max_drawdown(nav))),
        ("Benchmark", snapshot.benchmark_name or "-"),
        ("Benchmark Return", _pct(_period_return(benchmark))),
        ("Risk Label", snapshot.risk_label or "-"),
        ("Plan", snapshot.plan_type or "-"),
    ]


def _line_chart_svg(nav: pd.Series, benchmark: pd.Series) -> str:
    width, height = 720, 320
    plot = (40, 20, width - 24, height - 36)
    fund_series = _normalised_series(nav)
    benchmark_series = _normalised_series(benchmark)
    values = [
        value
        for series in (fund_series, benchmark_series)
        for value in series.tolist()
    ]
    min_val = min(values) if values else 0
    max_val = max(values) if values else 1
    if min_val == max_val:
        max_val = min_val + 1
    fund_points = _series_points(fund_series, plot, min_val, max_val)
    bm_points = _series_points(benchmark_series, plot, min_val, max_val)
    grid = "\n".join(
        f'<line x1="{plot[0]}" y1="{y}" x2="{plot[2]}" y2="{y}" stroke="rgba(255,255,255,.08)" />'
        for y in [40, 100, 160, 220, 280]
    )
    fund_polyline = _polyline(fund_points, "#38bdf8")
    bm_polyline = _polyline(bm_points, "#fbbf24") if bm_points else ""
    return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Fund and benchmark performance chart">{grid}{bm_polyline}{fund_polyline}</svg>'


def _normalised_series(series: pd.Series) -> pd.Series:
    if series.empty or len(series) < 2:
        return pd.Series(dtype=float)
    series = series.dropna()
    series = series[series > 0]
    if len(series) < 2:
        return pd.Series(dtype=float)
    if len(series) > 260:
        series = series.resample("W").last().dropna()
    return series / float(series.iloc[0]) * 100


def _series_points(
    series: pd.Series,
    plot: tuple[int, int, int, int],
    min_val: float,
    max_val: float,
) -> list[tuple[float, float]]:
    if series.empty:
        return []
    left, top, right, bottom = plot
    span_x = right - left
    span_y = bottom - top
    count = len(series) - 1
    points = []
    for index, value in enumerate(series):
        x = left + span_x * (index / count)
        y = bottom - span_y * ((float(value) - min_val) / (max_val - min_val))
        points.append((round(x, 2), round(y, 2)))
    return points


def _polyline(points: list[tuple[float, float]], color: str) -> str:
    if not points:
        return ""
    values = " ".join(f"{x},{y}" for x, y in points)
    return f'<polyline points="{values}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />'


def _max_drawdown(series: pd.Series):
    if series.empty:
        return None
    running = series.cummax()
    return ((series - running) / running * 100).min()


def _period_return(series: pd.Series):
    if series.empty or len(series) < 2 or series.iloc[0] <= 0:
        return None
    return (float(series.iloc[-1]) / float(series.iloc[0]) - 1) * 100


def _money(value, suffix: str = "") -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):,.0f}{suffix}"


def _pct(value) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.2f}%"


def _fmt_date(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else "-"
