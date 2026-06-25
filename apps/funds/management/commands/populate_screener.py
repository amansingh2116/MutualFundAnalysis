"""
Management command: populate_screener
======================================
All-in-one pipeline command that:
  1. Fetches full NAV history from mfapi.in AND saves scheme_category from meta block
  2. Runs ingest_metadata (captnemo.in) for expense_ratio, AUM, fund_manager, start_date
     with rate limiting and automatic fallback to mftool if captnemo fails
  3. Computes all analytics (trailing returns, rolling returns, risk metrics) from NAV
  4. Builds/refreshes the FundScreenerSnapshot
  5. Computes and saves the full model score (FundModelScore) using DB-only portfolio data
  6. Calls populate_home_dashboard (CategorySnapshot + quartile ranks) unless skipped

Usage:
    python manage.py populate_screener
    python manage.py populate_screener --limit=100
    python manage.py populate_screener --amfi=120503
    python manage.py populate_screener --direct-growth-only   (default: True)
    python manage.py populate_screener --skip-nav             (skip NAV fetch)
    python manage.py populate_screener --skip-metadata        (skip captnemo metadata)
    python manage.py populate_screener --skip-analytics       (skip compute_all_metrics)
    python manage.py populate_screener --skip-model-score     (skip FundModelScore compute)
    python manage.py populate_screener --skip-home-dashboard  (skip populate_home_dashboard)
    python manage.py populate_screener --force-nav            (re-fetch NAV even if up to date)
    python manage.py populate_screener --force-metadata       (re-fetch metadata even if fresh)
"""
import logging
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max

from adapters.amfi_adapter import AMFIAdapter
from adapters.captnemo_adapter import CaptnemoAdapter
from apps.analytics.engine import compute_all_metrics
from apps.core.utils import parse_amfi_date
from apps.funds.models import NAVHistory, Scheme, SchemeMeta
from apps.funds.screener import refresh_snapshot_for_scheme, compute_and_save_model_score

logger = logging.getLogger("mfanalysis")

# Re-fetch metadata if older than this many days
METADATA_STALE_DAYS = 7


