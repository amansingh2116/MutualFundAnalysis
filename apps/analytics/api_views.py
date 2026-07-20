"""
apps/analytics/api_views.py — JSON API endpoints for chart data
"""
import json
import logging
from datetime import date, timedelta

import pandas as pd
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from apps.funds.models import NAVHistory, Scheme
from apps.analytics.engine import simulate_sip, simulate_lumpsum, simulate_swp

logger = logging.getLogger('mfanalysis')


def get_scheme_or_404(amfi_code):
    return get_object_or_404(Scheme, amfi_code=amfi_code)


def _rebased_benchmark_rows(nav_rows, benchmark_series: pd.Series) -> list[dict]:
    if not nav_rows or benchmark_series is None or benchmark_series.empty:
        return []
    try:
        first_nav = float(nav_rows[0]['nav'])
        start = pd.Timestamp(nav_rows[0]['date'])
        end = pd.Timestamp(nav_rows[-1]['date'])
        bm = benchmark_series[(benchmark_series.index >= start) & (benchmark_series.index <= end)].dropna()
        if len(bm) < 2:
            return []
        base = float(bm.iloc[0])
        if not base:
            return []
        rebased = bm / base * first_nav
        return [
            {
                'date': idx.date().isoformat(),
                'value': round(float(value), 4),
                'raw_value': round(float(bm.loc[idx]), 4),
            }
            for idx, value in rebased.items()
        ]
    except Exception as exc:
        logger.info("Could not rebase benchmark chart rows: %s", exc)
        return []


@require_GET
def nav_chart_api(request, amfi_code):
    """Returns NAV history as [{date, nav}, ...] with optional ?days= filter."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    days = request.GET.get('days')
    data = snapshot.nav_rows
    if days:
        try:
            cutoff = date.today() - timedelta(days=int(days))
            data = [r for r in data if date.fromisoformat(r['date']) >= cutoff]
        except ValueError:
            pass
    benchmark_data = _rebased_benchmark_rows(data, snapshot.benchmark_series)
    return JsonResponse({
        'data': data,
        'benchmark_data': benchmark_data,
        'scheme_name': scheme.scheme_name,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })


@require_GET
def returns_api(request, amfi_code):
    """Trailing returns for returns bar chart."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    trailing = [
        {
            'period': r.period,
            'cagr_pct': float(r.cagr_pct) if r.cagr_pct is not None else None,
            'bm_cagr': float(r.bm_cagr) if r.bm_cagr is not None else None,
            'excess': float(r.excess) if r.excess is not None else None,
            'years': float(r.years) if r.years is not None else None,
        }
        for r in snapshot.trailing_returns
    ]
    return JsonResponse({
        'trailing': trailing,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })


@require_GET
def calendar_api(request, amfi_code):
    """Calendar year returns."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    calendar = [
        {
            'year': r.year,
            'return_pct': float(r.return_pct) if r.return_pct is not None else None,
            'bm_return': float(r.bm_return) if r.bm_return is not None else None,
            'outperformed': bool(r.outperformed) if r.outperformed is not None else None,
        }
        for r in sorted(snapshot.calendar_returns, key=lambda row: row.year)
    ]
    return JsonResponse({
        'calendar': calendar,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })


@require_GET
def drawdown_api(request, amfi_code):
    """Compute and return drawdown series from stored NAV."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    data = [{'date': r.date, 'drawdown': round(r.drawdown, 4)} for r in snapshot.drawdown]
    return JsonResponse({'data': data})


@require_GET
def risk_api(request, amfi_code):
    """Risk metrics for the fund."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    result = {}
    for period in ['3Y', '5Y']:
        rm = getattr(snapshot, f"risk_{period.lower()}", None)
        if rm:
            result[period] = {
                'std_dev_ann': float(rm.std_dev_ann) if rm.std_dev_ann is not None else None,
                'sharpe_ratio': float(rm.sharpe_ratio) if rm.sharpe_ratio is not None else None,
                'sortino_ratio': float(rm.sortino_ratio) if rm.sortino_ratio is not None else None,
                'max_drawdown': float(rm.max_drawdown) if rm.max_drawdown is not None else None,
                'beta': float(rm.beta) if rm.beta is not None else None,
                'alpha_ann': float(rm.alpha_ann) if rm.alpha_ann is not None else None,
                'r_squared': float(rm.r_squared) if rm.r_squared is not None else None,
                'tracking_error': float(rm.tracking_error) if rm.tracking_error is not None else None,
                'info_ratio': float(rm.info_ratio) if rm.info_ratio is not None else None,
                'upside_capture': float(rm.upside_capture) if rm.upside_capture is not None else None,
                'downside_capture': float(rm.downside_capture) if rm.downside_capture is not None else None,
                'rf_rate_pct': float(rm.rf_rate_pct) if rm.rf_rate_pct is not None else None,
                'as_of': rm.as_of.isoformat() if getattr(rm.as_of, 'isoformat', None) else rm.as_of,
            }
    payload = dict(result)
    payload.update({
        'risk': result,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })
    return JsonResponse(payload)


@require_GET
def holdings_api(request, amfi_code):
    """Top holdings as JSON — uses lightweight snapshot that skips benchmark fetch."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_portfolio_snapshot

    snapshot = get_portfolio_snapshot(scheme)
    holdings = [
        {
            'security_name': h.security_name,
            'sector': h.sector,
            'weight_pct': float(h.weight_pct) if h.weight_pct is not None else None,
            'isin': h.isin,
            'forward_pe': float(h.forward_pe) if h.forward_pe is not None else None,
            'holding_type': h.holding_type,
        }
        for h in snapshot.top_holdings
    ]
    return JsonResponse({'holdings': holdings, 'as_of': snapshot.holdings_month.isoformat() if snapshot.holdings_month else None})


