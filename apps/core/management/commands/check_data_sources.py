"""
management/commands/check_data_sources.py
==========================================
Data source schema contract validator.

Checks each external data source against a known "contract" (expected fields,
column counts, value ranges) and warns loudly when anything has changed.

Purpose:
    When AMFI, mfapi.in, NSE, or captnemo.in change their response format,
    this command detects it immediately rather than letting the daily pipeline
    silently produce corrupt data (like the 6->8 column AMFI incident in 2026).

Usage:
    python manage.py check_data_sources            # full check
    python manage.py check_data_sources --source amfi     # single source
    python manage.py check_data_sources --fail-fast       # exit 1 on first failure
    python manage.py check_data_sources --skip-nse        # skip NSE (slow in CI)

Outputs:
    - Console table with PASS / WARN / FAIL per source
    - GitHub Actions ::warning:: / ::error:: annotations (visible in CI log)
    - Exit code 1 if any source FAILs (for CI pipeline gating)

Integrate into CI:
    Add as the first step in daily_pipeline.yml so format changes fail loudly
    before corrupting the database.
"""
import json
import logging
import sys
from datetime import date, datetime

from django.core.management.base import BaseCommand

logger = logging.getLogger('mfanalysis')


# ============================================================================
# Contract definitions
# Each contract describes what we expect from a live API call.
# ============================================================================

CONTRACTS = {

    # -- AMFI NAVAll.txt -----------------------------------------------------
    'amfi': {
        'description': 'AMFI NAVAll.txt -- scheme master + daily NAV',
        'url': 'https://www.amfiindia.com/spages/NAVAll.txt',
        'type': 'text',
        'checks': [
            {'name': 'row_count',            'min': 10_000, 'max': 25_000},
            {'name': 'direct_growth_count',  'min': 1_000},
            {'name': 'etf_count',            'min': 300},
            {'name': 'amfi_code_numeric',    'sample_size': 50},
            {'name': 'nav_parseable',        'sample_size': 50},
            {'name': 'date_parseable',       'sample_size': 50},
            {'name': 'column_count_stable',  'expected_cols': 8},
        ],
    },

    # -- mfapi.in ------------------------------------------------------------
    'mfapi': {
        'description': 'mfapi.in -- NAV history + scheme metadata',
        'url': 'https://api.mfapi.in/mf/120503',
        'type': 'json',
        'checks': [
            {'name': 'keys_present',    'keys': ['meta', 'data']},
            {'name': 'meta_keys',       'keys': ['scheme_name', 'fund_house', 'scheme_type', 'scheme_category']},
            {'name': 'data_nonempty'},
            {'name': 'data_item_keys',  'keys': ['date', 'nav'], 'sample_size': 5},
            {'name': 'nav_parseable',   'sample_size': 5},
            {'name': 'data_count',      'min': 2_500},
        ],
    },

    # -- NSE benchmark index -------------------------------------------------
    'nse_benchmark': {
        'description': 'NSE benchmark index (NIFTY 50 via nselib)',
        'type': 'nselib',
        'index': 'NIFTY 50',
        'checks': [
            {'name': 'row_count',      'min': 1},
            {'name': 'close_parseable'},
            {'name': 'date_parseable'},
        ],
    },

    # -- captnemo.in ---------------------------------------------------------
    'captnemo': {
        'description': 'mf.captnemo.in -- Kuvera fund metadata proxy',
        'url': 'https://mf.captnemo.in/kuvera/INF209K01YN0',  # Aditya Birla Banking PSU Debt Direct Growth
        'type': 'json',
        'checks': [
            {'name': 'is_list'},
            {'name': 'list_nonempty'},
            # Fields confirmed from live API: ISIN (uppercase), plan, direct, nav (nested), expense_ratio
            {'name': 'item_keys', 'keys': ['ISIN', 'plan', 'direct', 'nav'], 'sample_size': 1},
        ],
    },
}


# ============================================================================
# Result tracking
# ============================================================================

PASS = 'PASS'
WARN = 'WARN'
FAIL = 'FAIL'


class SourceResult:
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.status = PASS
        self.checks: list[dict] = []

    def add(self, check_name: str, status: str, message: str):
        if status == FAIL and self.status != FAIL:
            self.status = FAIL
        elif status == WARN and self.status == PASS:
            self.status = WARN
        self.checks.append({'name': check_name, 'status': status, 'message': message})

    def ok(self, name: str, msg: str):   self.add(name, PASS, msg)
    def warn(self, name: str, msg: str): self.add(name, WARN, msg)
    def fail(self, name: str, msg: str): self.add(name, FAIL, msg)