class Command(BaseCommand):
    help = "Full pipeline: NAV + metadata + analytics + screener snapshot"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--amfi", type=str, default=None)
        parser.add_argument(
            "--direct-growth-only",
            action="store_true",
            default=True,
            help="Only process active Direct Growth schemes (default: True)",
        )
        parser.add_argument("--skip-nav", action="store_true")
        parser.add_argument("--skip-metadata", action="store_true")
        parser.add_argument("--skip-analytics", action="store_true")
        parser.add_argument("--skip-model-score", action="store_true",
                            help="Skip FundModelScore computation (faster, no scoring)")
        parser.add_argument("--skip-home-dashboard", action="store_true",
                            help="Skip populate_home_dashboard auto-call at end")
        parser.add_argument("--force-nav", action="store_true")
        parser.add_argument("--force-metadata", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        amfi_code = options["amfi"]
        direct_growth_only = options["direct_growth_only"]
        skip_nav = options["skip_nav"]
        skip_metadata = options["skip_metadata"]
        skip_analytics = options["skip_analytics"]
        skip_model_score = options["skip_model_score"]
        skip_home_dashboard = options["skip_home_dashboard"]
        force_nav = options["force_nav"]
        force_metadata = options["force_metadata"]

        # Build queryset
        qs = Scheme.objects.filter(is_active=True)
        if direct_growth_only:
            qs = qs.filter(is_direct=True, plan="GROWTH")
        if amfi_code:
            qs = qs.filter(amfi_code=amfi_code)
        if limit:
            qs = qs[: limit]

        total = qs.count()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"populate_screener: {total} schemes | "
            f"nav={'SKIP' if skip_nav else 'YES'} "
            f"meta={'SKIP' if skip_metadata else 'YES'} "
            f"analytics={'SKIP' if skip_analytics else 'YES'} "
            f"score={'SKIP' if skip_model_score else 'YES'}"
        ))

        amfi_adapter = AMFIAdapter()
        cap_adapter = CaptnemoAdapter()
        stale_cutoff = date.today() - timedelta(days=METADATA_STALE_DAYS)
        today = date.today()

        nav_ok = nav_err = meta_ok = meta_err = meta_skip = analytics_ok = analytics_err = snap_ok = snap_err = score_ok = score_err = 0

        for index, scheme in enumerate(qs, 1):
            # ── 1. NAV ingestion ──────────────────────────────────────────────
            if not skip_nav:
                try:
                    latest_date = (
                        NAVHistory.objects.filter(scheme=scheme)
                        .aggregate(Max("date"))["date__max"]
                    )
                    if force_nav or not latest_date or latest_date < today:
                        history, meta_block = _fetch_nav_and_meta(amfi_adapter, scheme.amfi_code)
                        if history:
                            cutoff = latest_date if (latest_date and not force_nav) else date(1990, 1, 1)
                            new_rows = []
                            for entry in history:
                                entry_date = parse_amfi_date(entry.get("date", ""))
                                if not entry_date or entry_date <= cutoff:
                                    continue
                                try:
                                    nav_val = float(entry["nav"])
                                    if nav_val > 0:
                                        new_rows.append(
                                            NAVHistory(scheme=scheme, date=entry_date, nav=nav_val)
                                        )
                                except (ValueError, TypeError, KeyError):
                                    continue

                            if new_rows:
                                NAVHistory.objects.bulk_create(new_rows, ignore_conflicts=True)
                                latest_entry = sorted(new_rows, key=lambda r: r.date)[-1]
                                Scheme.objects.filter(pk=scheme.pk).update(
                                    nav_latest=latest_entry.nav,
                                    nav_date=latest_entry.date,
                                )
                            # Refresh in-memory for downstream steps
                            scheme.refresh_from_db()

                        # Save scheme_category from mfapi meta if currently blank
                        if meta_block:
                            _update_scheme_from_mfapi_meta(scheme, meta_block)
                        nav_ok += 1
                    else:
                        nav_ok += 1  # already up to date
                except Exception as exc:
                    nav_err += 1
                    logger.error(f"[{scheme.amfi_code}] NAV ingest error: {exc}")

                time.sleep(amfi_adapter.RATE_LIMIT_DELAY)

            # ── 2. Metadata (captnemo with fallback) ──────────────────────────
            if not skip_metadata:
                try:
                    meta_obj = None
                    try:
                        meta_obj = SchemeMeta.objects.get(scheme=scheme)
                        if not force_metadata and meta_obj.last_fetched.date() > stale_cutoff:
                            meta_skip += 1
                            meta_obj = meta_obj  # still valid for analytics reference
                    except SchemeMeta.DoesNotExist:
                        meta_obj = None

                    if force_metadata or meta_obj is None or (meta_obj and meta_obj.last_fetched.date() <= stale_cutoff):
                        isin = scheme.isin_growth or scheme.isin_idcw
                        fund_info = None
                        if isin:
                            fund_info = _fetch_captnemo_with_fallback(cap_adapter, isin, scheme.amfi_code)

                        if fund_info:
                            meta_fields = cap_adapter.extract_scheme_meta(fund_info)
                            SchemeMeta.objects.update_or_create(scheme=scheme, defaults=meta_fields)
                            # Denormalize expense_ratio and aum_cr onto Scheme
                            update_fields = {}
                            if meta_fields.get("expense_ratio") is not None:
                                update_fields["expense_ratio"] = meta_fields["expense_ratio"]
                            if meta_fields.get("aum") is not None:
                                update_fields["aum_cr"] = meta_fields["aum"]
                            if update_fields:
                                Scheme.objects.filter(pk=scheme.pk).update(**update_fields)
                            scheme.refresh_from_db()
                            meta_ok += 1
                        else:
                            meta_err += 1
                except Exception as exc:
                    meta_err += 1
                    logger.error(f"[{scheme.amfi_code}] metadata ingest error: {exc}")

                time.sleep(cap_adapter.RATE_LIMIT_DELAY)

            # ── 3. Analytics ──────────────────────────────────────────────────
            if not skip_analytics:
                try:
                    compute_all_metrics(scheme)
                    analytics_ok += 1
                except Exception as exc:
                    analytics_err += 1
                    logger.error(f"[{scheme.amfi_code}] analytics error: {exc}")

            # ── 4. Screener snapshot ──────────────────────────────────────────
            try:
                scheme_with_meta = Scheme.objects.select_related("meta").get(pk=scheme.pk)
                refresh_snapshot_for_scheme(scheme_with_meta)
                snap_ok += 1
            except Exception as exc:
                snap_err += 1
                logger.error(f"[{scheme.amfi_code}] snapshot error: {exc}")

            # ── 5. Model score (DB-only portfolio, Option B) ────────────────────
            if not skip_model_score:
                try:
                    compute_and_save_model_score(scheme_with_meta)
                    score_ok += 1
                except Exception as exc:
                    score_err += 1
                    logger.error(f"[{scheme.amfi_code}] model score error: {exc}")

            # Progress reporting every 50 schemes
            if index % 50 == 0:
                self.stdout.write(
                    f"  [{index}/{total}] "
                    f"nav={nav_ok}({nav_err}err) "
                    f"meta={meta_ok}+{meta_skip}skip({meta_err}err) "
                    f"analytics={analytics_ok}({analytics_err}err) "
                    f"snap={snap_ok}({snap_err}err)"
                )

        self.stdout.write(self.style.SUCCESS(
            f"\n=== populate_screener complete ===\n"
            f"NAV:         ok={nav_ok}  err={nav_err}\n"
            f"Metadata:    ok={meta_ok}  skip={meta_skip}  err={meta_err}\n"
            f"Analytics:   ok={analytics_ok}  err={analytics_err}\n"
            f"Snapshots:   ok={snap_ok}  err={snap_err}\n"
            f"Model Score: ok={score_ok}  err={score_err}"
        ))

        # ── Auto-call populate_home_dashboard ──────────────────────────────────
        if not skip_home_dashboard and not amfi_code:
            # Only run for full runs, not single-scheme targeted updates
            self.stdout.write("\nRunning populate_home_dashboard...")
            try:
                from django.core.management import call_command
                call_command("populate_home_dashboard", verbosity=0)
                self.stdout.write(self.style.SUCCESS("populate_home_dashboard: complete"))
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f"populate_home_dashboard failed: {exc}")
                )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fetch_nav_and_meta(adapter: AMFIAdapter, amfi_code: str):
    """
    Fetch NAV history + meta block from mfapi.in in one request.
    Returns (history_list, meta_dict).
    """
    import requests
    url = f"https://api.mfapi.in/mf/{amfi_code}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []), data.get("meta", {})
    except Exception as exc:
        logger.warning(f"[{amfi_code}] mfapi.in fetch failed: {exc}")
        # Fallback to mftool for NAV only
        history = adapter.fetch_nav_history_mftool(amfi_code)
        return history, {}


