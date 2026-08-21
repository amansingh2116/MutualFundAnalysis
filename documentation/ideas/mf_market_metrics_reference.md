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

---

## 3. Valuation Metrics

### 📊 Nifty 50 PE Ratio (Trailing)
- **Description**: Trailing Price-to-Earnings ratio of Nifty 50.
- **Interpretation**: Historically, Nifty 50 PE has traded in the 16x–28x range.
- **Signals**:
  - `PE < 18`: Deep value zone (historic strong long-term entry point for lump sums).
  - `18 <= PE <= 24`: Fair value zone (optimal for regular monthly SIP compounding).
  - `PE > 24`: Expensive (market priced for high growth; avoid large lump sums).
  - `PE > 28`: Frothy / extreme overvaluation (consider tactical equity-to-debt rebalancing).
- **Data Source**: NSE India (`/api/allIndices`, with `NIFTYBEES.NS` fallback).

### 📖 Nifty 50 PB Ratio (Price-to-Book)
- **Description**: Price-to-Book ratio comparing Nifty 50 market value to aggregate book value per share.
- **Signals**:
  - `PB < 2.5`: Undervalued relative to underlying corporate assets.
  - `2.5 <= PB <= 3.5`: Normal historical range for Indian large-cap equities.
  - `PB > 3.5`: Premium valuation (requires strong return on equity to justify).
- **Data Source**: NSE India (`/api/allIndices`).

### 🌾 Nifty Dividend Yield
- **Description**: Trailing annual dividend yield (%) of Nifty 50 index constituents.
- **Signals**:
  - `DY > 2.0%`: High dividend yield (indicates depressed stock prices and value buffer).
  - `1.2% <= DY <= 2.0%`: Fair historical range.
  - `DY < 1.2%`: Low dividend yield (growth premium priced into market; lower margin of safety).
- **Data Source**: NSE India (`/api/allIndices`).

### ⚖️ Earnings Yield – 10Y Bond Yield Gap
- **Description**: Spread between Nifty Earnings Yield `(1 / PE × 100%)` and India 10-Year G-Sec Yield.
- **Signals**:
  - `Gap > 2.0%`: Equities significantly undervalued relative to risk-free sovereign debt.
  - `0.0% <= Gap <= 2.0%`: Equities fairly valued compared to fixed income.
  - `Gap < 0.0%`: Sovereign bond yields exceed equity earnings yield; bonds offer superior risk-adjusted return.
- **Data Source**: Computed dynamically via Nifty PE and FRED India 10Y Yield (`INDIRLTLT01STM`).

### 🌐 Buffett Indicator (India Market Cap to GDP)
- **Description**: Total market capitalization of Indian listed companies expressed as a % of Indian GDP.
- **Signals**:
  - `< 75%`: Undervalued (exceptional long-term accumulation zone).
  - `75%–100%`: Fair valuation.
  - `100%–120%`: Moderately expensive.
  - `> 120%`: Substantially overvalued.
- **Data Source**: World Bank (`wbgapi` series `CM.MKT.LCAP.CD` and `NY.GDP.MKTP.CD`, cached 1 week).

---

## 4. Market Sentiment Indicators

### ⚡ India VIX (Volatility Index)
- **Description**: NSE India Volatility Index (fear gauge).
- **Signals**:
  - `VIX < 12`: Extreme complacency (potential vulnerability to pullbacks).
  - `12–18`: Normal healthy market volatility.
  - `18–25`: Elevated uncertainty / corrective pressure.
  - `> 25`: Panic / capitulation (historically exceptional multi-year SIP step-up or lump sum window).
- **Data Source**: `yfinance` (`^INDIAVIX`).

### 🎯 Nifty Put/Call Ratio (PCR by Open Interest)
- **Description**: Ratio of total Put Open Interest to Call Open Interest on Nifty derivatives: `Total PE OI / Total CE OI`.
- **Signals**:
  - `PCR < 0.7`: Extreme call buying / overbought (complacency; caution warranted).
  - `0.7–1.1`: Neutral market positioning.
  - `PCR > 1.1`: High put hedging / oversold (contrarian bullish signal).
- **Data Source**: NSE Derivatives API (`/api/liveEquity-derivatives?index=nse50_opt`).

