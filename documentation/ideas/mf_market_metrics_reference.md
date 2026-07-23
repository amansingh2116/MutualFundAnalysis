# Market Metrics Reference & Decision Framework for Mutual Fund Investors

This document serves as the comprehensive technical reference for market metrics, macro indicators, sentiment indicators, and fund performance ratios used in the Mutual Fund Analysis application.

---

## 1. Sentiment Indicators

### 🌡️ India VIX
- **Description**: Fear gauge of Indian equity markets — measures implied 30-day volatility of Nifty 50 options.
- **Bullish Signal**: VIX < 12 (Market is complacent; upside momentum intact, but watch for over-extended sentiment).
- **Bearish Signal**: VIX > 20 (Fear is elevated — historically a prime mean-reversion buying / SIP step-up zone).
- **Thresholds**: `< 12` complacent | `12–20` normal | `> 20` fearful | `> 30` panic
- **Data Source**: `yfinance` (`^INDIAVIX`)
- **Code Example**:
  ```python
  import yfinance as yf
  vix = yf.download('^INDIAVIX', period='1y')
  ```

### 📈 Put/Call Ratio (PCR)
- **Description**: Ratio of Put Open Interest to Call Open Interest on Nifty 50 options. Used as a contrarian indicator.
- **Bullish Signal**: PCR > 1.2 (Excessive bearishness in options market; often precedes short-covering rallies).
- **Bearish Signal**: PCR < 0.8 (Excessive bullishness; warns of near-term profit booking or correction).
- **Thresholds**: `< 0.8` overbought | `0.8–1.2` neutral | `> 1.2` oversold (contrarian buy)
- **Data Source**: NSE Option Chain API
- **Code Example**:
  ```python
  import requests
  res = requests.get('https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY')
  ```

### 📊 FII Net Activity
- **Description**: Net daily equity buy/sell volume by Foreign Institutional Investors (in ₹ Crore).
- **Bullish Signal**: Sustained FII buying over 15–30 trading sessions (Capital inflows drive broad market momentum).
- **Bearish Signal**: Sustained FII selling over 1M–3M (Capital flight puts downward pressure on bluechips and currency).
- **Thresholds**: `30-day rolling net flow > 0` = positive liquidity signal
- **Data Source**: NSE FII/DII API
- **Code Example**:
  ```python
  import requests
  res = requests.get('https://www.nseindia.com/api/fiidiiTradeReact')
  ```

### 🏢 DII Net Activity
- **Description**: Net daily equity buy/sell volume by Domestic Institutional Investors (Mutual funds, DIIs in ₹ Crore).
- **Bullish Signal**: DII net buying absorbs FII selling (Provides a strong valuation floor during global market stress).
- **Bearish Signal**: DII and FII both net sellers simultaneously (Double liquidity pressure).
- **Thresholds**: Combined `FII + DII Net Flow > 0`
- **Data Source**: NSE FII/DII API

### ⚖️ Advance / Decline Ratio (Breadth)
- **Description**: Ratio of advancing stocks vs. declining stocks across Nifty 500. Measures rally breadth.
- **Bullish Signal**: A/D > 1.5 (Broad-based market participation; rally is structurally healthy).
- **Bearish Signal**: A/D < 0.7 (Narrow market driven by only a few heavyweights; vulnerable to reversal).
- **Thresholds**: `< 0.7` weak breadth | `0.7–1.5` neutral | `> 1.5` broad participation
- **Data Source**: NSE Live Analysis API

### 💳 SIP Inflow Trend
- **Description**: Monthly SIP contribution data published by AMFI. Proxy for retail investor conviction and systematic inflows.
- **Bullish Signal**: Consistent MoM and YoY growth in monthly SIP totals (Provides steady liquidity buffer to funds).
- **Bearish Signal**: Declining monthly SIP totals or sharp uptick in SIP cancellations.
- **Thresholds**: YoY growth vs 12M trailing average
- **Data Source**: AMFI Monthly Data

---

## 2. Technical Indicators

### 📉 Nifty RSI (14-day)
- **Description**: 14-day Relative Strength Index calculated on Nifty 50 daily closing prices.
- **Bullish Signal**: RSI between 30–45 (Approaching oversold zone; favorable risk-reward for lump-sum deployment).
- **Bearish Signal**: RSI > 70 (Overbought zone; avoid fresh lump-sum investments, stick to SIP).
- **Thresholds**: `< 30` oversold | `30–70` neutral | `> 70` overbought
- **Code Example**:
  ```python
  import pandas as pd
  import yfinance as yf
  
  nifty = yf.download('^NSEI', period='1y')
  delta = nifty['Close'].diff()
  up = delta.clip(lower=0)
  down = -delta.clip(upper=0)
  rs = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
  rsi = 100 - (100 / (1 + rs))
  ```

