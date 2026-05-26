# Signal Generation:For the equity indices (midcap, momentum, Nasdaq), generates daily "buy" signals based on three rules:Momentum: If the 12-month return is positive.

# Trend: If the current price is above the 10-month simple moving average.

# Volatility: If the 6-month volatility is below its historical median.

# A signal is "on" if at least 2 of the 3 rules are true; otherwise, it's "off".

# Strategy Simulation:Simulates daily portfolio updates over the historical period.

# Monthly Investments (SIP): On the first day of each month, invests the SIP amount.Allocates according to weights, but for tactical: If a signal is "on" for an equity index, invests in it; if "off", shifts that portion to debt.

# Passive: Always allocates directly to the fixed weights, regardless of signals.

# Debt always gets its 20% base allocation.

# Daily Updates: Adjusts holdings based on that day's price changes for all assets.

# Annual Rebalancing: At the end of each year, resets allocations back to the target weights to prevent drift.

# Tracks total portfolio value for both tactical and passive approaches daily.

# Records cash flows (negative for investments) for later performance metrics.

# Performance Report:Calculates:Final portfolio value (corpus) for both strategies.

# XIRR (internal rate of return, accounting for irregular cash flows like monthly SIPs).

# 5-year trailing CAGR (most recent 5-year return).

# Prints a summary table comparing tactical and passive metrics.

# Plots the growth of both portfolios over time.


import pandas as pd
import numpy as np
import yfinance as yf
from scipy.optimize import newton
import matplotlib.pyplot as plt
import warnings
from nselib import capital_market
from datetime import datetime

warnings.filterwarnings("ignore")

# --- UTILITIES ---
def calculate_xirr(cashflows_series):
    """Computes XIRR using the Newton-Raphson method."""
    def xnpv(rate, cashflows):
        t0 = cashflows.index[0]
        return sum([cf / (1 + rate)**((d - t0).days / 365.25) for d, cf in cashflows.items()])
    
    try:
        # Initial guess of 10%
        return newton(lambda r: xnpv(r, cashflows_series), 0.1, maxiter=100)
    except:
        return np.nan

