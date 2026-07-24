# Advanced Quantitative Analysis Suite

> **Comprehensive documentation for the India-focused Mutual Fund Advanced Quantitative Analysis, Forecasting & Risk Engine.**

The **Advanced Quant Suite** (`#tab-advanced`) on the Fund Detail page provides institutional-grade quantitative finance tools, technical indicators, interactive chart overlay engines, stochastic risk simulations, period-wise VaR/CVaR matrices, multi-model statistical forecasting, and a 5-factor composite signal scoring model for mutual fund NAVs.

---

## 🏛 Architecture & Synchronized State

- **Template Location**: `templates/funds/detail.html` (within `{% block content %}`)
- **State Management**:
  - Global reactive variables `window.advRawNav` and `window.advChartDays` synchronize historical daily NAV data across all sub-sections.
  - Data is fetched once upon page load via `navOf()` and `datesOf()`, enabling real-time, sub-second client-side mathematical calculations without redundant server calls.
- **Rendering & Auto-Resize Engine**:
  - Plotly.js for responsive technical charts, sub-panel oscillators, drawdown curves, Monte Carlo percentile fans, 3-band forecast fan charts, and volatility models.
  - **Dynamic Chart Auto-Resizer**: Implemented via `window.triggerAllChartResizes()` and native `ResizeObserver` in `main.js`. Automatically resizes all Plotly SVG and Chart.js canvases during sidebar toggles, window resizes, or split-screen adjustments.
- **Navigation & Visible Tab Scrollbars**: Custom-styled slim horizontal scrollbars (`scrollbar-width: thin`, 6px height, accent-colored thumb) on main tabs (`.tabs`) and subtabs (`.adv-subtab-bar`) ensure first-time users can scroll across all 9 tabs on mobile or small viewports.

---

## 📊 Sub-Tab 1: Technical Indicators (`#adv-technical`)

### 1. Tri-Gauge Signal Summary Meter
A tri-gauge quantitative consensus display scoring technical direction from **-100 (Strongly Bearish)** to **+100 (Strongly Bullish)**:
- **Oscillators Gauge**: Combines 6 momentum-based oscillator signals (RSI, Stochastic, MACD, CCI, Williams %R, Ultimate Oscillator).
- **Moving Averages Gauge**: Combines 10 trend-following moving average signals (SMA & EMA across 10D, 20D, 50D, 100D, 200D).
- **Overall Summary Gauge**: Weighted consensus aggregating Oscillators ($40\%$) and Moving Averages ($60\%$) into an overall Buy, Sell, or Neutral signal.

### 2. Oscillators Table
- **RSI (14D)**: Relative Strength Index ($0\text{--}100$). Overbought $>70$, Oversold $<30$.
- **Stochastic %K/%D (14,3,3)**: Fast and slow stochastic momentum.
- **MACD (12,26,9)**: Moving Average Convergence Divergence line and signal line crossover.
- **CCI (20D)**: Commodity Channel Index.
- **Williams %R (14D)**: Momentum indicator measuring overbought/oversold levels.
- **Awesome Oscillator**: Market momentum indicator comparing 5-period and 34-period SMAs.
- **Average Directional Index (ADX 14)**: Measures trend strength independent of direction ($>25$ indicates strong trend).
- **Bull Bear Power**: Measures power of buyers and sellers relative to 13-period EMA.
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
- **Bollinger Bands ($2\sigma$)**: 20-day SMA center line with $+2\sigma$ upper band and $-2\sigma$ lower band.
- **Support & Resistance (S/R)**: Auto-detected historical price ceilings and floors.

### 3. Interactive Plotly Tools
- **📏 Measure Tool**: Click and drag across any chart range to calculate exact % return, ₹ gain, start/end dates, and duration.
- **✏️ Draw S/R Tool**: Freehand trendline drawing directly on the chart using Plotly's `drawline` modebar feature.

