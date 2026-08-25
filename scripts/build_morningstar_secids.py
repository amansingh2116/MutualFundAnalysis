"""
Script to build data/morningstar_secids.json (mapping ISIN -> Morningstar SecId).
This static mapping is checked into git so GitHub Actions and live runtime
can instantly resolve Morningstar SecIds in O(1) time without Selenium/Chrome.
"""
import os, sys, json, time, django

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from apps.funds.models import Scheme
from mstarpy.search import MorningstarSession

print("=== Starting Morningstar Universe Ingest ===", flush=True)
session = MorningstarSession()

# 1. Load existing mappings if file exists
out_path = os.path.join(os.getcwd(), 'data', 'morningstar_secids.json')
mapping = {}
if os.path.exists(out_path):
    try:
        with open(out_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        print(f"Loaded {len(mapping)} existing mappings from {out_path}", flush=True)
    except Exception:
        mapping = {}

def add_items(results):
    added = 0
    if not isinstance(results, list):
        return 0
    for item in results:
        fields = item.get('fields', {})
        meta = item.get('meta', {})
        isin = fields.get('isin', {}).get('value') if isinstance(fields.get('isin'), dict) else fields.get('isin')
        sec_id = meta.get('securityID') or meta.get('SecId') or meta.get('secId') or meta.get('performanceID')
        if isin and sec_id:
            isin_clean = str(isin).strip().upper()
            sec_clean = str(sec_id).strip()
            if isin_clean and sec_clean and isin_clean.startswith('INF'):
                if isin_clean not in mapping or mapping[isin_clean] != sec_clean:
                    mapping[isin_clean] = sec_clean
                    added += 1
    return added

# 2. Query by unique AMC names from our database
amcs = sorted(list(set(Scheme.objects.values_list('fund_house', flat=True).distinct())))
amcs = [a for a in amcs if a and a.strip()]
print(f"\nQuerying universe by {len(amcs)} AMC names...", flush=True)

for idx, amc in enumerate(amcs, start=1):
    # Strip suffixes like Mutual Fund, Asset Management, etc.
    term = amc.split(' Mutual Fund')[0].split(' Asset Management')[0].split(' Investment')[0].strip()
    if not term:
        term = amc
    print(f"[{idx}/{len(amcs)}] AMC: '{term}'...", flush=True)
    try:
        for page in range(1, 6):
            res = session.screener_universe(term, field=['isin', 'name'], pageSize=250, page=page)
            if not res:
                break
            added = add_items(res)
            print(f"  Page {page}: {len(res)} items, +{added} new (total mapped: {len(mapping)})", flush=True)
            if len(res) < 250:
                break
            time.sleep(0.2)
    except Exception as e:
        print(f"  Error for {term}: {e}", flush=True)
    time.sleep(0.2)

# 3. Save progress
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(mapping, f, indent=2, sort_keys=True)
print(f"\nSaved {len(mapping)} mappings to {out_path}", flush=True)

# 4. Check coverage against database schemes
schemes = list(Scheme.objects.filter(is_active=True).exclude(isin_growth='').exclude(isin_growth__isnull=True))
total_schemes = len(schemes)
matched = 0
unmatched_schemes = []

for s in schemes:
    isin = s.isin_growth.strip().upper()
    if isin in mapping:
        matched += 1
        if s.morningstar_id != mapping[isin]:
            s.morningstar_id = mapping[isin]
            s.save(update_fields=['morningstar_id'])
    else:
        unmatched_schemes.append(s)

print(f"Database coverage: {matched} / {total_schemes} ({matched / total_schemes * 100:.1f}%)", flush=True)

# 5. Targeted lookup for remaining unmatched schemes
if unmatched_schemes:
    print(f"\nAttempting targeted lookup for {len(unmatched_schemes)} remaining unmatched schemes...", flush=True)
    for idx, s in enumerate(unmatched_schemes, start=1):
        isin = s.isin_growth.strip().upper()
        try:
            res = session.screener_universe(isin, field=['isin', 'name'], pageSize=5)
            if isinstance(res, list):
                for item in res:
                    meta = item.get('meta', {})
                    sid = meta.get('securityID') or meta.get('SecId') or meta.get('secId') or meta.get('performanceID')
                    if sid:
                        mapping[isin] = str(sid).strip()
                        s.morningstar_id = str(sid).strip()
                        s.save(update_fields=['morningstar_id'])
                        print(f"  [{idx}/{len(unmatched_schemes)}] {s.amfi_code} ({isin}) -> {sid}", flush=True)
                        break
        except Exception:
            pass
        time.sleep(0.15)

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, sort_keys=True)

print(f"\n=== Build Complete: Final Mapping Count = {len(mapping)} ===", flush=True)
