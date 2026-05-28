import logging
import datetime
from decimal import Decimal
import pandas as pd
import numpy as np
from scipy import optimize

from apps.portfolio.models import Transaction, Portfolio
from apps.funds.models import Scheme, NAVHistory
from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV

logger = logging.getLogger('mfanalysis')

def calculate_xirr(cash_flows):
    """
    Calculate XIRR (Extended Internal Rate of Return) given a list of tuples (date, amount).
    Amounts should be negative for cash outflows (investments) and positive for inflows (current value/redemptions).
    """
    if not cash_flows:
        return None
        
    df = pd.DataFrame(cash_flows, columns=['date', 'amount'])
    df['date'] = pd.to_datetime(df['date'])
    
    # Needs to be sorted by date
    df = df.sort_values('date')
    
    dates = df['date'].values
    amounts = df['amount'].values
    
    # Check if there are both positive and negative cash flows
    if np.all(amounts >= 0) or np.all(amounts <= 0):
        return None
        
    t0 = dates[0]
    years = (dates - t0).astype('timedelta64[D]').astype(int) / 365.0
    
    def npv(rate):
        return np.sum(amounts / ((1 + rate) ** years))
        
    try:
        xirr = optimize.newton(npv, 0.1)
        return xirr * 100 # Return as percentage
    except RuntimeError:
        return None

def calculate_portfolio_xirr(portfolio):
    """
    Calculates the overall XIRR for a portfolio.
    """
    transactions = portfolio.transactions.filter(scheme__isnull=False).select_related('scheme')
    
    # Group transactions by scheme to find current units
    from collections import defaultdict
    scheme_units = defaultdict(float)
    cash_flows = []
    
    for tx in transactions:
        amount = float(tx.amount)
        if tx.tx_type in ('BUY', 'SIP', 'SWITCH_IN', 'DIV_REINV'):
            cash_flows.append((tx.tx_date, -amount)) # Investment is outflow
            scheme_units[tx.scheme] += float(tx.units)
        elif tx.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'):
            cash_flows.append((tx.tx_date, amount)) # Redemption is inflow
            scheme_units[tx.scheme] -= float(tx.units)
        elif tx.tx_type == 'DIV_PAYOUT':
            cash_flows.append((tx.tx_date, amount))
            
    # Add current value as a positive cash flow
    today = datetime.date.today()
    total_current_value = 0
    for scheme, units in scheme_units.items():
        if units > 0:
            if scheme.nav_latest:
                total_current_value += units * float(scheme.nav_latest)
                
    if total_current_value > 0:
        cash_flows.append((today, total_current_value))
        
    return calculate_xirr(cash_flows)


def simulate_benchmark(portfolio, benchmark_ticker="^NSEI"):
    """
    Simulates investing the same cash flows into a benchmark index (e.g. NIFTY 50).
    Returns the simulated current value and XIRR.
    """
    transactions = portfolio.transactions.filter(scheme__isnull=False).order_by('tx_date')
    
    # Need to map the ticker to BenchmarkIndex
    index = BenchmarkIndex.objects.filter(yahoo_ticker=benchmark_ticker).first()
    if not index:
        # Fallback to the first one available if not found
        index = BenchmarkIndex.objects.first()
        if not index:
            return None, None
            
    # We will simulate "units" of the benchmark
    simulated_units = 0
    cash_flows = []
    
    for tx in transactions:
        # Find index value on or before the tx_date
        nav_record = BenchmarkNAV.objects.filter(index=index, date__lte=tx.tx_date).order_by('-date').first()
        if not nav_record:
            continue
            
        index_val = float(nav_record.close)
        amount = float(tx.amount)
        
        if tx.tx_type in ('BUY', 'SIP', 'SWITCH_IN', 'DIV_REINV'):
            simulated_units += amount / index_val
            cash_flows.append((tx.tx_date, -amount))
        elif tx.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'):
            simulated_units -= amount / index_val
            cash_flows.append((tx.tx_date, amount))
            
    if simulated_units <= 0:
        return 0, 0
        
    # Find latest index value
    latest_nav = BenchmarkNAV.objects.filter(index=index).order_by('-date').first()
    if not latest_nav:
        return 0, 0
        
    current_value = simulated_units * float(latest_nav.close)
    cash_flows.append((datetime.date.today(), current_value))
    
    simulated_xirr = calculate_xirr(cash_flows)
    
    return current_value, simulated_xirr