### 4. Sub-Panels with Responsive HTML Headers
- **MACD Sub-Panel**: Plotted with MACD line, 9D Signal line, and colored momentum histogram. Uses HTML header to prevent title/legend collision.
- **RSI Sub-Panel**: Plotted with 14D RSI curve, upper overbought line ($70$), and lower oversold line ($30$). Uses HTML header for zero overlap.

---

## ⚡ Sub-Tab 3: Risk, Period-Wise VaR/CVaR & Monte Carlo (`#adv-risk`)

### 1. Quantitative Risk Metrics Grid
Calculated from historical daily returns using the India 10Y G-Sec risk-free rate proxy ($6.5\%$ p.a.):
- **Annualised Return (CAGR)**, **Annualised Volatility ($\sigma_{ann}$)**
- **Sharpe Ratio** ($>1.0$ is strong), **Sortino Ratio** ($>1.5$ is downside-protected), **Calmar Ratio** (CAGR / MaxDD)
- **Max Drawdown**: Worst peak-to-trough historical loss.
- **VaR (95%, 1D)** & **CVaR (95%, 1D)**: Daily Value at Risk and Expected Shortfall.

### 2. Period-Wise Value at Risk (VaR) & Expected Shortfall (CVaR) Matrix
Computes empirical rolling horizon risk across 4 holding periods at **95%** and **99%** confidence levels:
- **1-Day**: Daily trading fluctuation & short-term risk
- **1-Week (5D)**: 5-day rolling holding period risk
- **1-Month (21D)**: 21-day rolling SIP & rebalancing horizon risk
- **1-Year (252D)**: 252-day annual capital allocation & crash severity
- **Risk Metrics**: 95% VaR, 95% CVaR (Expected Shortfall), 99% VaR, 99% CVaR (Tail Shortfall), and **Tail Risk Verdict Badges** (`Low Downside Risk 🟢`, `Moderate Risk 🔵`, `High Crash Risk 🔴`).

### 3. Underwater (Drawdown) Chart
Plots historical peak-to-trough percentage falls from previous all-time high NAVs.

### 4. Monte Carlo Simulation Engine & Detailed Guide
- Runs **500 stochastic simulation paths** using historical daily return bootstrap resampling:
  - Preserves empirical fat tails, skewness, and crash jumps without assuming a rigid Gaussian normal distribution.
- **Horizons**: 1Y ($252$ days), 3Y ($756$ days), and 5Y ($1,260$ days).
- **Percentile Probability Bands**:
  - **95th Percentile** (Green 🟢): Optimistic Bull Case Scenario
  - **75th Percentile** (Indigo 🟣): Above-Average Growth Path
  - **50th Percentile** (Slate ⚪): Median Expected NAV Baseline
  - **25th Percentile** (Amber 🟡): Below-Average Path (Conservative Goal Benchmark)
  - **5th Percentile** (Red 🔴): Bear Case Scenario (Bottom 5% Crash Outcome)
- **Embedded Guide Card**: Explains simulation mechanics, percentile band definitions, and actionable financial goal planning tips.

---

## 🔬 Sub-Tab 4: Statistical Forecasting & Backtesting Suite (`#adv-forecast`)

Includes an embedded **Guide Card** explaining the 3 target modes, walk-forward backtesting metrics, and model mechanics.

### Target 1: Return / NAV Level Forecasting (Log-Returns)
- **3-Band Fan Chart**: Visualizes central forecast with 68% ($1\sigma$), 80%, and 95% ($2\sigma$) confidence interval shading.
- **Horizon Options**: 30D, 60D, 90D, and 180D horizons.
- **ADF Stationarity Test**: Augmented Dickey-Fuller test verifying stationarity ($p < 0.012$).
- **Model Suite**:
  - **🏆 Ensemble Model**: Blends all enabled models using inverse-MAPE weighting for optimal out-of-sample precision.
  - *Linear Trend*, *Holt Exponential Smoothing*, *Momentum*
  - *Naïve Baseline (Random Walk)*: Benchmark floor for market efficiency.
  - *Moving Average (20D)*, *ETS (Single Exponential Smoothing)*
  - *ARIMA($p,d,q$)*: Autoregressive Integrated Moving Average
  - *XGBoost / Random Forest*: Gradient boosted decision trees on lag features
  - *LSTM Sequence Net*: Deep recurrent neural net simulator
  - *ARIMAX*: Dynamic regression incorporating benchmark index return lags