def _update_scheme_from_mfapi_meta(scheme, meta_block: dict):
    """
    Persist scheme_category (and isin_growth if missing) from mfapi meta block.
    Only updates blank fields to avoid overwriting better data.
    """
    update = {}
    if not scheme.scheme_category and meta_block.get("scheme_category"):
        update["scheme_category"] = meta_block["scheme_category"]
    if not scheme.isin_growth and meta_block.get("isin_growth"):
        update["isin_growth"] = meta_block["isin_growth"]
    if update:
        Scheme.objects.filter(pk=scheme.pk).update(**update)
        scheme.refresh_from_db()


def _fetch_captnemo_with_fallback(adapter: CaptnemoAdapter, isin: str, amfi_code: str):
    """
    Try captnemo.in first; if it fails (404/timeout/empty), fall back to
    AMFI's own NAV data for the key fields we need from SchemeMeta.
    Returns a fund_info dict or None.
    """
    # Primary: captnemo
    try:
        fund_info = adapter.fetch_fund_info(isin=isin)
        if fund_info:
            return fund_info
    except Exception as exc:
        logger.warning(f"[{amfi_code}] captnemo primary failed: {exc}")

    # Secondary: try amfi_code endpoint
    try:
        fund_info = adapter.fetch_fund_info_by_amfi(amfi_code)
        if fund_info:
            logger.debug(f"[{amfi_code}] captnemo fallback via AMFI code succeeded")
            return fund_info
    except Exception as exc:
        logger.warning(f"[{amfi_code}] captnemo AMFI fallback failed: {exc}")

    # Tertiary: mftool scheme info (provides start_date via date of first NAV)
    try:
        from mftool import Mftool
        mf = Mftool()
        details = mf.get_scheme_details(amfi_code)
        if details:
            # Synthesize minimal fund_info dict compatible with extract_scheme_meta
            return {
                "fund_manager": details.get("fund_manager", ""),
                "start_date": details.get("inception_date", ""),
                "expense_ratio": None,
                "aum": None,
                "volatility": None,
                "returns": {},
                "sip_dates": "",
                "sip_available": "Y",
                "lump_available": "Y",
                "sip_min": None,
                "lump_min": None,
                "lump_min_additional": None,
                "sip_multiplier": None,
                "redemption_allowed": "Y",
                "switch_allowed": "Y",
                "stp_flag": "N",
                "swp_flag": "N",
                "lock_in_period": 0,
                "tax_period": 0,
                "fund_rating": None,
                "fund_rating_date": "",
                "expense_ratio_date": "",
                "crisil_rating": "",
                "investment_objective": "",
                "portfolio_turnover": None,
                "detail_info_url": "",
                "comparison": [],
            }
    except Exception as exc:
        logger.debug(f"[{amfi_code}] mftool scheme_details fallback failed: {exc}")

    return None
