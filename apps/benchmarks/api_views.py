"""apps/benchmarks/api_views.py -- Market strip + metric API endpoints"""
import json
import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from .metric_providers import (
    METRIC_CATALOGUE, FUND_METRIC_DEFS, BENCHMARK_METRIC_DEFS,
    get_all_metric_values, get_fund_metric, get_benchmark_metric, validate_fred_key
)
logger = logging.getLogger("mfanalysis")
DEFAULT_METRIC_KEYS = ["nifty50", "sensex", "midcap", "smallcap", "nifty200", "usdinr"]
ALL_METRICS = {k: v["label"] for k, v in METRIC_CATALOGUE.items()}
CATEGORY_ORDER = ["index", "sentiment", "technical", "valuation", "macro", "global"]
CATEGORY_LABELS = {
    "index":     "Indices",
    "sentiment": "Sentiment",
    "technical": "Technical",
    "valuation": "Valuation",
    "macro":     "Macro India",
    "global":    "Global",
    "fund":      "Fund",
}

def _user_entries(request):
    if not request.user.is_authenticated:
        return DEFAULT_METRIC_KEYS
    try:
        from .models import UserMarketStripProfile
        profile = UserMarketStripProfile.objects.filter(user=request.user).first()
        if profile and profile.metrics:
            valid = []
            for entry in profile.metrics:
                if isinstance(entry, str) and entry in ALL_METRICS:
                    valid.append(entry)
                elif isinstance(entry, dict) and entry.get("type") in ("fund", "benchmark"):
                    valid.append(entry)
            if valid:
                return valid
    except Exception as exc:
        logger.warning("_user_entries: %s", exc)
    return DEFAULT_METRIC_KEYS


def _enrich(data: dict) -> dict:
    """Add abs_change_pct so templates don't need |abs filter."""
    pct = data.get("change_pct")
    data["abs_change_pct"] = abs(pct) if pct is not None else None
    return data


@require_GET
def market_strip_partial(request):
    """GET /api/market/strip/ -- HTMX partial for the scrolling strip."""
    entries    = _user_entries(request)
    all_values = get_all_metric_values(user=request.user if request.user.is_authenticated else None)
    strip_items = []
    for entry in entries:
        if isinstance(entry, str):
            data = dict(all_values.get(entry) or {})
            data["key"] = entry
            meta = METRIC_CATALOGUE.get(entry, {})
            data.setdefault("label",          meta.get("label", entry))
            data.setdefault("category",       meta.get("category", "index"))
            data.setdefault("tooltip_what",   meta.get("tooltip_what", ""))
            data.setdefault("tooltip_interp", meta.get("tooltip_interp", ""))
            if "stale" not in data:
                data["stale"] = data.get("value") is None
            strip_items.append(_enrich(data))
        elif isinstance(entry, dict) and entry.get("type") == "fund":
            data = dict(get_fund_metric(entry.get("scheme_code", ""), entry.get("metric", "")))
            data["key"]        = "fund__{}_{}".format(entry.get("scheme_code",""), entry.get("metric",""))
            data["fund_entry"] = entry
            strip_items.append(_enrich(data))
        elif isinstance(entry, dict) and entry.get("type") == "benchmark":
            data = dict(get_benchmark_metric(entry.get("index_name", ""), entry.get("metric", "")))
            data["key"]        = "bm__{}_{}".format(entry.get("index_name",""), entry.get("metric",""))
            data["fund_entry"] = entry  # reuse template slot for label display
            strip_items.append(_enrich(data))
    return render(request, "benchmarks/_market_strip.html", {
        "strip_items": strip_items,
        "is_authenticated": request.user.is_authenticated,
    })


@require_GET
def market_indices_api(request):
    """GET /api/market/indices/ -- JSON fallback."""
    from .market_data import get_live_indices
    return JsonResponse({"indices": get_live_indices()})


@require_GET
def market_metrics_catalogue(request):
    """GET /api/market/metrics/ -- grouped catalogue for Manage Modal."""
    entries  = _user_entries(request)
    selected_keys = set(e for e in entries if isinstance(e, str))
    groups = {}
    for key, meta in METRIC_CATALOGUE.items():
        cat = meta.get("category", "index")
        if cat not in groups:
            groups[cat] = {"label": CATEGORY_LABELS.get(cat, cat), "metrics": []}
        groups[cat]["metrics"].append({
            "key": key, "label": meta["label"], "unit": meta.get("unit",""),
            "threshold": meta.get("threshold",""), "selected": key in selected_keys,
            "tooltip_what":  meta.get("tooltip_what",""),
            "tooltip_interp":meta.get("tooltip_interp",""),
        })
    fund_metrics = [{"key":k,"label":v["label"],"unit":v.get("unit",""),
                     "tooltip_what": v.get("tooltip_what",""),
                     "tooltip_interp":v.get("tooltip_interp","")} for k,v in FUND_METRIC_DEFS.items()]
    bench_metrics = [{"key":k,"label":v["label"],"unit":v.get("unit",""),
                      "tooltip_what":v.get("tooltip_what",""),
                      "tooltip_interp":v.get("tooltip_interp","")} for k,v in BENCHMARK_METRIC_DEFS.items()]
    saved_funds      = [e for e in entries if isinstance(e, dict) and e.get("type") == "fund"]
    saved_benchmarks = [e for e in entries if isinstance(e, dict) and e.get("type") == "benchmark"]
    ordered = [{"id":cat,**groups[cat]} for cat in CATEGORY_ORDER if cat in groups]
    return JsonResponse({
        "groups":ordered,
        "fund_metrics":fund_metrics,
        "bench_metrics":bench_metrics,
        "saved_funds":saved_funds,
        "saved_benchmarks":saved_benchmarks,
        "chosen":[e for e in entries if isinstance(e,str)]
    })


