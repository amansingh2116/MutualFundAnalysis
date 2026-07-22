# Advanced Quantitative Analysis Suite

> **Comprehensive documentation for the India-focused Mutual Fund Advanced Quantitative Analysis & Forecasting Engine.**

The **Advanced Quant Suite** (`#tab-advanced`) on the Fund Detail page provides institutional-grade quantitative finance tools, technical indicators, interactive chart overlay engines, stochastic risk simulations, and multi-model statistical forecasting for mutual fund NAVs.

---

## 🏛 Architecture & Synchronized State

- **Template Location**: `templates/funds/detail.html` (within `{% block content %}`)
- **State Management**:
  - Global reactive variables `window.advRawNav` and `window.advChartDays` synchronize historical daily NAV data across all 5 sub-sections.
  - Data is fetched once upon page load via `navOf()` and `datesOf()`, enabling real-time, sub-second client-side mathematical calculations without redundant server calls.
- **Rendering Engine**: Plotly.js for responsive technical charts, sub-panel oscillators, drawdown curves, Monte Carlo percentile fans, and forecast curves.

---

## 📊 Sub-Tab 1: Technical Indicators (`#adv-technical`)

### 1. Tri-Gauge Signal Summary Meter
A tri-gauge quantitative consensus display scoring technical direction from **-100 (Strongly Bearish)** to **+100 (Strongly Bullish)**:
- **Oscillators Gauge**: Combines 6 momentum-based oscillator signals (RSI, Stochastic, MACD, CCI, Williams %R, Ultimate Oscillator).
- **Moving Averages Gauge**: Combines 10 trend-following moving average signals (SMA & EMA across 10D, 20D, 50D, 100D, 200D).
- **Overall Summary Gauge**: Weighted consensus aggregating Oscillators ($40\%$) and Moving Averages ($60\%$) into an overall Buy, Sell, or Neutral signal.

### 2. Oscillators Table
- **RSI (14D)**: Relative Strength Index ($0\text{--}100$). Overbought $>70$, Oversold $<30$.
- **Stochastic %K/%D (14,3)**: Fast and slow stochastic momentum.
- **MACD (12,26,9)**: Moving Average Convergence Divergence line and signal line crossover.
- **CCI (20D)**: Commodity Channel Index.
- **Williams %R (14D)**: Momentum indicator measuring overbought/oversold levels.
- **Ultimate Oscillator**: Multi-timeframe momentum oscillator (7, 14, 28 periods).

### 3. Moving Averages Table
- Computes **SMA (Simple Moving Average)** and **EMA (Exponential Moving Average)** across 10D, 20D, 50D, 100D, and 200D periods.
- **Pattern Recognition**: Automatically flags **Golden Cross** ($50\text{D} \text{SMA} > 200\text{D} \text{SMA}$) and **Death Cross** ($50\text{D} \text{SMA} < 200\text{D} \text{SMA}$).

### 4. Pivot Points Matrix
Calculates 5 classic floor/ceiling pivot systems from 30-day High, Low, and Close NAVs:
1. **Classic Pivots** ($P, R_1, R_2, R_3, S_1, S_2, S_3$)
2. **Fibonacci Pivots** (based on $38.2\%, 61.8\%, 100\%$ ratios)
3. **Camarilla Pivots** (short-term mean reversion bounds)
4. **Woodie's Pivots** (weighted open price pivot)
5. **DeMark Pivots** (predicted high/low range)

---

## 📈 Sub-Tab 2: Interactive NAV Chart & Overlays (`#adv-chart`)

### 1. Multi-Period Selector
- **1Y, 3Y, 5Y, and ALL history** timeframes with dynamic recalculation of technical overlays.

### 2. Technical Overlays
- **SMA 20, 50, 200** & **EMA 12, 26** trendlines.
- **Bollinger Bands ($2\sigma$)**: 20-day SMA center line with $+2\sigma$ upper band and $-2\sigma$ lower band for volatility expansion/contraction channels.
- **Support & Resistance (S/R)**: Auto-detected historical price ceilings and floors.

### 3. Interactive Plotly Tools
- **📏 Measure Tool**: Click and drag across any chart range to generate a floating result banner calculating:
  - Date range & number of days
  - Start NAV & End NAV
  - Absolute gain/loss (₹)
  - Percentage return (%)
  - Holding period duration
- **✏️ Draw S/R Tool**: Enables freehand trendline drawing directly on the chart using Plotly's `drawline` modebar feature with shape editing and erasure controls.

### 4. Sub-Panels
- **MACD Sub-Panel**: Plotted with MACD line, 9D Signal line, and colored momentum histogram bars.
- **RSI Sub-Panel**: Plotted with 14D RSI curve, upper overbought line ($70$), and lower oversold line ($30$).

---

## ⚡ Sub-Tab 3: Risk & Monte Carlo Simulation (`#adv-risk`)

### 1. Quantitative Risk Metrics Grid
Calculated from historical daily returns using the India 10Y G-Sec risk-free rate proxy ($6.5\%$ p.a.):
- **Sharpe Ratio**: Risk-adjusted excess return per unit of total risk ($>1.0$ is strong).
- **Sortino Ratio**: Excess return per unit of downside risk ($>1.5$ is excellent).
- **Treynor Ratio**: Excess return per unit of market risk (Beta).
- **Calmar Ratio**: Annualized CAGR divided by Maximum Drawdown.
- **Beta ($\beta$)**: Sensitivity relative to benchmark index ($<1.0$ indicates lower market volatility).
- **Alpha ($\alpha$)**: Excess annual return generated beyond benchmark expectation.
- **Value at Risk (VaR 95%)**: Maximum expected daily loss at a $95\%$ confidence level.
- **Maximum Drawdown**: Worst peak-to-trough percentage fall in historical NAV.

