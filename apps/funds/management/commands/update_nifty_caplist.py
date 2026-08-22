"""
Management command: update_nifty_caplist

Fetches Nifty 50 + Nifty Next 50 + Nifty Midcap 150 constituent lists from
NSE India and writes data/nifty_caplist.json used by CapClassifier.

SEBI Classification:
  Nifty 50 + Nifty Next 50  = Top 100 stocks  = Large Cap
  Nifty Midcap 150           = 101–250 stocks  = Mid Cap
  Everything else                              = Small Cap (residual)

Run: python manage.py update_nifty_caplist
Schedule: monthly (before ingest_holdings)
"""
import json
import logging
import os
import time
from datetime import date

import requests
from django.core.management.base import BaseCommand

logger = logging.getLogger('mfanalysis')

# Management commands always run from the project root (where manage.py lives).
_CAPLIST_PATH = os.path.join(os.getcwd(), 'data', 'nifty_caplist.json')

# NSE India index constituent endpoints
_NSE_HEADERS = {
    'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept':          'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer':         'https://www.nseindia.com/',
    'Connection':      'keep-alive',
}
_INDICES = [
    ('NIFTY 50',        'large', 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050'),
    ('NIFTY NEXT 50',   'large', 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20NEXT%2050'),
    ('NIFTY MIDCAP 150','mid',   'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20MIDCAP%20150'),
]

# Fallback seed list (Nifty 50 constituents as of Aug 2025) to ensure command
# works even if NSE API is unreachable.
_SEED_LARGE = [
    "RELIANCE INDUSTRIES", "TATA CONSULTANCY SERVICES", "HDFC BANK",
    "INFOSYS", "ICICI BANK", "HINDUSTAN UNILEVER", "ITC", "STATE BANK OF INDIA",
    "BAJAJ FINANCE", "LARSEN AND TOUBRO", "AXIS BANK", "KOTAK MAHINDRA BANK",
    "BHARTI AIRTEL", "ASIAN PAINTS", "MARUTI SUZUKI INDIA", "HCL TECHNOLOGIES",
    "SUN PHARMACEUTICAL INDUSTRIES", "TITAN COMPANY", "WIPRO",
    "ULTRATECH CEMENT", "NESTLE INDIA", "POWER GRID CORPORATION OF INDIA",
    "NTPC", "MAHINDRA AND MAHINDRA", "TATA MOTORS", "OIL AND NATURAL GAS CORPORATION",
    "ADANI ENTERPRISES", "ADANI PORTS AND SPECIAL ECONOMIC ZONE",
    "TECH MAHINDRA", "BAJAJ AUTO", "BAJAJ FINSERV", "DR REDDYS LABORATORIES",
    "GRASIM INDUSTRIES", "EICHER MOTORS", "HERO MOTOCORP", "HINDALCO INDUSTRIES",
    "TATA STEEL", "JSW STEEL", "CIPLA", "DIVIS LABORATORIES", "BRITANNIA INDUSTRIES",
    "SHRIRAM FINANCE", "INDUSIND BANK", "SBI LIFE INSURANCE COMPANY",
    "HDFC LIFE INSURANCE COMPANY", "APOLLO HOSPITALS ENTERPRISE",
    "COAL INDIA", "TATA CONSUMER PRODUCTS", "BPCL", "LTIMINDTREE",
    # Nifty Next 50 (sample)
    "SIEMENS", "ABB INDIA", "INTERGLOBE AVIATION", "GODREJ CONSUMER PRODUCTS",
    "PIDILITE INDUSTRIES", "PI INDUSTRIES", "MUTHOOT FINANCE",
    "TORRENT PHARMACEUTICALS", "HAVELLS INDIA", "DABUR INDIA", "COLGATE PALMOLIVE INDIA",
    "AMBUJA CEMENTS", "ACC", "BERGER PAINTS INDIA", "CHOLMANDALAM INVESTMENT AND FINANCE",
    "DLF", "MOTHERSON SUMI WIRING INDIA", "MARICO", "GODREJ PROPERTIES",
    "UNITED SPIRITS", "TRENT", "NAUKRI", "BOSCH", "ZOMATO", "PAYTM",
    "LIC HOUSING FINANCE", "INDIAN OIL CORPORATION", "HINDUSTAN PETROLEUM CORPORATION",
    "VEDANTA", "BHARAT PETROLEUM CORPORATION",
]

_SEED_MID = [
    "PERSISTENT SYSTEMS", "COFORGE", "MPHASIS", "ORACLE FINANCIAL SERVICES",
    "TATA ELXSI", "ASTRAL", "CROMPTON GREAVES CONSUMER ELECTRICALS",
    "BALKRISHNA INDUSTRIES", "TUBE INVESTMENTS OF INDIA", "CARBORUNDUM UNIVERSAL",
    "VOLTAS", "ESCORTS KUBOTA", "SUNDRAM FASTENERS", "EXIDE INDUSTRIES",
    "AMARA RAJA ENERGY AND MOBILITY", "CUMMINS INDIA", "SCHAEFFLER INDIA",
    "TIMKEN INDIA", "AARTI INDUSTRIES", "DEEPAK NITRITE", "NAVIN FLUORINE INTERNATIONAL",
    "GALAXY SURFACTANTS", "FINE ORGANIC INDUSTRIES", "JUBILANT FOODWORKS",
    "WESTLIFE FOODWORLD", "DEVYANI INTERNATIONAL", "SAPPHIRE FOODS INDIA",
    "MAX HEALTHCARE INSTITUTE", "KRISHNA INSTITUTE OF MEDICAL SCIENCES",
    "METROPOLIS HEALTHCARE", "DR LAL PATHLABS", "THYROCARE TECHNOLOGIES",
    "LAURUS LABS", "ALEMBIC PHARMACEUTICALS", "ERIS LIFESCIENCES", "IPCA LABORATORIES",
    "GLAND PHARMA", "SYNGENE INTERNATIONAL", "PFIZER", "ABBOTT INDIA",
    "CITY UNION BANK", "KARUR VYSYA BANK", "SOUTH INDIAN BANK", "DCB BANK",
    "FEDERAL BANK", "EQUITAS SMALL FINANCE BANK", "AU SMALL FINANCE BANK",
    "CREDITACCESS GRAMEEN", "SPANDANA SPHOORTY FINANCIAL", "ADITYA BIRLA FASHION",
    "PAGE INDUSTRIES", "GO FASHION INDIA", "CAMPUS ACTIVEWEAR", "BATA INDIA",
    "RELAXO FOOTWEARS", "KAVERI SEED COMPANY", "RALLIS INDIA", "COROMANDEL INTERNATIONAL",
    "UPL", "SUMITOMO CHEMICAL INDIA", "PHOENIX MILLS", "PRESTIGE ESTATES PROJECTS",
    "OBEROI REALTY", "BRIGADE ENTERPRISES", "SOBHA", "KAJARIA CERAMICS",
    "CERA SANITARYWARE", "SUPRAJIT ENGINEERING", "MINDA INDUSTRIES",
    "SAMVARDHANA MOTHERSON INTERNATIONAL", "SONA BLW PRECISION FORGINGS",
    "GABRIEL INDIA", "GREAVES COTTON", "CRAFTSMAN AUTOMATION", "ISGEC HEAVY ENGINEERING",
    "BHARAT FORGE", "RAMKRISHNA FORGINGS", "INDIA GLYCOLS",
    "CENTURY TEXTILES AND INDUSTRIES", "RAYMOND", "ARVIND", "KPR MILL",
    "VARDHMAN TEXTILES", "NIIT TECHNOLOGIES", "HEXAWARE TECHNOLOGIES", "RATEGAIN TRAVEL",
    "ROUTE MOBILE", "TATA COMMUNICATIONS", "STERLITE TECHNOLOGIES", "TEJAS NETWORKS",
    "INTELLECT DESIGN ARENA", "ZENSAR TECHNOLOGIES", "BIRLASOFT", "CYIENT",
    "MASTEK", "KELLTON TECH SOLUTIONS", "TANLA PLATFORMS", "INDIAMART INTERMESH",
    "JUST DIAL", "AFFLE INDIA", "NAZARA TECHNOLOGIES", "DELTA CORP", "WONDERLA HOLIDAYS",
    "MAHINDRA HOLIDAYS AND RESORTS INDIA", "STERLING AND WILSON RENEWABLE ENERGY",
    "HITACHI ENERGY INDIA", "THERMAX", "KIRLOSKAR ELECTRIC", "TRIVENI TURBINE",
    "EIL", "NBCC INDIA", "IRCON INTERNATIONAL", "RITES",
]


class Command(BaseCommand):
    help = (
        'Fetch Nifty 50 + Next 50 + Midcap 150 constituents from NSE India '
        'and update data/nifty_caplist.json for CapClassifier.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--seed-only', action='store_true',
            help='Write seed data only (no NSE API calls). Useful for CI/offline.'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be written without saving.'
        )

    def handle(self, *args, **options):
        seed_only = options['seed_only']
        dry_run   = options['dry_run']

        stocks: dict[str, str] = {}   # name → 'large' | 'mid'

        if seed_only:
            self.stdout.write(self.style.WARNING('Using seed data only (--seed-only).'))
            for name in _SEED_LARGE:
                stocks[name] = 'large'
            for name in _SEED_MID:
                stocks[name] = 'mid'
        else:
            stocks = self._fetch_from_nse()

        total_large = sum(1 for v in stocks.values() if v == 'large')
        total_mid   = sum(1 for v in stocks.values() if v == 'mid')

        caplist = {
            'metadata': {
                'updated':     date.today().isoformat(),
                'large_count': total_large,
                'mid_count':   total_mid,
                'note': (
                    'Nifty 50 + Nifty Next 50 = Large (top 100). '
                    'Nifty Midcap 150 = Mid (101-250). '
                    'All other stocks = Small (SEBI residual rule).'
                ),
            },
            'stocks': stocks,
        }

        self.stdout.write(
            f"Cap list built: {total_large} large, {total_mid} mid, "
            f"{total_large + total_mid} total (small = all others)."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('--dry-run: Not saving.'))
            return

        os.makedirs(os.path.dirname(_CAPLIST_PATH), exist_ok=True)
        with open(_CAPLIST_PATH, 'w', encoding='utf-8') as fh:
            json.dump(caplist, fh, indent=2, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(f'Saved to {_CAPLIST_PATH}'))

        # Hot-reload the singleton classifier
        try:
            from apps.holdings.cap_classifier import get_classifier
            get_classifier().reload()
            self.stdout.write('CapClassifier singleton reloaded.')
        except Exception as exc:
            logger.warning('Could not reload CapClassifier singleton: %s', exc)

    def _fetch_from_nse(self) -> dict[str, str]:
        """Fetch constituent names from NSE API. Falls back to seed on error."""
        stocks: dict[str, str] = {}
        session = requests.Session()
        session.headers.update(_NSE_HEADERS)

        # Warm up cookie (NSE requires a browser-like session)
        try:
            session.get('https://www.nseindia.com/', timeout=10)
            time.sleep(1)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'NSE warm-up failed: {exc}. Using seed.'))
            for name in _SEED_LARGE:
                stocks[name] = 'large'
            for name in _SEED_MID:
                stocks[name] = 'mid'
            return stocks

        fetch_failed = False
        for index_name, cap, url in _INDICES:
            try:
                self.stdout.write(f'Fetching {index_name} ...')
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
                data  = resp.json()
                items = data.get('data', [])
                count = 0
                for item in items:
                    comp_name = str(
                        item.get('companyName') or item.get('meta', {}).get('companyName', '')
                    ).strip()
                    if comp_name and comp_name.upper() not in ('NIFTY 50', 'NIFTY MIDCAP 150'):
                        stocks[comp_name.upper()] = cap
                        count += 1
                self.stdout.write(f'  -> {count} stocks from {index_name}')
                time.sleep(1.5)   # polite delay between NSE calls
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'  Failed to fetch {index_name}: {exc}'))
                fetch_failed = True

        if fetch_failed or len(stocks) < 100:
            self.stdout.write(self.style.WARNING(
                f'Only {len(stocks)} stocks fetched from NSE. Merging with seed data.'
            ))
            # Merge seed: don't overwrite real data, just fill gaps
            for name in _SEED_LARGE:
                stocks.setdefault(name, 'large')
            for name in _SEED_MID:
                stocks.setdefault(name, 'mid')

        return stocks