### 📊 Nifty MACD (12, 26, 9)
- **Description**: Moving Average Convergence Divergence histogram on Nifty 50.
- **Bullish Signal**: MACD line crosses above signal line; positive expanding histogram (Uptrend strengthening).
- **Bearish Signal**: MACD line crosses below signal line; negative histogram (Momentum fading).
- **Thresholds**: Histogram > 0 = Bullish momentum | Histogram < 0 = Bearish momentum

### 🎯 Bollinger Bands (%B)
- **Description**: Price position relative to 2-standard deviation bands. `%B = (Price - Lower) / (Upper - Lower) * 100`.
- **Bullish Signal**: `%B < 20%` (Price near lower band; potential mean-reversion buying opportunity).
- **Bearish Signal**: `%B > 80%` (Price near upper band; extended rally, risk of short-term pullback).
- **Thresholds**: `< 20%` oversold | `20–80%` normal | `> 80%` overextended

### 🔀 Nifty 50/200 DMA Crossover
- **Description**: Percentage gap between Nifty 50's 50-day Simple Moving Average and 200-day Simple Moving Average.
- **Bullish Signal**: Golden Cross (50 DMA > 200 DMA) — Structural bull market pattern.
- **Bearish Signal**: Death Cross (50 DMA < 200 DMA) — Structural bear market warning.
- **Thresholds**: Gap > 0% = Bullish trend | Gap < 0% = Bearish trend

### 📏 Nifty Distance from 52W High & ATH
- **Description**: Percentage drawdown of Nifty 50 from its 52-week peak and All-Time High.
- **Bullish Signal**: Drawdown > 15–20% from peak (Deep correction; historically prime long-term SIP step-up zone).
- **Bearish Signal**: Drawdown < 2% with stretched valuations (Near ATH with high PE).
- **Thresholds**: `< 5%` near ATH | `10–20%` correction | `> 20%` bear market / deep value

### ⚖️ MidCap / LargeCap Relative Strength (RS)
- **Description**: Ratio of Nifty Midcap 150 Total Return to Nifty 50 Total Return over 6 months.
- **Bullish Signal**: RS > 1.0 (Midcaps outperforming Largecaps; Risk-on sentiment in broader market).
- **Bearish Signal**: RS < 1.0 (Largecaps leading; Risk-off flight to safety under way).

---

## 3. Macro India Indicators

### 🏛️ RBI Repo Rate
- **Description**: Benchmark interest rate set by the Reserve Bank of India.
- **Bullish Signal**: Rate cut cycle initiated (Equity-positive; long-duration debt funds gain capital appreciation).
- **Bearish Signal**: Rate hike cycle initiated (Equity valuation headwind; favor short-duration/floater debt funds).
- **Thresholds**: Direction of rate trajectory & MPC stance (Accommodative vs. Withdrawal of Accommodation)
- **Data Source**: FRED API (`INDIRLTLT01STM`) / RBI

### 🏷️ CPI Inflation (YoY)
- **Description**: Consumer Price Index YoY inflation. RBI target band is 4% ± 2%.
- **Bullish Signal**: CPI between 3–5% (Comfort zone; RBI stays accommodative, supporting equity P/E multiples).
- **Bearish Signal**: CPI > 6% (Breaches upper tolerance band; forces rate hikes and compresses P/E ratios).
- **Thresholds**: `< 4%` favorable | `4–6%` neutral | `> 6%` adverse

### 💵 USD / INR Exchange Rate
- **Description**: Exchange rate of Indian Rupee per US Dollar.
- **Bullish Signal**: Stable or appreciating INR (Encourages FII inflows; keeps import inflation low).
- **Bearish Signal**: Rapid INR depreciation > 5% YoY (FII capital exit pressure; wider Current Account Deficit).
- **Thresholds**: `> 5% YoY depreciation` = Macro headwind for domestic equities
- **Data Source**: `yfinance` (`USDINR=X`)

---

## 4. Global Macro Indicators

### 🌐 US VIX (CBOE)
- **Description**: CBOE Volatility Index — global equity market fear gauge.
- **Bullish Signal**: US VIX < 15 (Global risk-on; foreign institutional capital flows to Emerging Markets).
- **Bearish Signal**: US VIX > 25 (Global risk-off panic; liquidity withdrawal from Emerging Markets including India).
- **Thresholds**: `< 15` risk-on | `15–25` normal | `> 25` fear | `> 35` global crisis
- **Data Source**: `yfinance` (`^VIX`)