@require_GET
def sector_api(request, amfi_code):
    """Sector allocation as JSON for Plotly donut — uses lightweight snapshot that skips benchmark fetch."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_portfolio_snapshot

    snapshot = get_portfolio_snapshot(scheme)
    sectors = [{'sector': s.sector, 'weight_pct': float(s.weight_pct) if s.weight_pct else 0} for s in snapshot.sector_alloc]
    return JsonResponse({'sectors': sectors, 'as_of': snapshot.holdings_month.isoformat() if snapshot.holdings_month else None})


@require_http_methods(["POST"])
def sip_simulate_api(request, amfi_code):
    """SIP simulation endpoint. POST {amount, years} → returns simulation results."""
    scheme = get_scheme_or_404(amfi_code)
    try:
        body = json.loads(request.body)
        amount = float(body.get('amount', 10000))
        years = int(body.get('years', 10))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid input parameters.'}, status=400)

    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    nav_series = snapshot.nav_series
    if nav_series.empty:
        return JsonResponse({'error': 'No NAV data available from mfapi.in right now.'})

    # Trim to requested years
    from_date = nav_series.index[-1] - pd.DateOffset(years=years)
    nav_series = nav_series[nav_series.index >= from_date]

    if len(nav_series) < 12:
        return JsonResponse({'error': f'Insufficient NAV history for {years}-year simulation.'})

    result = simulate_sip(nav_series, monthly_amount=amount)
    if result is None:
        return JsonResponse({'error': 'SIP simulation returned no result.'})

    # Convert numpy types for JSON serialization
    return JsonResponse({k: float(v) if hasattr(v, '__float__') else v for k, v in result.items()})


@require_http_methods(["POST"])
def lumpsum_simulate_api(request, amfi_code):
    """Lumpsum simulation endpoint. POST {amount, years} → returns simulation results."""
    scheme = get_scheme_or_404(amfi_code)
    try:
        body = json.loads(request.body)
        amount = float(body.get('amount', 100000))
        years = float(body.get('years', 10))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid input parameters.'}, status=400)

    from apps.funds.runtime import get_runtime_snapshot
    snapshot = get_runtime_snapshot(scheme)
    nav_series = snapshot.nav_series
    if nav_series.empty:
        return JsonResponse({'error': 'No NAV data available from mfapi.in right now.'})

    # Trim to requested years
    from_date = nav_series.index[-1] - pd.DateOffset(days=int(years * 365.25))
    nav_series = nav_series[nav_series.index >= from_date]

    if len(nav_series) < 2:
        return JsonResponse({'error': f'Insufficient NAV history for {years}-year simulation.'})

    result = simulate_lumpsum(nav_series, principal=amount)
    if result is None:
        return JsonResponse({'error': 'Lumpsum simulation returned no result.'})

    return JsonResponse({k: float(v) if hasattr(v, '__float__') else v for k, v in result.items()})


@require_http_methods(["POST"])
def swp_simulate_api(request, amfi_code):
    """SWP simulation endpoint. POST {corpus, withdrawal, years} → returns simulation results."""
    scheme = get_scheme_or_404(amfi_code)
    try:
        body = json.loads(request.body)
        corpus = float(body.get('corpus', 1000000))
        withdrawal = float(body.get('withdrawal', 10000))
        years = float(body.get('years', 10))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid input parameters.'}, status=400)

    from apps.funds.runtime import get_runtime_snapshot
    snapshot = get_runtime_snapshot(scheme)
    nav_series = snapshot.nav_series
    if nav_series.empty:
        return JsonResponse({'error': 'No NAV data available from mfapi.in right now.'})

    # Trim to requested years
    from_date = nav_series.index[-1] - pd.DateOffset(days=int(years * 365.25))
    nav_series = nav_series[nav_series.index >= from_date]

    if len(nav_series) < 2:
        return JsonResponse({'error': f'Insufficient NAV history for {years}-year simulation.'})

    result = simulate_swp(nav_series, corpus=corpus, monthly_withdrawal=withdrawal)
    if result is None:
        return JsonResponse({'error': 'SWP simulation returned no result.'})

    # Ensure nested objects like 'history' lists are clean
    clean_result = {}
    for k, v in result.items():
        if isinstance(v, list):
            clean_result[k] = v
        else:
            clean_result[k] = float(v) if hasattr(v, '__float__') else v

    return JsonResponse(clean_result)


@require_GET
def rolling_timeseries_api(request, amfi_code):
    """Rolling return time-series API.

    Query params:
      window  — rolling window in days (default 365 = 1Y)
      start   — start date YYYY-MM-DD (optional, defaults to inception)
      end     — end date YYYY-MM-DD (optional, defaults to latest NAV)
      benchmark — optional override for benchmark data

    Returns:
      inception_date, latest_date, benchmark_name,
      series: [{date, fund, bm}, ...],
      stats: {avg, median, min, max, negative_pct, vol, dist_buckets}
    """
    import numpy as np
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot, fetch_benchmark_result

    snapshot = get_runtime_snapshot(scheme)
    nav = snapshot.nav_series

    # Check for benchmark override via ?benchmark= or ?custom_weights= query param
    bm_override = request.GET.get('benchmark', '').strip()
    custom_weights_str = request.GET.get('custom_weights', '').strip()

    if custom_weights_str:
        try:
            custom_weights = json.loads(custom_weights_str)
            total_w = sum(custom_weights.values())
            if total_w > 0:
                normalized_weights = {k: v / total_w for k, v in custom_weights.items()}
                
                from apps.funds.runtime import fetch_db_benchmark_series
                series_dict = {}
                for idx_name, w in normalized_weights.items():
                    s = fetch_db_benchmark_series(idx_name, None)
                    if s is not None and not s.empty:
                        series_dict[idx_name] = s
                
                if series_dict:
                    df_bm = pd.DataFrame(series_dict)
                    df_bm.ffill(inplace=True)
                    df_bm.dropna(inplace=True)
                    
                    if not df_bm.empty:
                        df_returns = df_bm.pct_change().fillna(0)
                        weighted_returns = pd.Series(0.0, index=df_returns.index)
                        for idx_name, w in normalized_weights.items():
                            if idx_name in df_returns:
                                weighted_returns += df_returns[idx_name] * w
                        
                        synthetic_nav = 100 * (1 + weighted_returns).cumprod()
                        bm = synthetic_nav
                        bm_name = "Custom Blended Benchmark"
                        
                        note_parts = [f"{k} ({v*100:.1f}%)" for k, v in normalized_weights.items() if k in series_dict]
                        bm_note = "Weights: " + ", ".join(note_parts)
                        bm_fallback = False
                    else:
                        raise ValueError("No overlapping data for custom benchmark constituents.")
                else:
                    raise ValueError("Could not fetch data for any custom benchmark constituents.")
            else:
                raise ValueError("Total weight must be greater than 0.")
        except Exception as exc:
            logger.info("Custom blended benchmark failed: %s", exc)
            bm = snapshot.benchmark_series
            bm_name = snapshot.benchmark_display_name
            bm_note = f"Custom blended benchmark failed; using fund's default. ({exc})"
            bm_fallback = True
    elif bm_override:
        try:
            bm_result = fetch_benchmark_result(bm_override, nav if not nav.empty else pd.Series(dtype=float))
            if bm_result.series is not None and not bm_result.series.empty:
                bm = bm_result.series
                bm_name = bm_result.display_name or bm_override
                bm_note = bm_result.note or ''
                bm_fallback = bm_result.fallback_used
            else:
                bm = snapshot.benchmark_series
                bm_name = snapshot.benchmark_display_name
                bm_note = f"Could not fetch '{bm_override}'; using fund's default benchmark."
                bm_fallback = True
        except Exception as exc:
            logger.info("Custom benchmark fetch failed for %s: %s", bm_override, exc)
            bm = snapshot.benchmark_series
            bm_name = snapshot.benchmark_display_name
            bm_note = f"Custom benchmark '{bm_override}' unavailable; using fund's default."
            bm_fallback = True
    else:
        bm = snapshot.benchmark_series
        bm_name = snapshot.benchmark_display_name
        bm_note = getattr(snapshot, 'benchmark_note', '') or ''
        bm_fallback = getattr(snapshot, 'benchmark_fallback_used', False) or False

    # ── NIFTY 50 ultimate fallback ─────────────────────────────────────────────
    # If bm is empty OR has fewer rows than we need for the rolling window,
    # try fetching NIFTY 50 from DB without a start-date filter to get all
    # available data (our DB has 2020–2026). We always show whatever we have.
    NIFTY50_FALLBACK = 'NIFTY 50'
    if not bm_override and not custom_weights_str:
        _need_bm_fallback = (bm is None or bm.empty)
        if _need_bm_fallback:
            try:
                from apps.funds.runtime import fetch_db_benchmark_series
                n50_series = fetch_db_benchmark_series(NIFTY50_FALLBACK, None)  # no date filter
                if n50_series is not None and not n50_series.empty:
                    original_bm_name = snapshot.benchmark_name or 'fund benchmark'
                    bm = n50_series
                    bm_name = f'NIFTY 50 (proxy for {original_bm_name})' if original_bm_name != NIFTY50_FALLBACK else NIFTY50_FALLBACK
                    fallback_note = (
                        f"Primary benchmark '{original_bm_name}' is unavailable; "
                        f"NIFTY 50 is shown as a proxy. Returns may not be directly comparable."
                    )
                    bm_note = (fallback_note + ' ' + bm_note).strip() if bm_note else fallback_note
                    bm_fallback = True
            except Exception as exc:
                logger.info("NIFTY 50 fallback fetch failed for %s: %s", amfi_code, exc)
        elif bm_name and bm_name.strip().upper() == NIFTY50_FALLBACK:
            # We have NIFTY 50 from snapshot but it may be date-filtered — refresh without filter
            try:
                from apps.funds.runtime import fetch_db_benchmark_series
                n50_full = fetch_db_benchmark_series(NIFTY50_FALLBACK, None)  # no date filter
                if n50_full is not None and len(n50_full) > len(bm):
                    bm = n50_full  # use the fuller series
            except Exception:
                pass

    if nav.empty:
        return JsonResponse({'error': 'No NAV data available.'})

    # Parse params
    try:
        window_days = int(request.GET.get('window', 365))
    except ValueError:
        window_days = 365

    inception_date = nav.index[0].date().isoformat()
    latest_date = nav.index[-1].date().isoformat()

    try:
        start = pd.Timestamp(request.GET.get('start') or inception_date)
    except Exception:
        start = nav.index[0]
    try:
        end = pd.Timestamp(request.GET.get('end') or latest_date)
    except Exception:
        end = nav.index[-1]

    # Clamp to available NAV range
    start = max(start, nav.index[0])
    end = min(end, nav.index[-1])

    # Resample to business days
    nav_b = nav.resample('B').ffill().dropna()
    bm_b = bm.resample('B').ffill().dropna() if bm is not None and not bm.empty else pd.Series(dtype=float)

    # Compute rolling returns: CAGR over window_days ending at each date
    years = window_days / 252
    rolling_fund = (nav_b / nav_b.shift(window_days)) ** (1 / years) - 1
    rolling_fund = rolling_fund.dropna() * 100

    rolling_bm = pd.Series(dtype=float)
    if not bm_b.empty and len(bm_b) > window_days:
        rolling_bm = (bm_b / bm_b.shift(window_days)) ** (1 / years) - 1
        rolling_bm = rolling_bm.dropna() * 100

    # Filter to requested date range (end-date of each window)
    mask = (rolling_fund.index >= start) & (rolling_fund.index <= end)
    rolling_fund = rolling_fund[mask]

    # Align benchmark to fund's rolling return dates via reindex+ffill.
    # This handles any date misalignment between fund NAV calendar and benchmark calendar.
    if not rolling_bm.empty:
        rolling_bm_aligned = rolling_bm.reindex(
            rolling_bm.index.union(rolling_fund.index)
        ).ffill().reindex(rolling_fund.index)
    else:
        rolling_bm_aligned = pd.Series(dtype=float, index=rolling_fund.index)

    # Build series
    series = []
    for dt, val in rolling_fund.items():
        bm_val = None
        if not rolling_bm_aligned.empty:
            bv = rolling_bm_aligned.get(dt)
            bm_val = round(float(bv), 4) if bv is not None and not pd.isna(bv) else None
        series.append({
            'date': dt.date().isoformat(),
            'fund': round(float(val), 4),
            'bm': bm_val,
        })

    # Compute stats
    vals = [p['fund'] for p in series]
    bm_vals = [p['bm'] for p in series if p['bm'] is not None]
    def pct_in(arr, lo, hi):
        if not arr: return 0.0
        return round(100 * sum(1 for v in arr if lo <= v < hi) / len(arr), 2)

    stats = {}
    if vals:
        stats = {
            'avg': round(float(np.mean(vals)), 2),
            'median': round(float(np.median(vals)), 2),
            'min': round(float(np.min(vals)), 2),
            'max': round(float(np.max(vals)), 2),
            'vol': round(float(np.std(vals)), 2),
            'negative_pct': round(100 * sum(1 for v in vals if v < 0) / len(vals), 2),
            'dist': {
                'neg': pct_in(vals, -999, 0),
                '0_8': pct_in(vals, 0, 8),
                '8_10': pct_in(vals, 8, 10),
                '10_12': pct_in(vals, 10, 12),
                '12_15': pct_in(vals, 12, 15),
                '15_20': pct_in(vals, 15, 20),
                'gt20': pct_in(vals, 20, 9999),
            },
            'count': len(vals),
        }
    bm_stats = {}
    if bm_vals:
        bm_stats = {
            'avg': round(float(np.mean(bm_vals)), 2),
            'median': round(float(np.median(bm_vals)), 2),
            'min': round(float(np.min(bm_vals)), 2),
            'max': round(float(np.max(bm_vals)), 2),
            'vol': round(float(np.std(bm_vals)), 2),
            'negative_pct': round(100 * sum(1 for v in bm_vals if v < 0) / len(bm_vals), 2),
            'dist': {
                'neg': pct_in(bm_vals, -999, 0),
                '0_8': pct_in(bm_vals, 0, 8),
                '8_10': pct_in(bm_vals, 8, 10),
                '10_12': pct_in(bm_vals, 10, 12),
                '12_15': pct_in(bm_vals, 12, 15),
                '15_20': pct_in(bm_vals, 15, 20),
                'gt20': pct_in(bm_vals, 20, 9999),
            },
            'count': len(bm_vals),
        }

    return JsonResponse({
        'inception_date': inception_date,
        'latest_date': latest_date,
        'scheme_name': scheme.scheme_name,
        'benchmark_name': bm_name,
        'benchmark_note': bm_note,
        'benchmark_fallback_used': bm_fallback,
        'window_days': window_days,
        'series': series,
        'stats': stats,
        'bm_stats': bm_stats,
    })


@require_GET
def analysis_api(request, amfi_code):
    """
    Fund analysis scorecard API.

    Returns a full multi-factor scorecard for the fund:
      - 6-pillar scores (Performance, Risk, Cost, Composition, Debt, Manager) and Red Flags
      - Overall composite score
      - Confidence level (Rated / Provisional / Unrated)
      - Category rank
      - Interpretive text per pillar
      - Fallback notes where data is missing
    """
    from django.core.cache import cache as django_cache

    scheme = get_scheme_or_404(amfi_code)
    cache_key = f"fund:analysis:v1:{amfi_code}"
    cached = django_cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    try:
        from apps.funds.runtime import get_runtime_snapshot
        from apps.analytics.scorer import score_fund, compute_category_rank

        snapshot = get_runtime_snapshot(scheme)
        result = score_fund(snapshot)

        # Compute category rank separately (DB-aware)
        rank_info = compute_category_rank(scheme, result.final_score)

        def _pillar_json(p: dict) -> dict:
            """Serialize a pillar result dict for JSON."""
            return {
                "score":          p.get("score"),
                "status":         p.get("status"),
                "interpretation": p.get("interpretation"),
                "missing":        p.get("missing"),
                "details":        p.get("details", {}),
            }

        payload = {
            "amfi_code":          amfi_code,
            "scheme_name":        scheme.scheme_name,
            "category":           scheme.scheme_category,
            "final_score":        result.final_score,
            "confidence":         result.confidence,
            "overall_badge":      result.overall_badge,
            "overall_interpretation": result.overall_interpretation,
            "model_version":      result.model_version,
            "nav_days":           result.nav_days,
            "missing_pillars":    result.missing_pillars,
            "provisional_pillars": result.provisional_pillars,
            "performance":        _pillar_json(result.performance),
            "risk":               _pillar_json(result.risk),
            "cost":               _pillar_json(result.cost),
            "composition":        _pillar_json(result.composition),
            "manager":            _pillar_json(result.manager),
            "debt":               _pillar_json(result.debt),
            "red_flags": {
                "flags":         result.red_flags["flags"],
                "total_penalty": result.red_flags["total_penalty"],
            },
            "rank": {
                "rank":       rank_info["rank"],
                "total":      rank_info["total"],
                "percentile": rank_info["percentile"],
                "category":   scheme.scheme_category,
            },
            # Normalized portfolio numbers for display fix
            "normalized_top10_weight": result.normalized_top10_weight,
            "normalized_total_count":  result.normalized_total_count,
        }

        ttl = 60 * 60 * 6 if result.confidence == "RATED" else 60 * 30
        django_cache.set(cache_key, payload, ttl)
        return JsonResponse(payload)

    except Exception as exc:
        logger.error(f"[{amfi_code}] analysis_api failed: {exc}", exc_info=True)
        return JsonResponse({"error": str(exc), "amfi_code": amfi_code}, status=500)


@require_GET
def peer_comparison_api(request, amfi_code):
    """
    Peer comparison data for a fund.

    Returns the base fund plus up to N category peers (same SEBI category,
    same plan/direct flag, different AMC) with a unified data payload covering:
      - Ratios (PE, Std Dev, Sharpe, Sortino, Max Drawdown)
      - Returns (trailing + rolling stats)
      - Scheme information (expense ratio, AUM, SIP/Lumpsum limits, etc.)

    Query params:
      max   — number of peers to return (default 5, max 8)
    """
    import math
    from django.core.cache import cache as django_cache

    scheme = get_scheme_or_404(amfi_code)
    max_peers = min(int(request.GET.get('max', 5)), 8)
    cache_key = f"fund:peers:v3:{amfi_code}:{max_peers}"
    cached = django_cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    try:
        from apps.funds.peers import get_peer_matches
        from apps.funds.runtime import get_runtime_snapshot

        peer_matches = get_peer_matches(scheme, max_peers=max_peers)
        match_by_code = {match.scheme.amfi_code: match for match in peer_matches}
        funds_to_fetch = [scheme] + [match.scheme for match in peer_matches]

        funds_data = []
        for s in funds_to_fetch:
            try:
                snap = get_runtime_snapshot(s)
            except Exception as exc:
                logger.info("[peers] snapshot failed for %s: %s", s.amfi_code, exc)
                continue

            # ── Ratios ──────────────────────────────────────────────────────
            pe_ratios = [
                h.forward_pe for h in snap.top_holdings
                if getattr(h, 'forward_pe', None)
            ]
            avg_pe = round(sum(pe_ratios) / len(pe_ratios), 2) if pe_ratios else None

            risk3 = snap.risk_3y
            risk5 = snap.risk_5y

            def _f(obj, attr):
                v = getattr(obj, attr, None) if obj else None
                if v is None: return None
                fv = float(v)
                return None if math.isnan(fv) else round(fv, 2)

            # ── Returns ─────────────────────────────────────────────────────
            trailing = {
                r.period: round(float(r.cagr_pct), 2)
                for r in (snap.trailing_returns or [])
                if r.cagr_pct is not None
            }

            rolling_1y = snap.rolling_returns.get('1Y') if snap.rolling_returns else None
            rolling_3y = snap.rolling_returns.get('3Y') if snap.rolling_returns else None

            # ── Scheme info ─────────────────────────────────────────────────
            meta = snap.meta

            match = match_by_code.get(s.amfi_code)
            funds_data.append({
                'amfi_code':    s.amfi_code,
                'scheme_name':  s.scheme_name,
                'fund_house':   s.fund_house,
                'category':     getattr(snap, 'category', s.scheme_category) or s.scheme_category,
                'is_base':      s.amfi_code == amfi_code,
                'match_score':  match.score if match else None,
                'match_reason': match.match_reason if match else '',
                'match_group':  match.match_group if match else '',
                # Ratios
                'pe_ratio':          avg_pe,
                'std_dev_3y':        _f(risk3, 'std_dev_ann'),
                'sharpe_3y':         _f(risk3, 'sharpe_ratio'),
                'sortino_3y':        _f(risk3, 'sortino_ratio'),
                'max_drawdown_3y':   _f(risk3, 'max_drawdown'),
                'std_dev_5y':        _f(risk5, 'std_dev_ann'),
                'sharpe_5y':         _f(risk5, 'sharpe_ratio'),
                'sortino_5y':        _f(risk5, 'sortino_ratio'),
                'max_drawdown_5y':   _f(risk5, 'max_drawdown'),
                # Returns
                'trailing':          trailing,
                'rolling_1y_mean':   round(float(rolling_1y.mean_pct), 2) if rolling_1y else None,
                'rolling_1y_median': round(float(rolling_1y.median_pct), 2) if rolling_1y else None,
                'rolling_3y_mean':   round(float(rolling_3y.mean_pct), 2) if rolling_3y else None,
                'rolling_3y_median': round(float(rolling_3y.median_pct), 2) if rolling_3y else None,
                # CAGR since inception
                'cagr_inception':    trailing.get('SI'),
                # Scheme information
                'expense_ratio':   float(meta.expense_ratio) if meta.expense_ratio is not None else None,
                'aum':             float(meta.aum) if meta.aum else None,
                'lock_in_period':  getattr(meta, 'lock_in_label', None),
                'min_sip':         float(meta.sip_min) if meta.sip_min else None,
                'min_lumpsum':     float(meta.lump_min) if meta.lump_min else None,
                'inception_date':  meta.start_date.isoformat() if meta.start_date else None,
                'investment_objective': (getattr(meta, 'investment_objective', '') or '')[:300],
                'fund_manager':    getattr(meta, 'fund_manager', '') or '',
                'crisil_rating':   getattr(meta, 'crisil_rating', '') or '',
                'ms_rating':       getattr(meta, 'ms_rating', None),
                'sip_available':   getattr(meta, 'sip_available', True),
                'exit_load':       None,   # not reliably available from any runtime source
            })

        from apps.funds.runtime import _extract_category_from_name
        inferred_category = scheme.scheme_category or _extract_category_from_name(scheme.scheme_name)

        peer_codes = [f['amfi_code'] for f in funds_data if not f['is_base']]
        compare_url = (
            '/calculators/compare/?funds=' + ','.join([amfi_code] + peer_codes[:3])
            if peer_codes else ''
        )

        payload = {
            'base_amfi_code': amfi_code,
            'funds': funds_data,
            'peer_count': len(funds_data) - 1,
            'category': scheme.scheme_category or inferred_category,
            'inferred_category': inferred_category,
            'compare_url': compare_url,
        }
        ttl = 60 * 30 if funds_data else 60 * 5
        django_cache.set(cache_key, payload, ttl)
        return JsonResponse(payload)

    except Exception as exc:
        logger.error("[%s] peer_comparison_api failed: %s", amfi_code, exc, exc_info=True)
        return JsonResponse({'error': str(exc), 'amfi_code': amfi_code}, status=500)


@require_GET
def rolling_chart_api(request, amfi_code):
    """Rolling return distribution for chart rendering.

    Returns percentile boxes per window (fund + benchmark) so the frontend
    can draw a grouped box / bar chart without re-computing anything heavy.
    """
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    windows = []
    for key, r in (snapshot.rolling_returns or {}).items():
        windows.append({
            'window': r.window,
            'min': round(r.min_pct, 2),
            'max': round(r.max_pct, 2),
            'mean': round(r.mean_pct, 2),
            'median': round(r.median_pct, 2),
            'std': round(r.std_dev, 2),
            'win_rate_0': round(r.win_rate_0, 1),
            'win_rate_8': round(r.win_rate_8, 1),
            'win_rate_12': round(r.win_rate_12, 1),
            'bm_min': round(r.bm_min, 2) if r.bm_min is not None else None,
            'bm_max': round(r.bm_max, 2) if r.bm_max is not None else None,
            'bm_mean': round(r.bm_mean, 2) if r.bm_mean is not None else None,
            'bm_median': round(r.bm_median, 2) if r.bm_median is not None else None,
            'outperformance_rate': round(r.outperformance_rate, 1) if r.outperformance_rate is not None else None,
        })
    return JsonResponse({
        'windows': windows,
        'benchmark_name': snapshot.benchmark_display_name,
    })


@require_GET
def compare_summary_api(request, amfi_code):
    """
    Comprehensive fund summary for compare page.
    Returns all data needed for side-by-side comparison:
    overview, returns, risk, portfolio, calendar, rolling, quarterly, NAV history.
    Cached for 30 minutes.
    """
    import math
    from django.core.cache import cache as django_cache

    scheme = get_scheme_or_404(amfi_code)
    cache_key = f"fund:compare-summary:v2:{amfi_code}"
    cached = django_cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    try:
        from apps.funds.runtime import get_runtime_snapshot

        snap = get_runtime_snapshot(scheme)
        meta = snap.meta

        # ── Helper ───────────────────────────────────────────────────────────
        def _f(obj, attr, digits=2):
            v = getattr(obj, attr, None) if obj else None
            if v is None: return None
            fv = float(v)
            return None if math.isnan(fv) else round(fv, digits)

        def _s(obj, attr):
            v = getattr(obj, attr, None) if obj else None
            return str(v) if v is not None else None

        # ── Trailing returns ─────────────────────────────────────────────────
        trailing = {}
        for r in (snap.trailing_returns or []):
            if r.cagr_pct is not None:
                trailing[r.period] = {
                    'fund': round(float(r.cagr_pct), 2),
                    'bm': round(float(r.bm_cagr), 2) if r.bm_cagr is not None else None,
                    'excess': round(float(r.excess), 2) if r.excess is not None else None,
                }

        # ── Calendar returns ─────────────────────────────────────────────────
        calendar = [
            {
                'year': r.year,
                'fund': round(float(r.return_pct), 2) if r.return_pct is not None else None,
                'bm': round(float(r.bm_return), 2) if r.bm_return is not None else None,
                'outperformed': bool(r.outperformed) if r.outperformed is not None else None,
            }
            for r in sorted(snap.calendar_returns or [], key=lambda x: x.year)
        ]

        # ── Rolling return stats ─────────────────────────────────────────────
        rolling = {}
        for key, r in (snap.rolling_returns or {}).items():
            rolling[key] = {
                'min':         round(float(r.min_pct), 2) if r.min_pct is not None else None,
                'max':         round(float(r.max_pct), 2) if r.max_pct is not None else None,
                'mean':        round(float(r.mean_pct), 2) if r.mean_pct is not None else None,
                'median':      round(float(getattr(r, 'median_pct', r.mean_pct)), 2) if r.mean_pct is not None else None,
                'std':         round(float(r.std_dev), 2) if r.std_dev is not None else None,
                'win_rate_0':  round(float(r.win_rate_0), 1) if r.win_rate_0 is not None else None,
                'win_rate_12': round(float(r.win_rate_12), 1) if r.win_rate_12 is not None else None,
            }

        # ── Risk metrics ─────────────────────────────────────────────────────
        def _risk_dict(rm):
            if not rm:
                return None
            return {
                'std_dev':         _f(rm, 'std_dev_ann'),
                'sharpe':          _f(rm, 'sharpe_ratio'),
                'sortino':         _f(rm, 'sortino_ratio'),
                'max_drawdown':    _f(rm, 'max_drawdown'),
                'beta':            _f(rm, 'beta'),
                'alpha':           _f(rm, 'alpha_ann'),
                'r_squared':       _f(rm, 'r_squared'),
                'tracking_error':  _f(rm, 'tracking_error'),
                'info_ratio':      _f(rm, 'info_ratio'),
                'upside_capture':  _f(rm, 'upside_capture'),
                'downside_capture':_f(rm, 'downside_capture'),
            }

        # ── Quarterly performance ────────────────────────────────────────────
        quarterly_raw = snap.quarterly_performance or {}
        q_fund_up = quarterly_raw.get('upside', [])
        q_fund_down = quarterly_raw.get('downside', [])
        q_fund = q_fund_up + q_fund_down

        good_quarters = [q for q in q_fund if q.get('fund_return', 0) and q['fund_return'] > 0]
        bad_quarters  = [q for q in q_fund if q.get('fund_return', 0) and q['fund_return'] < 0]
        best_q  = max(q_fund, key=lambda x: x.get('fund_return', -999), default=None) if q_fund else None
        worst_q = min(q_fund, key=lambda x: x.get('fund_return', 999), default=None) if q_fund else None
        quarterly = {
            'positive_count': len(good_quarters),
            'negative_count': len(bad_quarters),
            'positive_pct': round(100 * len(good_quarters) / len(q_fund), 1) if q_fund else None,
            'best':  {'label': best_q.get('quarter'), 'return': round(best_q['fund_return'], 2)} if best_q else None,
            'worst': {'label': worst_q.get('quarter'), 'return': round(worst_q['fund_return'], 2)} if worst_q else None,
            'all':   [{'label': q.get('quarter'), 'return': round(q['fund_return'], 2)} for q in q_fund if 'fund_return' in q]
        }

        # ── Portfolio ────────────────────────────────────────────────────────
        top_holdings = [
            {
                'name':   h.security_name,
                'sector': h.sector or '',
                'weight': round(float(h.weight_pct), 2) if h.weight_pct is not None else None,
                'pe':     round(float(h.forward_pe), 1) if getattr(h, 'forward_pe', None) else None,
            }
            for h in (snap.top_holdings or [])[:10]
        ]
        sector_alloc = [
            {'sector': s.sector, 'weight': round(float(s.weight_pct), 2)}
            for s in (snap.sector_alloc or [])[:12]
        ]
        pe_ratios = [h.forward_pe for h in (snap.top_holdings or []) if getattr(h, 'forward_pe', None)]
        avg_pe = round(sum(pe_ratios) / len(pe_ratios), 1) if pe_ratios else None
        top10_weight = round(sum(h.get('weight', 0) or 0 for h in top_holdings[:10]), 2)

        # Asset Allocation
        asset_alloc = None
        if snap.asset_alloc:
            asset_alloc = {item.label.lower(): round(float(item.weight_pct), 1) for item in snap.asset_alloc}

        # Market cap from MarketCapAllocation DB
        mcap = None
        try:
            from apps.holdings.models import MarketCapAllocation
            mca = MarketCapAllocation.objects.filter(scheme=scheme).order_by('-as_of_month').first()
            if mca:
                mcap = {
                    'large': float(mca.large_pct) if mca.large_pct else None,
                    'mid':   float(mca.mid_pct)   if mca.mid_pct   else None,
                    'small': float(mca.small_pct) if mca.small_pct else None,
                    'other': float(mca.other_pct) if mca.other_pct else None,
                }
        except Exception:
            pass

        # ── NAV history (thin — last 1095 days = 3Y for chart) ────────────────
        nav_rows = snap.nav_rows or []
        cutoff = date.today() - timedelta(days=1095)
        nav_history = [
            r for r in nav_rows
            if date.fromisoformat(r['date']) >= cutoff
        ]
        # Downsample to weekly to keep payload small
        if len(nav_history) > 200:
            step = max(1, len(nav_history) // 200)
            nav_history = nav_history[::step]

        # ── Category detection for debt metrics note ─────────────────────────
        cat = (snap.category or scheme.scheme_category or '').lower()
        is_debt_or_hybrid = any(k in cat for k in ['debt', 'bond', 'hybrid', 'credit', 'liquid', 'overnight', 'ultra short', 'short dur', 'medium dur', 'long dur', 'gilt', 'floating'])

        # ── Lock-in label ────────────────────────────────────────────────────
        lock_in_days = int(getattr(meta, 'lock_in_period', None) or 0)
        if lock_in_days >= 1095:
            lock_in_label = f'{lock_in_days // 365} Years (ELSS)'
        elif lock_in_days > 0:
            lock_in_label = f'{lock_in_days} Days'
        else:
            lock_in_label = 'None'

        # ── Category average lookup ──────────────────────────────────────────
        category_avg = None
        try:
            from apps.funds.models import CategorySnapshot, FundScreenerSnapshot
            sub_cat = (
                FundScreenerSnapshot.objects
                .filter(scheme=scheme)
                .values_list('scheme_sub_category', flat=True)
                .first() or ''
            )
            if sub_cat:
                cat_snap = CategorySnapshot.objects.filter(
                    scheme_sub_category__iexact=sub_cat
                ).first()
                if cat_snap:
                    category_avg = {
                        'sub_category': sub_cat,
                        'fund_count': cat_snap.fund_count,
                        'trailing': {
                            '1Y': float(cat_snap.avg_return_1y) if cat_snap.avg_return_1y else None,
                            '3Y': float(cat_snap.avg_return_3y) if cat_snap.avg_return_3y else None,
                            '5Y': float(cat_snap.avg_return_5y) if cat_snap.avg_return_5y else None,
                        },
                        'calendar': cat_snap.calendar_returns_json or {},
                        'rolling': cat_snap.rolling_returns_json or {},
                        'risk': {
                            'std_dev':      float(cat_snap.avg_volatility) if cat_snap.avg_volatility else None,
                            'sharpe':       float(cat_snap.avg_sharpe) if cat_snap.avg_sharpe else None,
                            'sortino':      float(cat_snap.avg_sortino) if cat_snap.avg_sortino else None,
                            'max_drawdown': float(cat_snap.avg_max_drawdown) if cat_snap.avg_max_drawdown else None,
                            'std_dev_5y':   float(cat_snap.avg_volatility_5y) if cat_snap.avg_volatility_5y else None,
                            'sharpe_5y':    float(cat_snap.avg_sharpe_5y) if cat_snap.avg_sharpe_5y else None,
                            'sortino_5y':   float(cat_snap.avg_sortino_5y) if cat_snap.avg_sortino_5y else None,
                            'max_drawdown_5y': float(cat_snap.avg_max_drawdown_5y) if cat_snap.avg_max_drawdown_5y else None,
                        },
                    }
        except Exception as _exc:
            logger.warning('[compare_summary_api] category_avg lookup failed: %s', _exc)

        payload = {
            'amfi_code':    scheme.amfi_code,
            'scheme_name':  scheme.scheme_name,
            'fund_house':   scheme.fund_house,
            'category':     snap.category or scheme.scheme_category,
            'plan':         'Direct' if scheme.is_direct else 'Regular',
            'benchmark_name': snap.benchmark_display_name,

            # Overview
            'inception_date':       _s(meta, 'start_date'),
            'aum':                  _f(meta, 'aum', 0),
            'expense_ratio':        _f(meta, 'expense_ratio'),
            'fund_manager':         _s(meta, 'fund_manager') or '',
            'investment_objective': (_s(meta, 'investment_objective') or '')[:400],
            'crisil_rating':        _s(meta, 'crisil_rating') or '',
            'ms_rating':            getattr(meta, 'ms_rating', None),
            'lock_in_days':         lock_in_days,
            'lock_in_label':        lock_in_label,
            'tax_period_days':      int(getattr(meta, 'tax_period', None) or 0),
            'min_sip':              _f(meta, 'sip_min', 0),
            'min_lumpsum':          _f(meta, 'lump_min', 0),
            'portfolio_turnover':   _f(meta, 'portfolio_turnover'),
            'is_debt_or_hybrid':    is_debt_or_hybrid,

            # Returns
            'trailing':  trailing,
            'calendar':  calendar,
            'rolling':   rolling,

            # Risk
            'risk_3y': _risk_dict(snap.risk_3y),
            'risk_5y': _risk_dict(snap.risk_5y),

            # Quarterly
            'quarterly': quarterly,

            # Portfolio
            'top_holdings':     top_holdings,
            'sector_alloc':     sector_alloc,
            'asset_alloc':      asset_alloc,
            'mcap':             mcap,
            'pe_ratio':         avg_pe,
            'top10_weight':     top10_weight,
            'holdings_count':   snap.total_holdings_count,
            'holdings_as_of':   snap.holdings_month.isoformat() if snap.holdings_month else None,

            # Chart data
            'nav_history': nav_history,
        }

        payload['category_avg'] = category_avg

        django_cache.set(cache_key, payload, 60 * 30)
        return JsonResponse(payload)

    except Exception as exc:
        logger.error("[%s] compare_summary_api failed: %s", amfi_code, exc, exc_info=True)
        return JsonResponse({'error': str(exc), 'amfi_code': amfi_code}, status=500)


@require_GET
def fund_category_avg_api(request, amfi_code):
    """
    Lightweight endpoint: return category average data for a fund's sub-category.
    Used by Rolling Return Calculator and any future consumers.
    GET /api/funds/<amfi_code>/category-avg/
    Response: {sub_category, fund_count, trailing, rolling, calendar, risk}
    """
    scheme = get_scheme_or_404(amfi_code)
    try:
        from apps.funds.models import CategorySnapshot, FundScreenerSnapshot
        sub_cat = (
            FundScreenerSnapshot.objects
            .filter(scheme=scheme)
            .values_list('scheme_sub_category', flat=True)
            .first() or ''
        )
        if not sub_cat:
            # Fallback to scheme_category
            sub_cat = scheme.scheme_category or ''
        if not sub_cat:
            return JsonResponse({'error': 'no category found'}, status=404)

        cat_snap = CategorySnapshot.objects.filter(
            scheme_sub_category__iexact=sub_cat
        ).first()
        if not cat_snap:
            return JsonResponse({'error': f'no CategorySnapshot for {sub_cat}'}, status=404)

        return JsonResponse({
            'sub_category': sub_cat,
            'fund_count': cat_snap.fund_count,
            'trailing': {
                '1Y': float(cat_snap.avg_return_1y) if cat_snap.avg_return_1y else None,
                '3Y': float(cat_snap.avg_return_3y) if cat_snap.avg_return_3y else None,
                '5Y': float(cat_snap.avg_return_5y) if cat_snap.avg_return_5y else None,
                'med_1y': float(cat_snap.median_return_1y) if cat_snap.median_return_1y else None,
                'med_3y': float(cat_snap.median_return_3y) if cat_snap.median_return_3y else None,
                'med_5y': float(cat_snap.median_return_5y) if cat_snap.median_return_5y else None,
            },
            'rolling': cat_snap.rolling_returns_json or {},
            'calendar': cat_snap.calendar_returns_json or {},
            'risk': {
                'std_dev':      float(cat_snap.avg_volatility) if cat_snap.avg_volatility else None,
                'sharpe':       float(cat_snap.avg_sharpe) if cat_snap.avg_sharpe else None,
                'sortino':      float(cat_snap.avg_sortino) if cat_snap.avg_sortino else None,
                'max_drawdown': float(cat_snap.avg_max_drawdown) if cat_snap.avg_max_drawdown else None,
                'std_dev_5y':   float(cat_snap.avg_volatility_5y) if cat_snap.avg_volatility_5y else None,
                'sharpe_5y':    float(cat_snap.avg_sharpe_5y) if cat_snap.avg_sharpe_5y else None,
                'sortino_5y':   float(cat_snap.avg_sortino_5y) if cat_snap.avg_sortino_5y else None,
                'max_drawdown_5y': float(cat_snap.avg_max_drawdown_5y) if cat_snap.avg_max_drawdown_5y else None,
            },
        })
    except Exception as exc:
        logger.error('[fund_category_avg_api] %s: %s', amfi_code, exc)
        return JsonResponse({'error': str(exc)}, status=500)