def get_portfolio_journey(portfolio):
    """
    Returns time-series data for the portfolio's total invested amount and current value.
    Uses weekly frequency to capture real market fluctuations, optimized with in-memory lookups.
    """
    import bisect
    transactions = list(portfolio.transactions.filter(scheme__isnull=False).order_by('tx_date'))
    if not transactions:
        return [], [], []

    start_date = transactions[0].tx_date
    end_date = datetime.date.today()
    
    # Use weekly frequency to show actual fluctuations based on NAV data
    journey_dates = pd.date_range(start=start_date, end=end_date, freq='W').date.tolist()
    # Always include today
    if journey_dates and journey_dates[-1] != end_date:
        journey_dates.append(end_date)
    if not journey_dates:
        journey_dates = [end_date]
        
    invested_series = []
    value_series = []
    
    schemes = list(Scheme.objects.filter(transaction__portfolio=portfolio).distinct())
    
    # Bulk load NAV history for each scheme in chronological order
    nav_cache = {}
    for scheme in schemes:
        nav_cache[scheme.id] = list(
            NAVHistory.objects.filter(scheme=scheme)
            .order_by('date')
            .values_list('date', 'nav')
        )

    for d in journey_dates:
        invested = 0.0
        current_val = 0.0
        
        for scheme in schemes:
            # Filter transactions on or before d in memory
            txs = [t for t in transactions if t.scheme_id == scheme.id and t.tx_date <= d]
            if not txs:
                continue
                
            scheme_invested = sum(float(t.amount) for t in txs if t.tx_type in ('BUY', 'SIP', 'SWITCH_IN'))
            scheme_redeemed = sum(float(t.amount) for t in txs if t.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'))
            units = sum(float(t.units) for t in txs if t.tx_type in ('BUY', 'SIP', 'SWITCH_IN'))
            units -= sum(float(t.units) for t in txs if t.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'))
            
            invested += (scheme_invested - scheme_redeemed)
            
            if units > 0:
                # Find NAV on or before d using binary search in memory
                navs = nav_cache.get(scheme.id, [])
                if navs:
                    dates_list = [item[0] for item in navs]
                    idx = bisect.bisect_right(dates_list, d)
                    if idx > 0:
                        nav_val = float(navs[idx - 1][1])
                        current_val += units * nav_val
                    
        invested_series.append(invested)
        value_series.append(current_val)
        
    return [d.strftime('%Y-%m-%d') for d in journey_dates], invested_series, value_series

def calculate_diversification_score(portfolio):
    """
    Calculates a diversification score (0-100) based on asset allocation and number of funds.
    Also provides a brief commentary.
    """
    schemes = Scheme.objects.filter(transaction__portfolio=portfolio).distinct()
    if not schemes.exists():
        return 0, "No funds in portfolio"
        
    num_funds = schemes.count()
    
    score = 50 # Base score
    
    if num_funds < 2:
        score -= 20
        comment = "Under-diversified: Too few funds."
    elif num_funds > 15:
        score -= 10
        comment = "Over-diversified: Too many funds may lead to index-hugging."
    else:
        score += 20
        comment = "Good number of funds."
        
    # Check AMC diversification
    amcs = schemes.values('fund_house').distinct().count()
    if amcs == 1 and num_funds > 1:
        score -= 10
        comment += " All funds are from the same AMC, posing concentration risk."
    else:
        score += 10
        
    # Further sophisticated correlation matrix analysis can be added here
    return min(100, max(0, score)), comment

def calculate_portfolio_ratios(portfolio):
    """
    Computes weighted average of standard deviation, beta, and Sharpe ratio.
    """
    transactions = portfolio.transactions.filter(scheme__isnull=False).select_related('scheme')
    
    # Get current value for each scheme to calculate weights
    from collections import defaultdict
    scheme_values = defaultdict(float)
    total_value = 0
    
    for tx in transactions:
        if tx.tx_type in ('BUY', 'SIP', 'SWITCH_IN', 'DIV_REINV'):
            scheme_values[tx.scheme] += float(tx.units)
        elif tx.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'):
            scheme_values[tx.scheme] -= float(tx.units)
            
    for scheme, units in list(scheme_values.items()):
        if units > 0 and scheme.nav_latest:
            val = units * float(scheme.nav_latest)
            scheme_values[scheme] = val
            total_value += val
        else:
            del scheme_values[scheme]
            
    if total_value <= 0:
        return {}
        
    # Calculate weighted metrics based on captnemo SchemeMeta runtime data
    weighted_volatility = 0
    
    for scheme, val in scheme_values.items():
        weight = val / total_value
        if hasattr(scheme, 'meta') and scheme.meta.volatility:
            weighted_volatility += float(scheme.meta.volatility) * weight
            
    return {
        'weighted_volatility': round(weighted_volatility, 2) if weighted_volatility else None,
        # Sharpe, Beta, Alpha would be fetched from meta or computed similarly
    }

def get_default_blended_benchmark_weights(portfolio):
    """
    Determines the default blended benchmark for the portfolio.
    It equal-weights the benchmarks of the funds present in the portfolio.
    If a fund's benchmark index is missing or has no NAV data, NIFTY 50 is used.
    """
    from collections import defaultdict
    from apps.benchmarks.models import BenchmarkIndex
    from apps.benchmarks.registry import benchmark_for
    
    transactions = portfolio.transactions.filter(scheme__isnull=False).select_related('scheme')
    schemes = list({tx.scheme for tx in transactions if tx.scheme})
    
    if not schemes:
        return {'NIFTY 50': 1.0}
        
    weights = defaultdict(float)
    equal_weight = 1.0 / len(schemes)
    
    for scheme in schemes:
        bm_name = benchmark_for(scheme.scheme_category, scheme.scheme_name)
        try:
            index = BenchmarkIndex.objects.get(name=bm_name)
            if index.nav_history.exists():
                weights[bm_name] += equal_weight
            else:
                weights['NIFTY 50'] += equal_weight
        except BenchmarkIndex.DoesNotExist:
            weights['NIFTY 50'] += equal_weight
            
    return dict(weights)

def simulate_custom_benchmark(portfolio, weights_dict):
    """
    Simulates investing portfolio cash flows into a blended index defined by weights_dict.
    Returns (current_value, xirr, journey_dates, journey_values)
    """
    from collections import defaultdict
    import bisect
    from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV
    
    transactions = list(portfolio.transactions.filter(scheme__isnull=False).order_by('tx_date'))
    
    if not transactions or not weights_dict:
        return 0, 0, [], []
        
    start_date = transactions[0].tx_date
    end_date = datetime.date.today()
    
    journey_dates = pd.date_range(start=start_date, end=end_date, freq='W').date.tolist()
    if journey_dates and journey_dates[-1] != end_date:
        journey_dates.append(end_date)
    if not journey_dates:
        journey_dates = [end_date]
        
    indices = {}
    nav_cache = {}
    for name, weight in weights_dict.items():
        try:
            index = BenchmarkIndex.objects.get(name=name)
            indices[index] = weight
            nav_cache[index.id] = list(
                BenchmarkNAV.objects.filter(index=index)
                .order_by('date')
                .values_list('date', 'close')
            )
        except BenchmarkIndex.DoesNotExist:
            continue
            
    if not indices:
        return 0, 0, [], []
        
    simulated_units = defaultdict(float)
    cash_flows = []
    
    journey_values = []
    
    for d in journey_dates:
        d_units = defaultdict(float)
        txs_to_d = [t for t in transactions if t.tx_date <= d]
        for tx in txs_to_d:
            amount = float(tx.amount)
            for index, weight in indices.items():
                navs = nav_cache.get(index.id, [])
                if not navs: continue
                dates_list = [item[0] for item in navs]
                idx = bisect.bisect_right(dates_list, tx.tx_date)
                if idx > 0:
                    index_val = float(navs[idx - 1][1])
                    part_amount = amount * weight
                    if tx.tx_type in ('BUY', 'SIP', 'SWITCH_IN', 'DIV_REINV'):
                        d_units[index.id] += part_amount / index_val
                    elif tx.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'):
                        d_units[index.id] -= part_amount / index_val
                        
        d_val = 0.0
        for index, weight in indices.items():
            if d_units[index.id] > 0:
                navs = nav_cache.get(index.id, [])
                dates_list = [item[0] for item in navs]
                idx = bisect.bisect_right(dates_list, d)
                if idx > 0:
                    index_val = float(navs[idx - 1][1])
                    d_val += d_units[index.id] * index_val
        journey_values.append(d_val)
        
    for tx in transactions:
        amount = float(tx.amount)
        if tx.tx_type in ('BUY', 'SIP', 'SWITCH_IN', 'DIV_REINV'):
            cash_flows.append((tx.tx_date, -amount))
        elif tx.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT', 'DIV_PAYOUT'):
            cash_flows.append((tx.tx_date, amount))
        
    current_value = journey_values[-1] if journey_values else 0
    if current_value > 0:
        cash_flows.append((end_date, current_value))
        
    xirr = calculate_xirr(cash_flows)
    
    return current_value, xirr, [d.strftime('%Y-%m-%d') for d in journey_dates], journey_values

def compute_advanced_risk_metrics(portfolio_journey, benchmark_journey, risk_free_rate=0.06):
    if len(portfolio_journey) < 2 or len(benchmark_journey) < 2:
        return {}
        
    port_series = pd.Series(portfolio_journey)
    bench_series = pd.Series(benchmark_journey)
    
    port_returns = port_series.pct_change().dropna()
    bench_returns = bench_series.pct_change().dropna()
    
    if len(port_returns) < 2:
        return {}
        
    annualization_factor = 52
    
    port_vol = port_returns.std() * np.sqrt(annualization_factor)
    bench_vol = bench_returns.std() * np.sqrt(annualization_factor)
    
    cov_matrix = np.cov(port_returns, bench_returns)
    if cov_matrix.shape == (2, 2):
        cov = cov_matrix[0][1]
    else:
        cov = 0
    var = np.var(bench_returns)
    beta = cov / var if var > 0 else 1.0
    
    port_annual_return = (port_series.iloc[-1] / port_series.iloc[0]) ** (annualization_factor / len(port_returns)) - 1 if port_series.iloc[0] > 0 else 0
    bench_annual_return = (bench_series.iloc[-1] / bench_series.iloc[0]) ** (annualization_factor / len(bench_returns)) - 1 if bench_series.iloc[0] > 0 else 0
    alpha = port_annual_return - (risk_free_rate + beta * (bench_annual_return - risk_free_rate))
    
    excess_returns = port_returns - (risk_free_rate / annualization_factor)
    sharpe = np.mean(excess_returns) / port_returns.std() * np.sqrt(annualization_factor) if port_returns.std() > 0 else 0
    
    downside_returns = port_returns[port_returns < 0]
    downside_std = downside_returns.std() * np.sqrt(annualization_factor)
    sortino = np.mean(excess_returns) / (downside_std / np.sqrt(annualization_factor)) * np.sqrt(annualization_factor) if downside_std > 0 else 0
    
    up_periods = bench_returns > 0
    down_periods = bench_returns < 0
    
    up_capture = 0
    down_capture = 0
    
    if up_periods.sum() > 0:
        port_up_ret = np.prod(1 + port_returns[up_periods]) - 1
        bench_up_ret = np.prod(1 + bench_returns[up_periods]) - 1
        up_capture = (port_up_ret / bench_up_ret * 100) if bench_up_ret > 0 else 0
        
    if down_periods.sum() > 0:
        port_down_ret = np.prod(1 + port_returns[down_periods]) - 1
        bench_down_ret = np.prod(1 + bench_returns[down_periods]) - 1
        down_capture = (port_down_ret / bench_down_ret * 100) if bench_down_ret < 0 else 0
        
    return {
        "volatility": round(port_vol * 100, 2) if port_vol else None,
        "benchmark_volatility": round(bench_vol * 100, 2) if bench_vol else None,
        "beta": round(beta, 2),
        "alpha": round(alpha * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "up_capture": round(up_capture, 2),
        "down_capture": round(down_capture, 2)
    }
