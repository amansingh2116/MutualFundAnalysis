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

def main():
    portfolio = Portfolio.objects.get(id=1)
    schemes = list({tx.scheme for tx in portfolio.transactions.all() if tx.scheme})
    
    today = timezone.localdate()
    as_of_month = date(today.year, today.month, 1)

    print(f"Creating mock holdings for {len(schemes)} schemes...")
    
    # Common stocks to create overlaps
    stocks = [
        ('HDFC Bank Ltd', 8.5),
        ('Reliance Industries Ltd', 7.2),
        ('ICICI Bank Ltd', 6.0),
        ('Infosys Ltd', 5.1),
        ('ITC Ltd', 4.3),
        ('Larsen & Toubro Ltd', 3.8),
        ('TCS Ltd', 3.2),
        ('Bharti Airtel Ltd', 2.9),
        ('Axis Bank Ltd', 2.5),
        ('State Bank of India', 2.1)
    ]
    
    # We will give scheme 1 stocks 0-6 (7 stocks)
    # Scheme 2 stocks 3-9 (7 stocks)
    # Scheme 3 stocks 1, 5, 8 (3 stocks) + some unique ones
    
    allocations = [
        (0, 7),
        (3, 10),
        (1, 9, 2) # step of 2
    ]
    
    for i, scheme in enumerate(schemes):
        Holding.objects.filter(scheme=scheme).delete()
        
        new_holdings = []
        
        if i == 0:
            subset = stocks[0:7]
        elif i == 1:
            subset = stocks[3:10]
        else:
            subset = stocks[1:10:2]
            
        # Add some unique stocks so total is 100%
        subset = list(subset)
        subset.append((f'Unique Stock {i}A', 25.0))
        subset.append((f'Unique Stock {i}B', 20.0))
        
        # normalize to 100%
        total_weight = sum(w for _, w in subset)
        
        for name, weight in subset:
            norm_weight = (weight / total_weight) * 100
            new_holdings.append(Holding(
                scheme=scheme,
                as_of_month=as_of_month,
                security_name=name,
                weight_pct=norm_weight,
                sector='Financial Services' if 'Bank' in name else 'Technology',
                source='mock'
            ))
            
        Holding.objects.bulk_create(new_holdings)
        print(f"Created {len(new_holdings)} holdings for {scheme.scheme_name}")

if __name__ == '__main__':
    main()
