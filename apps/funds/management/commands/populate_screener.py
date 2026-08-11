"""
Management command: populate_screener
======================================
All-in-one pipeline command that:
  1. Fetches INCREMENTAL NAV history from mfapi.in (only new rows since last DB date)
       - Existing funds: uses ?startDate=<last_db_date+1>&endDate=<today> endpoint
       - New funds (no history): fetches full history + meta block for category/ISIN
       - This means on subsequent runs only a few new rows are downloaded per fund,
         not thousands of historical rows re-downloaded and then discarded.
  2. Runs ingest_metadata (captnemo.in) for expense_ratio, AUM, fund_manager, start_date
     with rate limiting and automatic fallback to mftool if captnemo fails.
     Metadata staleness is checked per-fund (re-fetched if older than METADATA_STALE_DAYS).
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
    python manage.py populate_screener --force-nav            (re-fetch full NAV history)
    python manage.py populate_screener --force-metadata       (re-fetch metadata even if fresh)
    python manage.py populate_screener --resume               (skip already-processed funds)
    python manage.py populate_screener --resume-hours=24      (resume window in hours, default 24)
    python manage.py populate_screener --start-from=120503    (skip all funds before this AMFI code)
"""
import logging
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max, Q

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
            help="Only process active Direct Growth schemes or ETFs (default: True)",
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
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip schemes already processed (FundScreenerSnapshot updated within --resume-hours).",
        )
        parser.add_argument(
            "--resume-hours",
            type=int,
            default=24,
            help="Hours within which a snapshot is considered 'already done' for --resume (default 24).",
        )
        parser.add_argument(
            "--start-from",
            type=str,
            default=None,
            dest="start_from",
            help="Skip all schemes with amfi_code < this value (lexicographic). Useful for resuming from a specific point.",
        )
        parser.add_argument(
            "--shard",
            type=int,
            default=None,
            help=(
                "0-indexed shard number. Process only funds where "
                "fund_list_index %% --num-shards == shard. "
                "Use with --num-shards=7 and the day-of-week (0=Sun…6=Sat) "
                "for the weekday-split daily pipeline strategy."
            ),
        )
        parser.add_argument(
            "--num-shards",
            type=int,
            default=7,
            dest="num_shards",
            help="Total number of shards (default 7, one per weekday).",
        )
        parser.add_argument(
            "--skip-analytics-if-no-new-nav",
            action="store_true",
            dest="skip_analytics_if_no_new_nav",
            help=(
                "Skip analytics computation for funds that received no new NAV rows. "
                "On weekends/holidays when markets are closed, this reduces a "
                "34-hour analytics pass to ~10 minutes because no fund has new data."
            ),
        )
        parser.add_argument(
            "--time-limit-minutes",
            type=int,
            default=0,
            dest="time_limit_minutes",
            help=(
                "Stop gracefully after this many minutes (default 0 = no limit). "
                "Use 310 in GitHub Actions so sync_content always has time to run "
                "before the 6-hour job timeout kills the process hard."
            ),
        )

    def handle(self, *args, **options):
        import time as _time
        _run_start = _time.monotonic()

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
        do_resume = options["resume"]
        resume_hours = options["resume_hours"]
        start_from = options.get("start_from")
        shard = options.get("shard")          # None = no sharding
        num_shards = options.get("num_shards", 7)
        skip_if_no_new_nav = options.get("skip_analytics_if_no_new_nav", False)
        time_limit_sec = options.get("time_limit_minutes", 0) * 60  # 0 = no limit

        # Build queryset — always ordered by amfi_code for deterministic processing
        qs = Scheme.objects.filter(is_active=True).order_by("amfi_code")
        if direct_growth_only:
            qs = qs.filter(Q(is_direct=True, plan="GROWTH") | Q(is_etf=True))
            qs = qs.exclude(Q(scheme_type__icontains="close") | Q(scheme_type__icontains="interval"))
        if amfi_code:
            qs = qs.filter(amfi_code=amfi_code)
        if start_from:
            qs = qs.filter(amfi_code__gte=start_from)

        # ── Shard filter (for weekday-split pipeline) ─────────────────────────
        # Select every N-th fund by position so each shard covers an equal
        # fraction regardless of AMFI code distribution.
        # Example: --shard=1 --num-shards=7 processes funds at index 1, 8, 15, …
        if shard is not None and num_shards > 1:
            all_pks = list(qs.values_list('pk', flat=True))
            shard_pks = [pk for i, pk in enumerate(all_pks) if i % num_shards == shard]
            qs = Scheme.objects.filter(pk__in=shard_pks).order_by("amfi_code")
            self.stdout.write(
                f"Shard {shard}/{num_shards}: {len(shard_pks)} of {len(all_pks)} funds"
            )

        if limit:
            qs = qs[:limit]

        # Build resume set: amfi_codes already done within the past resume_hours
        already_done: set[str] = set()
        if do_resume:
            from datetime import datetime as dt
            from django.utils import timezone as tz
            from apps.funds.models import FundScreenerSnapshot
            cutoff_ts = tz.now() - timedelta(hours=resume_hours)
            already_done = set(
                FundScreenerSnapshot.objects
                .filter(updated_at__gte=cutoff_ts)
                .values_list("scheme__amfi_code", flat=True)
            )
            logger.info(
                "Resume mode: %d schemes already done within last %dh — will skip them",
                len(already_done), resume_hours,
            )

        total = qs.count()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"populate_screener: {total} schemes | "
            f"nav={'SKIP' if skip_nav else 'YES'} "
            f"meta={'SKIP' if skip_metadata else 'YES'} "
            f"analytics={'SKIP' if skip_analytics else 'YES'} "
            f"score={'SKIP' if skip_model_score else 'YES'}"
            + (" | skip-analytics-if-no-new-nav=ON" if skip_if_no_new_nav else "")
            + (f" | RESUME ({len(already_done)} skip)" if do_resume else "")
            + (f" | start-from={start_from}" if start_from else "")
        ))

        amfi_adapter = AMFIAdapter()
        cap_adapter = CaptnemoAdapter()
        stale_cutoff = date.today() - timedelta(days=METADATA_STALE_DAYS)
        today = date.today()

        nav_ok = nav_err = meta_ok = meta_err = meta_skip = analytics_ok = analytics_err = snap_ok = snap_err = score_ok = score_err = 0

        failed_nav_amfis = set()
        failed_meta_amfis = set()


        for index, scheme in enumerate(qs, 1):
            # ── Time-limit check — exit gracefully before GitHub Actions kills us ──
            if time_limit_sec and index % 5 == 0:   # check every 5 funds to reduce overhead
                elapsed = _time.monotonic() - _run_start
                remaining = time_limit_sec - elapsed
                if remaining < 180:   # < 3 minutes left → stop now
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⏱  Time limit reached after {elapsed/60:.1f} min. "
                            f"Processed {index-1}/{total} funds. "
                            f"{total - index + 1} remaining — will continue next run."
                        )
                    )
                    break

            # ── Resume: skip if already processed ────────────────────────────
            if do_resume and scheme.amfi_code in already_done:
                if index % 200 == 0:
                    self.stdout.write(f"  [{index}/{total}] resuming — {len(already_done)} skipped so far")
                continue

            # Track whether this fund received any new NAV rows this cycle.
            # Used by --skip-analytics-if-no-new-nav.
            had_new_nav: bool = False

            # ── 1. NAV ingestion (incremental) ────────────────────────────────
            if not skip_nav:
                try:
                    latest_date = (
                        NAVHistory.objects.filter(scheme=scheme)
                        .aggregate(Max("date"))["date__max"]
                    )
                    if force_nav or not latest_date or latest_date < today:
                        # Determine fetch mode:
                        #   - New fund (no history) or --force-nav → full history + meta block
                        #   - Existing fund → incremental: only rows after latest_date
                        is_full_fetch = force_nav or not latest_date
                        since_date = None if is_full_fetch else latest_date

                        history, meta_block = _fetch_nav_incremental(
                            amfi_adapter, scheme.amfi_code, since_date=since_date
                        )

                        if history:
                            new_rows = []
                            for entry in history:
                                entry_date = parse_amfi_date(entry.get("date", ""))
                                if not entry_date:
                                    continue
                                # On a full fetch, skip any row on-or-before the latest_date
                                # (safety guard; shouldn't be needed for incremental)
                                if not is_full_fetch and latest_date and entry_date <= latest_date:
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
                                had_new_nav = True   # ← new rows saved
                            # Refresh in-memory for downstream steps
                            scheme.refresh_from_db()

                        # Save scheme_category/ISIN from mfapi meta block.
                        # meta_block is only populated on full-history fetches
                        # (date-range requests don't return the meta block).
                        if meta_block:
                            _update_scheme_from_mfapi_meta(scheme, meta_block)

                        # For incremental fetches: empty result means no new trading days
                        # since last DB date — this is perfectly valid (weekend/holiday).
                        # Only flag as error on a full fetch (new fund) that returns nothing.
                        if not history and is_full_fetch:
                            failed_nav_amfis.add(scheme.amfi_code)
                            nav_err += 1
                        else:
                            nav_ok += 1  # incremental empty = already up-to-date
                    else:
                        nav_ok += 1  # latest_date >= today, nothing to do
                except Exception as exc:
                    failed_nav_amfis.add(scheme.amfi_code)
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
                            failed_meta_amfis.add(scheme.amfi_code)
                            meta_err += 1
                except Exception as exc:
                    failed_meta_amfis.add(scheme.amfi_code)
                    meta_err += 1
                    logger.error(f"[{scheme.amfi_code}] metadata ingest error: {exc}")

                time.sleep(cap_adapter.RATE_LIMIT_DELAY)

            # ── 3. Analytics ───────────────────────────────────────────
            if not skip_analytics:
                # On weekends/holidays, no new NAV data arrives for any fund.
                # If the caller passed --skip-analytics-if-no-new-nav, skip the
                # ~50-second analytics computation for this fund since it would
                # produce identical results to yesterday's run.
                if skip_if_no_new_nav and not had_new_nav:
                    analytics_ok += 1   # count as OK — data is still valid
                else:
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

        # ── RETRY PHASE ────────────────────────────────────────────────────────
        retry_amfis = failed_nav_amfis | failed_meta_amfis
        final_failed = {}
        if retry_amfis:
            self.stdout.write(self.style.WARNING(f"\nRetrying {len(retry_amfis)} failed funds..."))
            time.sleep(2)  # Pause before retry burst
            
            for amfi_code in retry_amfis:
                if not amfi_code:
                    continue
                scheme = Scheme.objects.filter(amfi_code=amfi_code).first()
                if not scheme:
                    continue
                error_reasons = []
                
                # Retry NAV — use incremental if we have partial history, full if not
                if amfi_code in failed_nav_amfis:
                    try:
                        latest_date = (
                            NAVHistory.objects.filter(scheme=scheme)
                            .aggregate(Max("date"))["date__max"]
                        )
                        history, meta_block = _fetch_nav_incremental(
                            amfi_adapter, amfi_code, since_date=latest_date
                        )
                        if history:
                            new_rows = []
                            for entry in history:
                                entry_date = parse_amfi_date(entry.get("date", ""))
                                if not entry_date:
                                    continue
                                if latest_date and entry_date <= latest_date:
                                    continue
                                try:
                                    nav_val = float(entry["nav"])
                                    if nav_val > 0:
                                        new_rows.append(NAVHistory(scheme=scheme, date=entry_date, nav=nav_val))
                                except (ValueError, TypeError, KeyError):
                                    continue
                            if new_rows:
                                NAVHistory.objects.bulk_create(new_rows, ignore_conflicts=True)
                                latest_entry = sorted(new_rows, key=lambda r: r.date)[-1]
                                Scheme.objects.filter(pk=scheme.pk).update(nav_latest=latest_entry.nav, nav_date=latest_entry.date)
                            if meta_block:
                                _update_scheme_from_mfapi_meta(scheme, meta_block)
                            failed_nav_amfis.remove(amfi_code)
                        else:
                            error_reasons.append("NAV fetch returned empty")
                    except Exception as exc:
                        error_reasons.append(f"NAV exception: {exc}")
                        
                # Retry Metadata
                if amfi_code in failed_meta_amfis:
                    try:
                        isin = scheme.isin_growth or scheme.isin_idcw
                        fund_info = None
                        if isin:
                            fund_info = _fetch_captnemo_with_fallback(cap_adapter, isin, scheme.amfi_code)
                        
                        if fund_info:
                            meta_fields = cap_adapter.extract_scheme_meta(fund_info)
                            SchemeMeta.objects.update_or_create(scheme=scheme, defaults=meta_fields)
                            update_fields = {}
                            if meta_fields.get("expense_ratio") is not None: update_fields["expense_ratio"] = meta_fields["expense_ratio"]
                            if meta_fields.get("aum") is not None: update_fields["aum_cr"] = meta_fields["aum"]
                            if update_fields: Scheme.objects.filter(pk=scheme.pk).update(**update_fields)
                            failed_meta_amfis.remove(amfi_code)
                        else:
                            error_reasons.append("Captnemo metadata empty after retry")
                    except Exception as exc:
                        error_reasons.append(f"Metadata exception: {exc}")
                        
                if error_reasons:
                    final_failed[amfi_code] = {
                        "name": getattr(scheme, 'scheme_name', ''),
                        "reasons": error_reasons
                    }
                    
            if final_failed:
                import json
                import os
                from django.conf import settings
                reports_dir = os.path.join(settings.MEDIA_ROOT, "reports")
                os.makedirs(reports_dir, exist_ok=True)
                report_path = os.path.join(reports_dir, "failed_funds_report.json")
                with open(report_path, "w") as f:
                    json.dump(final_failed, f, indent=2)
                self.stdout.write(self.style.ERROR(f"Final failed funds: {len(final_failed)} -> Saved to {report_path}"))
            else:
                self.stdout.write(self.style.SUCCESS("All retries succeeded!"))

        self.stdout.write(self.style.SUCCESS(
            f"\nFinished populate_screener:\n"
            f" NAV:   {nav_ok} OK, {nav_err} Error\n"
            f" Meta:  {meta_ok} OK, {meta_skip} Skip, {meta_err} Error\n"
            f" Anal:  {analytics_ok} OK, {analytics_err} Error\n"
            f" Snap:  {snap_ok} OK, {snap_err} Error\n"
            f" Score: {score_ok} OK, {score_err} Error\n"
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

def _fetch_nav_incremental(adapter: AMFIAdapter, amfi_code: str, since_date=None):
    """
    Fetch NAV history from mfapi.in, incrementally when possible.

    Args:
        adapter:    AMFIAdapter instance (used for mftool fallback).
        amfi_code:  AMFI scheme code.
        since_date: If provided (a date object), fetches only rows AFTER this date
                    using the mfapi date-range endpoint:
                    GET /mf/{code}?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
                    Note: the date-range endpoint does NOT return a meta block.
                    If None, fetches full history (returns meta block too).

    Returns:
        (history_list, meta_dict)
        history_list: list of {'date': 'DD-MM-YYYY', 'nav': '...'}
        meta_dict:    dict from mfapi meta block, or {} for incremental fetches.
    """
    import requests
    from datetime import date as _date, timedelta

    today_str = _date.today().strftime("%Y-%m-%d")

    if since_date is not None:
        # Incremental: request only rows from (since_date + 1) to today
        start_str = (since_date + timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"https://api.mfapi.in/mf/{amfi_code}?startDate={start_str}&endDate={today_str}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            history = data.get("data", [])
            # Date-range endpoint does not return meta block — return empty dict
            return history, {}
        except Exception as exc:
            logger.warning(f"[{amfi_code}] mfapi.in incremental fetch failed: {exc}")
            # Fallback: full mftool fetch; caller will filter by since_date
            history = adapter.fetch_nav_history_mftool(amfi_code)
            return history, {}
    else:
        # Full fetch: returns both NAV history and meta block
        url = f"https://api.mfapi.in/mf/{amfi_code}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", []), data.get("meta", {})
        except Exception as exc:
            logger.warning(f"[{amfi_code}] mfapi.in full fetch failed: {exc}")
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