@require_POST
def save_market_strip_metrics(request):
    """POST /api/market/metrics/save/ -- save metric selection including fund & benchmark entries."""
    if not request.user.is_authenticated:
        return JsonResponse({"error":"Login required"},status=401)
    try:
        from .models import UserMarketStripProfile
        body    = json.loads(request.body)
        metrics = body.get("metrics",[])
        valid   = []
        for entry in metrics:
            if isinstance(entry,str) and entry in ALL_METRICS:
                valid.append(entry)
            elif isinstance(entry,dict) and entry.get("type")=="fund" and entry.get("scheme_code") and entry.get("metric"):
                valid.append(entry)
            elif isinstance(entry,dict) and entry.get("type")=="benchmark" and entry.get("index_name") and entry.get("metric"):
                valid.append(entry)
        profile, _ = UserMarketStripProfile.objects.get_or_create(user=request.user)
        profile.metrics = valid; profile.save()
        return JsonResponse({"saved":True,"count":len(valid)})
    except Exception as exc:
        logger.error("save_market_strip_metrics: %s",exc)
        return JsonResponse({"error":"server error"},status=500)


@require_GET
def benchmark_metric_api(request):
    """GET /api/market/benchmark-metric/?index_name=X&metric=Y"""
    idx = request.GET.get("index_name",""); mk = request.GET.get("metric","")
    if not idx or not mk: return JsonResponse({"error":"index_name and metric required"},status=400)
    return JsonResponse(get_benchmark_metric(idx,mk))


@require_GET
def benchmark_search_api(request):
    """GET /api/market/benchmark-search/?q=nifty -- returns list of BenchmarkIndex names."""
    q = request.GET.get("q","").strip()
    try:
        from .models import BenchmarkIndex
        qs = BenchmarkIndex.objects.filter(is_active=True)
        if q:
            qs = qs.filter(name__icontains=q)
        results = list(qs.values("name","description")[:20])
        return JsonResponse({"results":results})
    except Exception as exc:
        logger.error("benchmark_search_api: %s",exc)
        return JsonResponse({"results":[]})



@require_GET
def fund_metric_api(request):
    """GET /api/market/fund-metric/?scheme_code=X&metric=Y"""
    sc = request.GET.get("scheme_code",""); mk = request.GET.get("metric","")
    if not sc or not mk: return JsonResponse({"error":"scheme_code and metric required"},status=400)
    return JsonResponse(get_fund_metric(sc,mk))


@require_GET
def user_api_keys_list(request):
    """GET /api/market/apikeys/"""
    if not request.user.is_authenticated: return JsonResponse({"keys":[],"authenticated":False})
    try:
        from .models import UserAPIKey
        keys = list(UserAPIKey.objects.filter(user=request.user).values("provider","is_valid","label"))
        for k in keys:
            obj = UserAPIKey.objects.get(user=request.user,provider=k["provider"])
            k["masked_key"] = obj.masked_key()
        return JsonResponse({"keys":keys,"authenticated":True})
    except Exception as exc:
        logger.error("user_api_keys_list: %s",exc); return JsonResponse({"error":"server error"},status=500)


@require_POST
def save_api_key(request):
    """POST /api/market/apikeys/save/"""
    if not request.user.is_authenticated: return JsonResponse({"error":"Login required"},status=401)
    try:
        from .models import UserAPIKey
        body = json.loads(request.body)
        provider = body.get("provider","").lower(); api_key = body.get("api_key","").strip(); label = body.get("label","")
        if not provider or not api_key: return JsonResponse({"error":"provider and api_key required"},status=400)
        is_valid,msg = validate_fred_key(api_key) if provider=="fred" else (True,"Saved (no validation for this provider)")
        obj,created = UserAPIKey.objects.update_or_create(user=request.user,provider=provider,defaults={"api_key":api_key,"is_valid":is_valid,"label":label})
        return JsonResponse({"saved":True,"is_valid":is_valid,"message":msg,"created":created})
    except Exception as exc:
        logger.error("save_api_key: %s",exc); return JsonResponse({"error":"server error"},status=500)


@require_POST
def delete_api_key(request):
    """POST /api/market/apikeys/delete/"""
    if not request.user.is_authenticated: return JsonResponse({"error":"Login required"},status=401)
    try:
        from .models import UserAPIKey
        body = json.loads(request.body)
        UserAPIKey.objects.filter(user=request.user,provider=body.get("provider","")).delete()
        return JsonResponse({"deleted":True})
    except Exception as exc:
        logger.error("delete_api_key: %s",exc); return JsonResponse({"error":"server error"},status=500)
