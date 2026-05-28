import os
import sys
import django
import logging

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from datetime import date
from django.utils import timezone
from apps.portfolio.models import Portfolio
from apps.holdings.models import Holding
from adapters.registry import ADAPTERS

logger = logging.getLogger('mfanalysis')

def main():
    portfolio = Portfolio.objects.get(id=1)
    schemes = {tx.scheme for tx in portfolio.transactions.all() if tx.scheme}
    
    adapter = ADAPTERS['mstarpy']()
    
    today = timezone.localdate()
    as_of_month = date(today.year, today.month, 1)

    for scheme in schemes:
        print(f"\nProcessing {scheme.scheme_name}...")
        if not scheme.morningstar_id:
            # Try to search for it
            search_term = scheme.scheme_name.replace(" - Growth Option - Direct Plan", " Direct Growth")
            search_term = search_term.replace("- Direct Plan Growth", "Direct Growth")
            search_term = search_term.replace("- Direct Plan - Growth", "Direct Growth")
            
            # Simple heuristic
            search_term = " ".join(search_term.split("-")[0].strip().split()[:5]) + " Direct Growth"
            
            print(f"  Searching Morningstar for '{search_term}'...")
            results = adapter.search_fund(search_term)
            if results:
                ms_id = results[0].get('securityID') or results[0].get('SecId')
                name_val = results[0].get('name', {}).get('value') if isinstance(results[0].get('name'), dict) else results[0].get('Name', '')
                print(f"  Found ID: {ms_id} ({name_val})")
                scheme.morningstar_id = ms_id
                scheme.save()
            else:
                print(f"  Could not find Morningstar ID for {scheme.scheme_name}")
                continue
                
        # Fetch holdings
        if scheme.morningstar_id:
            print(f"  Fetching holdings for {scheme.morningstar_id}...")
            holdings_df = adapter.fetch_holdings(scheme.morningstar_id)
            if holdings_df is not None and not holdings_df.empty:
                print(f"  Found {len(holdings_df)} holdings. Saving to DB...")
                # Clear old holdings for this month
                Holding.objects.filter(scheme=scheme, as_of_month=as_of_month).delete()
                
                new_holdings = []
                for _, row in holdings_df.iterrows():
                    new_holdings.append(Holding(
                        scheme=scheme,
                        as_of_month=as_of_month,
                        security_name=row.get('securityName', 'Unknown')[:300],
                        isin=row.get('isin', '')[:15] if row.get('isin') else '',
                        ticker=row.get('ticker', '')[:20] if row.get('ticker') else '',
                        weight_pct=row.get('weighting', 0) or 0,
                        sector=row.get('sector', '')[:100] if row.get('sector') else '',
                        source='mstarpy'
                    ))
                Holding.objects.bulk_create(new_holdings)
                print(f"  Saved {len(new_holdings)} holdings successfully.")
            else:
                print("  Failed to fetch holdings or empty dataframe returned.")

if __name__ == '__main__':
    main()