### 2. Underwater (Drawdown) Chart
Plots the historical percentage fall from the fund's previous all-time high NAV, highlighting trough depth and recovery duration.

### 3. Monte Carlo Simulation Engine
- Runs **1,000 stochastic simulation paths** using historical daily return bootstrapping and geometric Brownian motion:
  $$\text{NAV}_{t+1} = \text{NAV}_t \cdot \exp\left( \left(\mu - \frac{\sigma^2}{2}\right) \Delta t + \sigma \sqrt{\Delta t} Z_t \right)$$
- **Horizons**: 1Y ($252$ days), 3Y ($756$ days), and 5Y ($1,260$ days).
- **Percentile Probability Bands**:
  - **95th Percentile** (Green 🟢): Optimistic Bull Case
  - **75th Percentile** (Indigo 🟣): Upper Middle Expectation
  - **50th Percentile** (Slate ⚪): Median Expected NAV
  - **25th Percentile** (Amber 🟡): Lower Middle Expectation
  - **5th Percentile** (Red 🔴): Pessimistic Bear Case

---

## 🔭 Sub-Tab 4: Statistical Forecasting Suite (`#adv-forecast`)

The forecasting engine addresses 3 distinct quantitative targets:

### Target 1: Return / NAV Level Forecasting (Log-Returns)
- **Log Returns Transformation**: Models predict log returns $r_t = \ln(\text{NAV}_t / \text{NAV}_{t-1})$ to satisfy stationarity, then project NAV curves:
  $$\text{NAV}_{t+k} = \text{NAV}_t \cdot \exp\left(\sum_{i=1}^k r_{t+i}\right)$$
- **ADF Stationarity Test**: Computes Augmented Dickey-Fuller test $p$-value ($p < 0.012$) to verify log-return stationarity.
- **Model Suite**:
  - *Linear Trend*, *Holt Exponential Smoothing*, *Momentum*
  - *Naive Baseline*, *Moving Average (20D)*, *ETS*
  - *ARIMA($p,d,q$)*: Autoregressive Integrated Moving Average
  - *XGBoost / Random Forest*: Gradient boosted decision trees on lag features (1, 3, 5, 10, 20D) & rolling stats
  - *LSTM Sequence Net*: Deep recurrent neural net simulator learning sequence dependencies
  - *ARIMAX*: Dynamic regression incorporating benchmark index return lags as exogenous variables
- **Walk-Forward Out-of-Sample Backtest Table**: Evaluates out-of-sample prediction accuracy reporting **MAPE (Mean Absolute Percentage Error)** and **Directional Hit Rate %**.

### Target 2: Direction of Movement Forecasting (Classifiers)
- **Target Labels**: `BULLISH 📈` (return $\ge +\text{threshold}$), `BEARISH 📉` (return $\le -\text{threshold}$), or `SIDEWAYS ➡️`.
- **Classifier Models**: Logistic Regression, XGBoost Classifier, SVM Classifier, Random Forest Ensemble.
- **Diagnostic Table**: Reports **ROC-AUC** ($0.5\text{--}1.0$), **Precision**, **F1-Score**, and **Directional Hit Rate %** ($>55\%$ indicates predictive edge).

### Target 3: Volatility Forecasting (GARCH & ML Volatility)
- **Volatility Target**: Models return volatility ($\sigma_r$) scaled as annualized % p.a. ($\times \sqrt{252} \cdot 100$) or daily %.
- **Model Suite**:
  - *Rolling Volatility (20D)*
  - *EWMA Volatility*: RiskMetrics exponential weighting ($\lambda = 0.94$)
  - *GARCH(1,1)*: $\sigma_t^2 = \omega + \alpha \epsilon_{t-1}^2 + \beta \sigma_{t-1}^2$
  - *EGARCH*: Asymmetric volatility leverage effect $\ln(\sigma_t^2) = \omega + \beta \ln(\sigma_{t-1}^2) + \alpha |\epsilon_{t-1}| + \gamma \epsilon_{t-1}$
  - *Gradient Boosted Volatility ML*: Machine learning model on lagged squared returns
- **Metrics Table**: Evaluates models using **QLIKE Loss** ($\ln(\sigma_{pred}^2) + \frac{\sigma_{actual}^2}{\sigma_{pred}^2}$), **RMSE**, and **Volatility Regime State** (Low 🟢 $<10\%$, Normal 🔵 $10\text{--}20\%$, High 🔴 $>20\%$).

---

## 🧩 Sub-Tab 5: Composite Signal Score (`#adv-signals`)

Aggregates 5 quantitative pillars into a composite score ($0\text{--}100$):
1. **Trend Strength** (SMA/EMA alignment)
2. **Momentum** (RSI, MACD divergence)
3. **Volatility Regime** (Bandwidth, GARCH stability)
4. **Mean Reversion** (Bollinger Band percentile)
5. **Consistency** (Rolling return win rate)

**Score Bands**:
- **80–100**: Strongly Favourable 🟢
- **60–80**: Favourable 🔵
- **40–60**: Neutral 🟡
- **20–40**: Cautious 🟠
- **0–20**: Unfavourable 🔴

---

## 💡 Educational `ⓘ` Info Button System

Every card, table header, chart tool, overlay checkbox, risk metric, and forecast parameter includes an interactive `ⓘ` button. Clicking any `ⓘ` button displays a modal popup providing:
- **What Is It?**: Clear plain-English definition.
- **How to Interpret**: Actionable guidance on thresholds and signals.
- **Notes & Cautions**: Statistical caveats and best practices.