# --- CORE ENGINE ---
class QuantBacktester:
    def __init__(self, start_date, end_date, sip=500):
        self.start = start_date
        self.end = end_date
        self.sip = sip
        self.weights = {'midcap': 0.25, 'momentum': 0.25, 'nasdaq': 0.30, 'debt': 0.20}
        self.data = None
        self.returns = None

    def fetch_data(self):
        # Indices symbols
        indices = {
            'midcap': 'NIFTY MIDCAP 150',
            'momentum': 'NIFTY200 MOMENTUM 30',
            'nasdaq': '^NDX'
        }

        # Convert dates to strings for nselib
        start_dt = datetime.strptime(self.start, '%Y-%m-%d')
        end_dt = datetime.strptime(self.end, '%Y-%m-%d')
        start_str = start_dt.strftime('%d-%m-%Y')
        end_str = end_dt.strftime('%d-%m-%Y')

        dfs = []
        for name in ['midcap', 'momentum']:
            df = capital_market.index_data(indices[name], start_str, end_str)
            df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'], format='%d-%b-%Y')
            df = df.set_index('TIMESTAMP')
            close = df['CLOSE_INDEX_VAL']
            close.name = name
            dfs.append(close)

        # Nasdaq with handling for possible multiindex
        df_nasdaq = yf.download(indices['nasdaq'], start=start_dt, end=end_dt)
        if isinstance(df_nasdaq.columns, pd.MultiIndex):
            close_nasdaq = df_nasdaq[('Close', indices['nasdaq'])]
        else:
            close_nasdaq = df_nasdaq['Close']
        close_nasdaq.name = 'nasdaq'
        dfs.append(close_nasdaq)

        self.data = pd.concat(dfs, axis=1, join='outer').sort_index().ffill().dropna()
        
        if self.data.empty:
            raise ValueError("No overlapping data available for the given date range. Adjust the start date.")

        # Synthetic Debt Index (7% CAGR)
        days = (self.data.index - self.data.index[0]).days
        self.data['debt'] = 100 * (1.07 ** (days / 365.25))
        
        # Compute returns
        self.returns = self.data.pct_change().dropna()

    def get_signals(self):
        signals = pd.DataFrame(index=self.data.index)
        for col in ['midcap', 'momentum', 'nasdaq']:
            # 12M Return > 0
            sig_mom = self.data[col].pct_change(252) > 0
            # Price > 10M SMA
            sig_sma = self.data[col] > self.data[col].rolling(210).mean()
            # 6M Volatility < Median
            vol = self.data[col].pct_change().rolling(126).std()
            sig_vol = vol < vol.expanding().median()
            
            # Aggregate Signal (Rule: >= 2 ON)
            signals[col] = (sig_mom.astype(int) + sig_sma.astype(int) + sig_vol.astype(int)) >= 2
        return signals.fillna(False)

    def run_strategy(self):
        
        signals = self.get_signals()
        dates = self.data.index
        
        # Portfolio States
        tactical_holdings = {k: 0.0 for k in self.weights.keys()}
        passive_holdings = {k: 0.0 for k in self.weights.keys()}
        
        tactical_cfs = []
        passive_cfs = []
        history = []

        for i, today in enumerate(dates):
            # Monthly SIP
            if i == 0 or today.month != dates[i-1].month:
                tactical_cfs.append((today, -self.sip))
                passive_cfs.append((today, -self.sip))
                
                for asset in ['midcap', 'momentum', 'nasdaq']:
                    w = self.weights[asset]
                    # Tactical: Check Signal
                    t_target = asset if signals.loc[today, asset] else 'debt'
                    tactical_holdings[t_target] += self.sip * w
                    # Passive: Direct Allotment
                    passive_holdings[asset] += self.sip * w
                
                # Base Debt Allotment (20%)
                tactical_holdings['debt'] += self.sip * self.weights['debt']
                passive_holdings['debt'] += self.sip * self.weights['debt']

            # Daily Price Update
            t_total, p_total = 0, 0
            if i > 0:
                for asset in self.weights.keys():
                    ret = self.data[asset].iloc[i] / self.data[asset].iloc[i-1]
                    tactical_holdings[asset] *= ret
                    passive_holdings[asset] *= ret
            
            t_total = sum(tactical_holdings.values())
            p_total = sum(passive_holdings.values())

            # Annual Rebalancing (Reset to target weights)
            if i > 0 and today.year > dates[i-1].year:
                for asset, w in self.weights.items():
                    tactical_holdings[asset] = t_total * w
                    passive_holdings[asset] = p_total * w

            history.append({'Date': today, 'Tactical': t_total, 'Passive': p_total})

        self.res = pd.DataFrame(history).set_index('Date')
        self.t_cfs = pd.Series(dict(tactical_cfs))
        self.p_cfs = pd.Series(dict(passive_cfs))

    def plot_correlation(self):
        corr = self.returns.corr()
        print("Correlation Matrix:")
        print(corr)
        
        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.matshow(corr, cmap='coolwarm')
        ax.set_xticks(range(len(corr.columns)))
        ax.set_yticks(range(len(corr.columns)))
        ax.set_xticklabels(corr.columns, rotation=45)
        ax.set_yticklabels(corr.columns)
        plt.colorbar(im)
        plt.title("Correlation Matrix of Indices")
        plt.show()

    def calculate_volatility(self):
        ann_vol = self.returns.std() * np.sqrt(252) * 100  # in %
        print("Annualized Volatility of Individual Indices (%):")
        print(ann_vol)
        
        blended_returns = (self.returns * pd.Series(self.weights)).sum(axis=1)
        blended_vol = blended_returns.std() * np.sqrt(252) * 100
        print("\nBlended Benchmark Volatility (%):", blended_vol)

    def analyze_rolling_returns(self, years=5):
        trading_days = 252 * years
        rolling_cagr = {}
        
        for col in self.data.columns:
            prices = self.data[col]
            rolling_ret = prices / prices.shift(trading_days) - 1
            cagr = (1 + rolling_ret) ** (1 / years) - 1
            rolling_cagr[col] = cagr.dropna() * 100  # in %
        
        # Blended Benchmark
        blended_returns = (self.returns * pd.Series(self.weights)).sum(axis=1)
        blended_cum = (1 + blended_returns).cumprod()
        blended_rolling_ret = blended_cum / blended_cum.shift(trading_days) - 1
        blended_cagr = (1 + blended_rolling_ret) ** (1 / years) - 1
        rolling_cagr['blended'] = blended_cagr.dropna() * 100
        
        # Plot
        pd.DataFrame(rolling_cagr).plot(figsize=(12, 6))
        plt.title(f"{years}-Year Rolling CAGR (%)")
        plt.grid(True)
        plt.show()
        
        # Stats
        stats = pd.DataFrame({
            'Min': {k: v.min() for k, v in rolling_cagr.items()},
            'Max': {k: v.max() for k, v in rolling_cagr.items()},
            'Avg': {k: v.mean() for k, v in rolling_cagr.items()}
        })
        print(f"{years}-Year Rolling Returns Stats (%):")
        print(stats)

    def report(self):
        # Add final value to cashflows for XIRR
        t_cfs, p_cfs = self.t_cfs.copy(), self.p_cfs.copy()
        t_cfs[self.res.index[-1]] = self.res['Tactical'].iloc[-1]
        p_cfs[self.res.index[-1]] = self.res['Passive'].iloc[-1]

        # Trailing Returns (5 Year)
        t_5y = (self.res['Tactical'].iloc[-1] / self.res['Tactical'].iloc[-252*5])**(1/5) - 1 if len(self.res) > 252*5 else np.nan
        p_5y = (self.res['Passive'].iloc[-1] / self.res['Passive'].iloc[-252*5])**(1/5) - 1 if len(self.res) > 252*5 else np.nan

        print("\n--- PERFORMANCE SUMMARY ---")
        print(f"{'Metric':<20} | {'Tactical (You)':<15} | {'Passive':<15}")
        print("-" * 55)
        print(f"{'Final Corpus':<20} | ₹{t_cfs.iloc[-1]:>13,.0f} | ₹{p_cfs.iloc[-1]:>13,.0f}")
        print(f"{'XIRR (%)':<20} | {calculate_xirr(t_cfs)*100:>14.2f}% | {calculate_xirr(p_cfs)*100:>14.2f}%")
        print(f"{'5Y Trailing (%)':<20} | {t_5y*100:>14.2f}% | {p_5y*100:>14.2f}%")
        
        # Plotting
        self.res.plot(figsize=(10, 5), title="Tactical vs Passive Growth")
        plt.grid(True)
        plt.show()

# --- RUN ---
tester = QuantBacktester("2012-01-01", "2024-12-31")
tester.fetch_data()
tester.plot_correlation()
tester.calculate_volatility()
tester.analyze_rolling_returns()
tester.run_strategy()
tester.report()