# ============================================================================
# Individual source checkers
# ============================================================================

def _check_amfi(contract: dict, result: SourceResult) -> None:
    """Validate AMFI NAVAll.txt format and content."""
    import urllib.request
    try:
        with urllib.request.urlopen(contract['url'], timeout=30) as r:
            text = r.read().decode('utf-8', errors='replace')
    except Exception as e:
        result.fail('fetch', f"Failed to download NAVAll.txt: {e}")
        return

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Detect format version
    header_line = lines[0] if lines else ''
    detected_cols = 8 if (';Plan;' in header_line or 'Plan;Option' in header_line) else 6
    new_fmt = detected_cols == 8

    # Parse data rows
    current_type = ''
    schemes = []
    for line in lines:
        if line.startswith('Scheme Code') or line.startswith(';ISIN'):
            continue
        if line.startswith(('Open Ended', 'Close Ended', 'Interval')):
            current_type = line
            continue
        if not line[0].isdigit() and ';' not in line:
            continue
        parts = line.split(';')
        min_cols = 8 if new_fmt else 6
        if len(parts) < min_cols or not parts[0].strip().isdigit():
            continue
        if new_fmt:
            schemes.append({
                'amfi_code': parts[0].strip(),
                'nav':  parts[6].strip(),
                'date': parts[7].strip(),
                'name': parts[3].strip(),
                'plan': parts[4].strip().lower(),
                'opt':  parts[5].strip().lower(),
                'type': current_type,
            })
        else:
            schemes.append({
                'amfi_code': parts[0].strip(),
                'nav':  parts[4].strip(),
                'date': parts[5].strip(),
                'name': parts[3].strip(),
                'plan': '',
                'opt':  '',
                'type': current_type,
            })

    total = len(schemes)

    # row_count
    if total < 10_000:
        result.fail('row_count', f"Only {total} rows -- expected 10,000+. File may be truncated.")
    elif total > 25_000:
        result.warn('row_count', f"{total} rows -- unusually high (expected <25,000).")
    else:
        result.ok('row_count', f"{total} total rows (healthy)")

    # column_count_stable
    expected = contract['checks'][-1].get('expected_cols', 8)
    if detected_cols != expected:
        result.warn(
            'column_count_stable',
            f"Column count changed: expected {expected}-col, detected {detected_cols}-col. "
            f"Review amfi_adapter._parse_navall() and build_scheme_master."
        )
    else:
        result.ok('column_count_stable', f"Column format confirmed: {detected_cols}-column layout")

    # direct_growth_count
    open_ended = [s for s in schemes
                  if 'close' not in s['type'].lower() and 'interval' not in s['type'].lower()]
    if new_fmt:
        direct_growth = [s for s in open_ended
                         if 'direct' in s['plan'] and 'growth' in s['opt'] and 'idcw' not in s['opt']]
    else:
        direct_growth = [s for s in open_ended
                         if 'direct' in s['name'].lower() and 'growth' in s['name'].lower()]

    if len(direct_growth) < 1_000:
        result.fail('direct_growth_count',
                    f"Only {len(direct_growth)} Direct Growth schemes found -- expected 1,000+. "
                    f"Format: {detected_cols}-col. Filtering logic may be broken.")
    else:
        result.ok('direct_growth_count', f"{len(direct_growth)} Direct Growth schemes")

    # etf_count
    etfs = [s for s in open_ended if 'etf' in s['name'].lower()]
    if len(etfs) < 300:
        result.warn('etf_count', f"Only {len(etfs)} ETFs (expected 300+).")
    else:
        result.ok('etf_count', f"{len(etfs)} ETF schemes")

    # amfi_code_numeric
    bad_codes = [s['amfi_code'] for s in schemes[:50] if not s['amfi_code'].isdigit()]
    if bad_codes:
        result.fail('amfi_code_numeric', f"Non-numeric amfi_codes: {bad_codes[:5]}")
    else:
        result.ok('amfi_code_numeric', "All sampled amfi_codes are numeric")

    # nav_parseable
    nav_errors = []
    for s in schemes[:50]:
        try:
            v = float(s['nav'])
            if v <= 0:
                nav_errors.append(f"{s['amfi_code']}: nav={s['nav']} (non-positive)")
        except (ValueError, TypeError):
            nav_errors.append(f"{s['amfi_code']}: nav='{s['nav']}' (not a float)")
    if nav_errors:
        result.warn('nav_parseable', f"{len(nav_errors)} NAV issues in first 50: {nav_errors[:2]}")
    else:
        result.ok('nav_parseable', "All sampled NAV values are valid floats")

    # date_parseable
    date_errors = []
    for s in schemes[:50]:
        parsed = False
        for fmt in ('%d-%b-%Y', '%d-%m-%Y'):
            try:
                datetime.strptime(s['date'], fmt)
                parsed = True
                break
            except ValueError:
                pass
        if not parsed:
            date_errors.append(f"{s['amfi_code']}: '{s['date']}'")
    if date_errors:
        result.warn('date_parseable', f"{len(date_errors)} date issues: {date_errors[:2]}")
    else:
        result.ok('date_parseable', "All sampled dates are parseable")