- **Walk-Forward Out-of-Sample Backtest Table**:
  - Evaluates out-of-sample accuracy over last 90 days.
  - Metrics: **MAPE (%)**, **RMSE (₹)**, **Directional Hit Rate (%)**, and **🥇 Best Model Badge** highlighting.

### Target 2: Direction of Movement Forecasting (Classifiers)
- **Target Labels**: `BULLISH 📈` (return $\ge +\text{threshold}$), `BEARISH 📉` (return $\le -\text{threshold}$), or `SIDEWAYS ➡️`.
- **Classifier Models**: Logistic Regression, XGBoost Classifier, SVM Classifier, Random Forest Ensemble.
- **Diagnostic Table**: Reports **ROC-AUC** ($0.5\text{--}1.0$), **Precision**, **F1-Score**, and **Directional Hit Rate %** ($>55\%$ indicates predictive edge).

### Target 3: Volatility Forecasting (GARCH & ML Volatility)
- **Model Suite**: *Rolling Volatility (20D)*, *EWMA Volatility ($\lambda=0.94$)*, *GARCH(1,1)*, *EGARCH (Asymmetric)*, *Gradient Boosted Volatility ML*.
- **Metrics Table**: Evaluates models using **QLIKE Loss**, **RMSE**, and **Volatility Regime State** (Low 🟢 $<10\%$, Normal 🔵 $10\text{--}20\%$, High 🔴 $>20\%$).

---

## 🧠 Sub-Tab 5: Multi-Factor Composite Quant Signal Score (`#adv-signals`)

Institutional multi-factor quantitative scoring model ($0\text{--}100$) aggregating 15+ sub-indicators across 5 weighted factor pillars:

1. **Factor 1: Trend & Momentum (20% Weight)**: SMA20/50/200 alignment + 1M/3M/6M trailing momentum.
2. **Factor 2: Technical Oscillators & Mean Reversion (20% Weight)**: RSI(14), MACD histogram momentum, and Bollinger %B.
3. **Factor 3: Multi-Model Forecast Consensus (25% Weight)**: Ensemble, Holt, ARIMA, XGBoost/RF, and Direction Classifier % Bullish probability.
4. **Factor 4: Volatility & Tail Risk Regime (20% Weight)**: ATR volatility ratio, GARCH(1,1) forecast, and 95% CVaR tail risk.
5. **Factor 5: Return Consistency (15% Weight)**: Positive monthly return win-rate over past 12 rolling months.

### Component Features:
- **Composite Score Badge & Gauge**: Color-coded 0–100 score badge (`85–100 Strong Bullish Conviction 🟢`, `65–84 Favourable 🔵`, `45–64 Neutral 🟡`, `25–44 Cautious 🟧`, `0–24 Bearish 🔴`).
- **Quant Factor Contribution Matrix Table**: Displays sub-indicators used, factor score (0–100), pillar weight %, weighted points added (+pts), status verdict badges (`✓ Bullish`, `✓ Favourable`, `Neutral`, `⚠ Weak`), and `ⓘ` info buttons per row.
- **💡 How the Engine Works Guide Card**: Embedded guide explaining mathematical methodology, score scale bands, and actionable investment decision rules.
- **Factor Deep-Dive Cards Grid**: Individual cards for each of the 5 factor pillars with key metric values and `ⓘ` tooltips.

---

## 💡 Educational `ⓘ` Info Button System

Every card, table header, chart tool, overlay checkbox, risk metric, forecast parameter, and signal factor includes an interactive `ⓘ` button. Clicking any `ⓘ` button displays a viewport-aware modal popup providing:
- **What Is It?**: Clear plain-English definition.
- **Formula**: Mathematical equation.
- **How to Interpret**: Actionable guidance on thresholds and decision rules.
- **Notes & Cautions**: Statistical caveats and best practices.