### 💵 DXY (US Dollar Index)
- **Description**: US Dollar Index against a basket of 6 major currencies.
- **Bullish Signal**: DXY < 100 (Soft dollar; favorable for Emerging Market equity inflows and currency stability).
- **Bearish Signal**: DXY > 105 (Strong dollar; triggers capital flight from EM equities to US Treasuries).
- **Thresholds**: `< 100` EM-friendly | `100–105` neutral | `> 105` headwind

### 🏛️ US 10-Year Treasury Yield
- **Description**: Benchmark global risk-free rate.
- **Bullish Signal**: Falling US 10Y yield (Eases global cost of capital; expands EM equity valuation multiples).
- **Bearish Signal**: Rising US 10Y yield > 4.5% (Increases hurdle rate for equities; drives capital back to US bonds).
- **Data Source**: `yfinance` (`^TNX`)

### ⛽ Brent Crude Oil
- **Description**: Spot price of Brent crude oil in USD per barrel. India imports ~85% of crude oil requirement.
- **Bullish Signal**: Brent < $70 / barrel (Reduces import bill, lowers inflation, improves CAD).
- **Bearish Signal**: Brent > $90 / barrel (Widens CAD, fuels inflation, pressures Rupee and equity margins).
- **Thresholds**: `< $70` favorable | `$70–$90` neutral | `> $90` severe headwind

---

## 5. Mutual Fund Performance & Risk Metrics

### 📊 Rolling 3Y / 5Y CAGR
- **Description**: Average rolling return across all available 3-year or 5-year windows from fund NAV history.
- **Interpretation**: Superior to point-to-point returns. Eliminates end-date bias and tests consistency across market cycles.

### 🛡️ Sharpe & Sortino Ratios (3Y)
- **Sharpe**: Risk-adjusted excess return per unit of total risk: `(Fund Return - Risk Free Rate) / Std Dev`.
- **Sortino**: Risk-adjusted excess return per unit of **downside risk**: `(Fund Return - Risk Free Rate) / Downside Deviation`.
- **Interpretation**: Sortino is superior for equity funds because it does not penalize upside volatility.
- **Thresholds**: `< 0.5` poor | `0.5–1.0` acceptable | `> 1.0` good | `> 2.0` excellent

### 🎯 Alpha & Beta (3Y)
- **Alpha**: Annualized excess return generated by fund manager over benchmark prediction (Jensen's Alpha). Positive alpha indicates genuine stock-picking skill.
- **Beta**: Fund NAV sensitivity to benchmark index. `< 0.85` = Defensive | `0.85–1.15` = Market-like | `> 1.15` = Aggressive.

### 📉 Maximum Drawdown (3Y)
- **Description**: Worst peak-to-trough NAV percentage loss in the past 3 years.
- **Interpretation**: Measures capital preservation in bear markets. Lower drawdown means faster recovery to ATH.

### 💰 Total Expense Ratio (TER)
- **Description**: Annual management & operational fee charged by AMC as a % of fund AUM.
- **Interpretation**: Direct compounding drag on returns. A 0.5% TER savings over 20 years on ₹10 Lakh adds ~₹3.5 Lakh to final corpus.

---

## 6. Mutual Fund Decision Map

| Investment Action | Key Trigger Conditions | What to Avoid |
| :--- | :--- | :--- |
| **💰 Lump Sum Deployment** | • Nifty RSI < 40 (oversold)<br>• Nifty Dist 52WH > 15% (correction)<br>• India VIX > 20 (fear signal)<br>• Brent Crude < $75 | Avoid deploying large lump sum when RSI > 70 and VIX < 12 simultaneously. |
| **⬆️ Step-Up SIP** | • Market in 10–20% correction<br>• CPI Inflation < 5.5% (stable macro)<br>• Monthly SIP inflows growing | Do not pause SIP during market dips — step up instead for lower NAV average. |
| **⏸️ Pause / Slow SIP** | • Nifty 50/200 DMA gap > 15% (euphoria)<br>• RSI > 75 (extreme overbought)<br>• Within 1 year of financial goal | Never pause SIP due to short-term noise; only when near goal horizon. |
| **💸 Profit Booking** | • Financial goal horizon reached (< 12M)<br>• Equity allocation exceeded target by > 15% | Do not book profits solely to time market tops — tax drag reduces compound return. |
| **🔄 Switch: Equity → Debt** | • RBI Rate hike cycle starting<br>• Equity valuation stretched + yield gap negative<br>• Portfolio rebalancing required | Switch systematically via STP over 6–12 months to avoid timing risk. |
| **📋 Switch: Active → Index** | • Active fund 3Y rolling alpha negative<br>• Fund AUM > ₹50,000 Cr with declining performance<br>• TER gap > 0.8% with no alpha | Give active fund at least 2–3 years of underperformance before switching. |