### 💼 FII / DII Net Institutional Activity
- **Description**: Net purchase/sale value (in ₹ Crores) by Foreign Institutional Investors for the latest trading session.
- **Signals**:
  - `FII Net > +₹2,000 Cr`: Sustained institutional accumulation (index tailwind).
  - `FII Net < -₹2,000 Cr`: Institutional distribution / risk-off selling.
- **Data Source**: NSE FII/DII API (`/api/fiidiiTradeReact`).

### 📈 Advance / Decline Ratio (Nifty 500 Breadth)
- **Description**: Ratio of advancing stocks to declining stocks across the broader Nifty 500 universe.
- **Signals**:
  - `A/D > 1.5`: Broad-based healthy market rally.
  - `0.8–1.5`: Mixed / selective market.
  - `A/D < 0.8`: Broad-based market decline (warning signal if headline indices are rising on narrow stock leadership).
- **Data Source**: NSE Index API (`/api/allIndices`).

### 🌊 Monthly SIP Inflow Trends
- **Description**: Total monthly mutual fund SIP contributions (in ₹ Crores) across all AMCs.
- **Signals**:
  - `> ₹22,000 Cr/month & Growing`: Robust domestic retail liquidity providing structural market downside support ("SIP Cushion").
- **Data Source**: AMFI India (`/research-information/amfi-monthly`, cached 24h).

---

## 5. Macro India Indicators

### 🏛️ India 10-Year Government Bond Yield (G-Sec)
- **Description**: 10-Year Long-Term Government Bond Yield (benchmark risk-free sovereign rate).
- **Bullish Signal**: Falling 10Y yield (Equity-positive; long-duration debt funds gain capital appreciation).
- **Bearish Signal**: Rising 10Y yield > 7.2% (Equity valuation headwind; favor short-duration/floater debt funds).
- **Thresholds**: `< 6.5%` bond-friendly | `6.5%–7.2%` neutral | `> 7.2%` equity headwind
- **Data Source**: FRED API (`INDIRLTLT01STM`) / OECD

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
## 6. Global Macro Indicators

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

## 7. Mutual Fund Performance & Risk Metrics

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

## 8. Mutual Fund Decision Map

| Investment Action | Key Trigger Conditions | What to Avoid |
| :--- | :--- | :--- |
| **💰 Lump Sum Deployment** | • Nifty PE < 18 (deep value) or EY–Bond Gap > 2%<br>• Nifty RSI < 40 (oversold) & PCR > 1.1<br>• Nifty Dist 52WH > 15% (correction)<br>• India VIX > 20 (fear signal) | Avoid deploying large lump sums when PE > 25, RSI > 70, and VIX < 12 simultaneously. |
| **⬆️ Step-Up SIP** | • Market in 10–20% correction<br>• Buffett Indicator < 100% (fair value)<br>• CPI Inflation < 5.5% (stable macro)<br>• Monthly SIP inflows growing (>₹22,000 Cr) | Do not pause SIP during market dips — step up instead for lower NAV rupee-cost averaging. |
| **⏸️ Pause / Slow SIP** | • Nifty 50/200 DMA gap > 15% (euphoria)<br>• RSI > 75 (extreme overbought)<br>• Within 1 year of financial goal maturity | Never pause SIP due to short-term headlines; only when approaching goal horizon. |
| **💸 Tactical Profit Booking** | • Financial goal horizon reached (< 12M)<br>• Nifty PE > 28 & Buffett Indicator > 120%<br>• Equity allocation exceeded portfolio target by > 15% | Do not book profits solely to time tops — capital gains tax drag reduces compound growth. |
| **🔄 Switch: Equity → Debt** | • EY–Bond Yield Gap < 0% (Bonds offer higher yield than earnings)<br>• India 10Y Yield rising > 7.5%<br>• Rebalancing to target asset allocation | Switch systematically via STP over 6–12 months to minimize execution risk. |
| **📋 Switch: Active → Index** | • Active fund 3Y rolling alpha negative across 2+ market cycles<br>• Fund AUM > ₹50,000 Cr with declining quartile rank<br>• TER gap > 0.8% with no alpha generation | Give active fund manager at least 2–3 years of underperformance before switching. |

