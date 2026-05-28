"""
apps/portfolio/services/forecasting.py — Portfolio forecasting and TA engine
========================================================================
Implements:
1. Daily portfolio history reconstruction.
2. Technical Analysis indicators (RSI, MACD, Moving Averages, Bollinger Bands).
3. Correlated Monte Carlo simulations using Cholesky covariance matrix.
4. ARIMA time series forecasting.
5. Machine Learning autoregressive forecasting (Ridge, Random Forest).
"""
import datetime
import logging
import bisect
import numpy as np
import pandas as pd
from decimal import Decimal

from apps.funds.models import Scheme, NAVHistory
from apps.portfolio.models import Transaction

logger = logging.getLogger('mfanalysis')

def get_daily_portfolio_history(portfolio):
    """
    Reconstructs daily portfolio valuation history from transactions.
    Returns a pandas DataFrame with columns: ['date', 'invested', 'current_value']
    """
    transactions = list(portfolio.transactions.filter(scheme__isnull=False).order_by('tx_date'))
    if not transactions:
        return pd.DataFrame(columns=['date', 'invested', 'current_value'])

    start_date = transactions[0].tx_date
    end_date = datetime.date.today()
    
    # Generate daily date range
    dates = pd.date_range(start=start_date, end=end_date, freq='D').date.tolist()
    
    schemes = list(Scheme.objects.filter(transaction__portfolio=portfolio).distinct())
    
    # Bulk load NAV histories to cache
    nav_cache = {}
    for scheme in schemes:
        nav_cache[scheme.id] = list(
            NAVHistory.objects.filter(scheme=scheme)
            .order_by('date')
            .values_list('date', 'nav')
        )

    history = []
    for d in dates:
        invested = 0.0
        current_val = 0.0
        
        for scheme in schemes:
            txs = [t for t in transactions if t.scheme_id == scheme.id and t.tx_date <= d]
            if not txs:
                continue
                
            scheme_invested = sum(float(t.amount) for t in txs if t.tx_type in ('BUY', 'SIP', 'SWITCH_IN'))
            scheme_redeemed = sum(float(t.amount) for t in txs if t.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'))
            units = sum(float(t.units) for t in txs if t.tx_type in ('BUY', 'SIP', 'SWITCH_IN'))
            units -= sum(float(t.units) for t in txs if t.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'))
            
            invested += (scheme_invested - scheme_redeemed)
            
            if units > 0:
                navs = nav_cache.get(scheme.id, [])
                if navs:
                    dates_list = [item[0] for item in navs]
                    idx = bisect.bisect_right(dates_list, d)
                    if idx > 0:
                        nav_val = float(navs[idx - 1][1])
                        current_val += units * nav_val
        
        history.append({
            'date': d,
            'invested': invested,
            'current_value': current_val if current_val > 0 else invested
        })
        
    return pd.DataFrame(history)


def calculate_ta_indicators(portfolio):
    """
    Computes SMA, RSI, MACD, and Bollinger Bands on the portfolio's aggregate history.
    """
    df = get_daily_portfolio_history(portfolio)
    if df.empty or len(df) < 5:
        return {'consensus': 'NOT ENOUGH DATA'}
        
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    # 1. Moving Averages
    df['sma50'] = df['current_value'].rolling(window=min(50, len(df))).mean()
    df['sma200'] = df['current_value'].rolling(window=min(200, len(df))).mean()
    
    # 2. Bollinger Bands
    window_bb = min(20, len(df))
    df['bb_mid'] = df['current_value'].rolling(window=window_bb).mean()
    df['bb_std'] = df['current_value'].rolling(window=window_bb).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std'].fillna(0)
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std'].fillna(0)
    
    # 3. RSI (14-day)
    delta = df['current_value'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(14, len(df))).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(14, len(df))).mean()
    rs = gain / (loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 4. MACD (12, 26, 9)
    df['ema12'] = df['current_value'].ewm(span=min(12, len(df)), adjust=False).mean()
    df['ema26'] = df['current_value'].ewm(span=min(26, len(df)), adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['signal'] = df['macd'].ewm(span=min(9, len(df)), adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']
    
    latest = df.iloc[-1]
    
    # Consensus Trading Signals Logic
    votes = []
    
    # SMA Crossover
    if not pd.isna(latest['sma50']) and not pd.isna(latest['sma200']):
        if latest['sma50'] > latest['sma200']:
            votes.append('BUY')
        else:
            votes.append('SELL')
            
    # RSI Indicators
    rsi_val = latest['rsi']
    if not pd.isna(rsi_val):
        if rsi_val > 70:
            votes.append('SELL')  # Overbought
        elif rsi_val < 30:
            votes.append('BUY')   # Oversold
        else:
            votes.append('HOLD')
            
    # MACD Crossover
    if not pd.isna(latest['macd']) and not pd.isna(latest['signal']):
        if latest['macd'] > latest['signal']:
            votes.append('BUY')
        else:
            votes.append('SELL')
            
    # Bollinger Bands Proximity
    if not pd.isna(latest['bb_upper']) and not pd.isna(latest['bb_lower']):
        price = latest['current_value']
        if price > latest['bb_upper']:
            votes.append('SELL')
        elif price < latest['bb_lower']:
            votes.append('BUY')
        else:
            votes.append('HOLD')
            
    # Compile Consensus
    buys = votes.count('BUY')
    sells = votes.count('SELL')
    holds = votes.count('HOLD')
    
    if buys > sells and buys >= holds:
        consensus = 'BUY' if buys <= 2 else 'STRONG BUY'
    elif sells > buys and sells >= holds:
        consensus = 'SELL' if sells <= 2 else 'STRONG SELL'
    else:
        consensus = 'HOLD'
        
    return {
        'current_value': round(latest['current_value'], 2),
        'sma50': round(latest['sma50'], 2) if not pd.isna(latest['sma50']) else None,
        'sma200': round(latest['sma200'], 2) if not pd.isna(latest['sma200']) else None,
        'rsi': round(rsi_val, 1) if not pd.isna(rsi_val) else None,
        'macd': round(latest['macd'], 2) if not pd.isna(latest['macd']) else None,
        'macd_signal': round(latest['signal'], 2) if not pd.isna(latest['signal']) else None,
        'bb_upper': round(latest['bb_upper'], 2) if not pd.isna(latest['bb_upper']) else None,
        'bb_lower': round(latest['bb_lower'], 2) if not pd.isna(latest['bb_lower']) else None,
        'consensus': consensus,
        'votes_buy': buys,
        'votes_sell': sells,
        'votes_hold': holds
    }


def simulate_monte_carlo(portfolio, horizon_days=365, simulations_count=250, vol_adjustment=0.0):
    """
    Simulates portfolio price trajectories over horizon_days using Geometric Brownian Motion.
    Incorporates historical fund covariance correlations and user volatility adjustments.
    """
    schemes = list(Scheme.objects.filter(transaction__portfolio=portfolio).distinct())
    if not schemes:
        return None

    # 1. Fetch daily returns for all assets to compute correlations
    nav_df_list = []
    lookback = datetime.date.today() - datetime.timedelta(days=730)  # 2 years historical return calculations
    
    for scheme in schemes:
        navs = NAVHistory.objects.filter(scheme=scheme, date__gte=lookback).order_by('date').values('date', 'nav')
        if navs.exists():
            s_df = pd.DataFrame(navs)
            s_df['date'] = pd.to_datetime(s_df['date'])
            col_name = f'nav_{scheme.id}'
            s_df.rename(columns={'nav': col_name}, inplace=True)
            s_df[col_name] = s_df[col_name].astype(float)
            nav_df_list.append(s_df)

    if not nav_df_list:
        return None
        
    merged_df = nav_df_list[0]
    for s_df in nav_df_list[1:]:
        merged_df = pd.merge(merged_df, s_df, on='date', how='outer')
        
    merged_df = merged_df.sort_values('date').ffill().bfill()
    merged_df.set_index('date', inplace=True)
    
    returns_df = merged_df.pct_change().dropna()
    if returns_df.empty:
        return None

    # 2. Compute parameters: Mean Vector & Covariance Matrix
    mean_returns = returns_df.mean().values
    cov_matrix = returns_df.cov().values
    
    # Adjust covariance scale based on user volatility parameter
    scale = (1.0 + float(vol_adjustment))
    cov_matrix = cov_matrix * (scale ** 2)
    stds = np.sqrt(np.diag(cov_matrix))

    # Cholesky decomposition for correlated normal draws
    use_correlation = False
    try:
        L = np.linalg.cholesky(cov_matrix)
        use_correlation = True
    except np.linalg.LinAlgError:
        try:
            # Regularize diagonal
            reg_cov = cov_matrix + np.eye(cov_matrix.shape[0]) * 1e-6
            L = np.linalg.cholesky(reg_cov)
            use_correlation = True
        except np.linalg.LinAlgError:
            # Fall back to independent simulations
            pass

    # 3. Compile current holding units
    holdings = []
    for scheme in schemes:
        txs = Transaction.objects.filter(portfolio=portfolio, scheme=scheme)
        units = sum(float(t.units) for t in txs if t.tx_type in ('BUY', 'SIP', 'SWITCH_IN'))
        units -= sum(float(t.units) for t in txs if t.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'))
        if units > 0:
            latest_nav = float(scheme.nav_latest) if scheme.nav_latest else 10.0
            holdings.append({
                'id': scheme.id,
                'units': units,
                'latest_nav': latest_nav
            })

    if not holdings:
        return None

    start_val = sum(h['units'] * h['latest_nav'] for h in holdings)
    num_schemes = len(holdings)
    
    # Setup Monte Carlo grid: (Simulations, Horizon + 1)
    paths = np.zeros((simulations_count, horizon_days + 1))
    paths[:, 0] = start_val
    
    # Daily normal random shocks
    Z = np.random.normal(0, 1, size=(simulations_count, num_schemes, horizon_days))
    
    if use_correlation:
        shocks = np.einsum('ij,sjt->sit', L, Z)
    else:
        shocks = Z * stds[:, np.newaxis, np.newaxis]
        
    drifts = mean_returns - 0.5 * (stds ** 2)
    growth = np.exp(drifts[np.newaxis, :, np.newaxis] + shocks)

    # Project NAV trajectories and sum portfolio aggregate
    for s in range(simulations_count):
        scheme_navs = np.zeros((num_schemes, horizon_days + 1))
        for i, h in enumerate(holdings):
            scheme_navs[i, 0] = h['latest_nav']
            scheme_navs[i, 1:] = h['latest_nav'] * np.cumprod(growth[s, i, :])
        
        portfolio_path = np.zeros(horizon_days + 1)
        for i, h in enumerate(holdings):
            portfolio_path += h['units'] * scheme_navs[i]
        paths[s] = portfolio_path

    # Extract percentiles
    p10 = np.percentile(paths, 10, axis=0)
    p50 = np.percentile(paths, 50, axis=0)
    p90 = np.percentile(paths, 90, axis=0)
    
    future_dates = [datetime.date.today() + datetime.timedelta(days=i) for i in range(horizon_days + 1)]
    
    return {
        'dates': [d.strftime('%Y-%m-%d') for d in future_dates],
        'p10': p10.tolist(),
        'p50': p50.tolist(),
        'p90': p90.tolist(),
        'final_values': paths[:, -1].tolist()
    }


def forecast_arima(portfolio, horizon_days=365, p=1, d=1, q=1):
    """
    Fits an ARIMA model to the daily aggregate portfolio values and projects point predictions.
    """
    df = get_daily_portfolio_history(portfolio)
    if df.empty or len(df) < 10:
        return None
        
    series = df['current_value'].values
    
    try:
        from statsmodels.tsa.arima.model import ARIMA
        model = ARIMA(series, order=(p, d, q))
        res = model.fit()
        forecast_res = res.get_forecast(steps=horizon_days)
        
        mean = forecast_res.predicted_mean
        conf = forecast_res.conf_int(alpha=0.1) # 90% confidence
        lower = conf[:, 0]
        upper = conf[:, 1]
    except Exception as e:
        logger.warning(f"ARIMA fitting failed: {e}. Falling back to linear trend.")
        # Fallback: simple trend line projection
        t = np.arange(len(series))
        slope, intercept = np.polyfit(t, series, 1)
        
        future_t = np.arange(len(series), len(series) + horizon_days)
        mean = slope * future_t + intercept
        std = np.std(series - (slope * t + intercept)) if len(series) > 2 else 10.0
        
        lower = mean - 1.645 * std * np.sqrt(np.arange(1, horizon_days + 1))
        upper = mean + 1.645 * std * np.sqrt(np.arange(1, horizon_days + 1))

    # Replace negatives with 0
    mean = np.clip(mean, 0, None)
    lower = np.clip(lower, 0, None)
    upper = np.clip(upper, 0, None)
    
    # Prepend starting values
    start_val = series[-1]
    mean = np.insert(mean, 0, start_val)
    lower = np.insert(lower, 0, start_val)
    upper = np.insert(upper, 0, start_val)
    
    future_dates = [datetime.date.today() + datetime.timedelta(days=i) for i in range(horizon_days + 1)]
    
    return {
        'dates': [d.strftime('%Y-%m-%d') for d in future_dates],
        'p10': lower.tolist(),
        'p50': mean.tolist(),
        'p90': upper.tolist(),
        'final_values': [mean[-1]]
    }


def forecast_machine_learning(portfolio, horizon_days=365, model_name='RIDGE', lags=10):
    """
    Fits Ridge Regression or Random Forest model to recursive time lags and projects paths.
    """
    df = get_daily_portfolio_history(portfolio)
    if df.empty or len(df) < (lags + 5):
        return None
        
    series = df['current_value'].values
    N = len(series)
    
    # Construct lag features
    X = []
    y = []
    for t in range(lags, N):
        row = [series[t - i] for i in range(1, lags + 1)]
        row.append(t)  # Add time index trend feature
        X.append(row)
        y.append(series[t])
        
    X = np.array(X)
    y = np.array(y)
    
    if model_name.upper() == 'RANDOM_FOREST':
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=50, random_state=42)
    else:
        from sklearn.linear_model import Ridge
        model = Ridge(alpha=1.0)
        
    try:
        model.fit(X, y)
        
        # Calculate standard deviation of residuals for confidence bands
        residuals = y - model.predict(X)
        resid_std = np.std(residuals) if len(residuals) > 1 else 10.0
    except Exception as e:
        logger.error(f"ML fitting failed: {e}")
        return None
        
    # Autoregressive recursive projection
    predictions = []
    lower_bound = []
    upper_bound = []
    
    # Seed features from last window
    curr_features = [series[N - i] for i in range(1, lags + 1)]
    
    for day in range(1, horizon_days + 1):
        feature_vector = np.array(curr_features + [N + day - 1]).reshape(1, -1)
        pred = float(model.predict(feature_vector)[0])
        predictions.append(pred)
        
        # Proportional confidence widening over time
        spread = 1.645 * resid_std * np.sqrt(day)
        lower_bound.append(max(0, pred - spread))
        upper_bound.append(pred + spread)
        
        # Slide window
        curr_features = [pred] + curr_features[:-1]

    # Prepend starting values
    start_val = series[-1]
    predictions.insert(0, start_val)
    lower_bound.insert(0, start_val)
    upper_bound.insert(0, start_val)
    
    future_dates = [datetime.date.today() + datetime.timedelta(days=i) for i in range(horizon_days + 1)]
    
    return {
        'dates': [d.strftime('%Y-%m-%d') for d in future_dates],
        'p10': lower_bound,
        'p50': predictions,
        'p90': upper_bound,
        'final_values': [predictions[-1]]
    }