def _check_mfapi(contract: dict, result: SourceResult) -> None:
    """Validate mfapi.in scheme endpoint structure."""
    import urllib.request
    try:
        with urllib.request.urlopen(contract['url'], timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        result.fail('fetch', f"Failed to reach mfapi.in: {e}")
        return

    # keys_present
    for key in ['meta', 'data']:
        if key not in data:
            result.fail('keys_present', f"Missing top-level key '{key}' in mfapi.in response")
            return
    result.ok('keys_present', "Top-level keys 'meta' and 'data' present")

    # meta_keys
    meta = data.get('meta', {})
    missing_meta = [k for k in ['scheme_name', 'fund_house', 'scheme_type', 'scheme_category'] if k not in meta]
    if missing_meta:
        result.fail('meta_keys', f"Missing meta fields: {missing_meta}")
    else:
        result.ok('meta_keys', f"meta OK. scheme_category='{meta.get('scheme_category', '?')}'")

    # data_nonempty
    nav_data = data.get('data', [])
    if not nav_data:
        result.fail('data_nonempty', "mfapi.in 'data' list is empty")
        return
    result.ok('data_nonempty', f"data list has {len(nav_data)} entries")

    # data_count
    if len(nav_data) < 2_500:
        result.warn('data_count', f"Only {len(nav_data)} NAV rows (expected 2,500+).")
    else:
        result.ok('data_count', f"{len(nav_data)} NAV history rows")

    # data_item_keys + nav_parseable
    item_errors = []
    nav_errors = []
    for item in nav_data[:5]:
        for k in ['date', 'nav']:
            if k not in item:
                item_errors.append(f"Missing '{k}' in data item")
        try:
            float(item.get('nav', 'x'))
        except (ValueError, TypeError):
            nav_errors.append(f"nav='{item.get('nav')}' is not a float")

    if item_errors:
        result.fail('data_item_keys', '; '.join(item_errors))
    else:
        result.ok('data_item_keys', "Data items have 'date' and 'nav' keys")

    if nav_errors:
        result.warn('nav_parseable', '; '.join(nav_errors))
    else:
        result.ok('nav_parseable', "All sampled NAV values in data are parseable")


def _check_nse_benchmark(contract: dict, result: SourceResult) -> None:
    """Validate NSE benchmark index fetch via BenchmarkAdapter."""
    try:
        from datetime import timedelta
        import datetime as dt
        end = dt.date.today()
        start = end - timedelta(days=7)

        from adapters.benchmark_adapter import BenchmarkAdapter
        adapter = BenchmarkAdapter()
        rows = adapter.fetch_index_history(
            contract['index'],
            start.strftime('%d-%m-%Y'),
            end.strftime('%d-%m-%Y'),
        )
    except Exception as e:
        result.fail('fetch', f"NSE benchmark fetch failed for '{contract['index']}': {e}")
        return

    if not rows:
        result.warn('row_count', f"No rows for '{contract['index']}' in last 7 days (market holiday?)")
        return

    result.ok('row_count', f"{len(rows)} rows for '{contract['index']}' over last 7 days")

    close_errors = []
    for row in rows[:5]:
        close = row.get('close')
        try:
            v = float(close)
            if v <= 0:
                close_errors.append(f"Non-positive close: {close}")
        except (TypeError, ValueError):
            close_errors.append(f"close='{close}' not a float")

    if close_errors:
        result.fail('close_parseable', '; '.join(close_errors))
    else:
        result.ok('close_parseable', f"Close values OK (latest: {rows[0].get('close')})")

    date_errors = []
    for row in rows[:5]:
        d = row.get('date')
        if not isinstance(d, (date, datetime)):
            date_errors.append(f"date='{d}' (type: {type(d).__name__}) is not a date object")

    if date_errors:
        result.warn('date_parseable', '; '.join(date_errors))
    else:
        result.ok('date_parseable', f"Date fields are proper date objects (latest: {rows[0].get('date')})")


def _check_captnemo(contract: dict, result: SourceResult) -> None:
    """Validate captnemo.in API structure."""
    import urllib.request
    try:
        req = urllib.request.Request(
            contract['url'],
            headers={'User-Agent': 'MutualFundAnalysis/1.0 (health-check)'}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        result.warn('fetch', f"captnemo.in unreachable: {e}. This API is unofficial -- non-critical.")
        return

    if not isinstance(data, list):
        result.fail('is_list', f"Expected list response, got {type(data).__name__}. API format may have changed.")
        return
    result.ok('is_list', "Response is a list (as expected)")

    if not data:
        result.warn('list_nonempty', "captnemo.in returned empty list for test ISIN.")
        return
    result.ok('list_nonempty', f"List has {len(data)} plan entries")

    item = data[0]
    missing = [k for k in ['ISIN', 'nav', 'plan', 'direct'] if k not in item]
    if missing:
        # captnemo is an unofficial API — field changes are non-critical (WARN not FAIL)
        result.warn('item_keys', f"Missing fields: {missing}. captnemo API schema may have changed -- "
                                 f"check CaptnemoAdapter and ingest_metadata if AUM/expense data stops updating.")
    else:
        result.ok('item_keys', f"All key fields present. plan='{item.get('plan')}' direct='{item.get('direct')}'")


# ============================================================================
# Output helpers
# ============================================================================

STATUS_ICONS = {PASS: '[OK  ]', WARN: '[WARN]', FAIL: '[FAIL]'}
GH_LEVEL = {PASS: None, WARN: 'warning', FAIL: 'error'}


def _emit_github_annotation(level: str, source: str, message: str) -> None:
    """Emit a GitHub Actions annotation line."""
    print(f"::{level} title=Data Source [{source}]::{message}")


class Command(BaseCommand):
    help = 'Validate external data source schema contracts and warn on format changes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            choices=list(CONTRACTS.keys()),
            default=None,
            help='Check only a specific source (default: all)',
        )
        parser.add_argument(
            '--fail-fast',
            action='store_true',
            help='Exit immediately on first FAIL result',
        )
        parser.add_argument(
            '--skip-nse',
            action='store_true',
            help='Skip NSE benchmark check (requires nselib, can be slow in CI)',
        )

    def handle(self, *args, **options):
        source_filter = options['source']
        fail_fast = options['fail_fast']
        skip_nse = options['skip_nse']

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nData Source Contract Check -- {date.today()}\n"
        ))

        checkers = {
            'amfi':          _check_amfi,
            'mfapi':         _check_mfapi,
            'nse_benchmark': _check_nse_benchmark,
            'captnemo':      _check_captnemo,
        }

        if skip_nse:
            checkers.pop('nse_benchmark', None)

        to_check = {
            k: v for k, v in checkers.items()
            if source_filter is None or k == source_filter
        }

        all_results: list[SourceResult] = []
        any_fail = False

        for source_name, checker_fn in to_check.items():
            contract = CONTRACTS[source_name]
            self.stdout.write(f"\n  Checking: {source_name} -- {contract['description']}")

            result = SourceResult(source_name)
            try:
                checker_fn(contract, result)
            except Exception as e:
                result.fail('unexpected', f"Unhandled exception: {e}")
                logger.exception(f"check_data_sources: unexpected error for {source_name}")

            for check in result.checks:
                icon = STATUS_ICONS[check['status']]
                self.stdout.write(f"    {icon}  [{check['name']}] {check['message']}")

            icon = STATUS_ICONS[result.status]
            self.stdout.write(f"\n  --> {source_name}: {icon} {result.status}")

            # GitHub Actions annotations for non-PASS
            gh_level = GH_LEVEL[result.status]
            if gh_level:
                for check in result.checks:
                    if check['status'] != PASS:
                        _emit_github_annotation(gh_level, source_name,
                                                f"[{check['name']}] {check['message']}")

            all_results.append(result)

            if result.status == FAIL:
                any_fail = True
                if fail_fast:
                    self.stdout.write(self.style.ERROR(
                        "\n  --fail-fast: stopping on first FAIL\n"
                    ))
                    sys.exit(1)

        # Summary table
        self.stdout.write(self.style.MIGRATE_HEADING("\n\n  ====== Summary ======"))
        for r in all_results:
            icon = STATUS_ICONS[r.status]
            self.stdout.write(f"  {icon}  {r.source_name:<20} {r.status}")

        if any_fail:
            self.stdout.write(self.style.ERROR(
                "\n  One or more data sources FAILED contract checks.\n"
                "  Review the details above and fix the affected adapter\n"
                "  before the pipeline writes incorrect data to the database.\n"
            ))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n  All data sources passed contract checks.\n"
            ))
