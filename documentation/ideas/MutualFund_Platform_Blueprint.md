# 📊 MutualEdge — Mutual Fund Intelligence Platform
## Comprehensive Product & Technical Blueprint

> *A unified platform for live NAV tracking, institutional-grade technical analysis, multi-model ML forecasting, risk intelligence, and portfolio optimization — built for the Indian retail investor.*

---

## Table of Contents

1. [Platform Vision & Goals](#1-platform-vision--goals)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Data Ingestion & Management Layer](#3-data-ingestion--management-layer)
4. [Technical Analysis Engine](#4-technical-analysis-engine)
5. [Risk Analysis Module](#5-risk-analysis-module)
6. [Time-Series Forecasting Suite](#6-time-series-forecasting-suite)
7. [Machine Learning Forecasting Engine](#7-machine-learning-forecasting-engine)
8. [Live NAV Estimation & Real-Time Tracking](#8-live-nav-estimation--real-time-tracking)
9. [TruthLens — Prediction Accuracy Tracker](#9-truthlens--prediction-accuracy-tracker)
10. [Fund Screener & Comparison Engine](#10-fund-screener--comparison-engine)
11. [Portfolio Builder & Optimizer](#11-portfolio-builder--optimizer)
12. [AI-Powered Insights Layer](#12-ai-powered-insights-layer)
13. [Interactive Dashboard & Visualization](#13-interactive-dashboard--visualization)
14. [Alerts, Watchlist & Notifications](#14-alerts-watchlist--notifications)
15. [Automation & Retraining Pipeline](#15-automation--retraining-pipeline)
16. [Technology Stack](#16-technology-stack)
17. [Database Schema Design](#17-database-schema-design)
18. [API Design](#18-api-design)
19. [UI/UX Blueprint](#19-uiux-blueprint)
20. [Deployment Strategy](#20-deployment-strategy)
21. [Monetization & Access Tiers](#21-monetization--access-tiers)
22. [Compliance & Disclaimers](#22-compliance--disclaimers)

---

## 1. Platform Vision & Goals

### Vision Statement

MutualEdge is India's most comprehensive mutual fund intelligence platform, providing retail investors with institutional-grade technical analysis, multi-algorithm AI forecasting, real-time NAV estimation, and transparent prediction accountability — all in one unified terminal.

### Core Goals

**G1 — Democratize institutional analytics:** Bring TradingView-style charting, RSI, MACD, Bollinger Bands, and VWAP to mutual fund NAV data — tools previously inaccessible to retail investors.

**G2 — Multi-model forecasting transparency:** Don't just show predictions; show *which model* made them, *how accurate* they've historically been, and let users choose models based on their investment horizon.

**G3 — Live intelligence during market hours:** Estimate intra-day NAV movements every minute during NSE/BSE trading hours by tracking underlying portfolio holdings — not just end-of-day data.

**G4 — Prediction accountability (TruthLens):** Compare every prior prediction against the official AMC-published NAV the following day. Let users see exactly how reliable the platform's forecasts are.

**G5 — Comprehensive risk-adjusted selection:** Help users pick funds not just by returns but through alpha, beta, Sharpe ratio, standard deviation, R-squared, and expense ratio scoring across 3-, 5-, and 10-year horizons.

### Target Users

- Retail mutual fund investors in India (primary)
- Independent financial advisors and distributors (AMFI-registered)
- Fintech researchers and data scientists studying NAV prediction
- Portfolio management services (PMS) professionals

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                 │
│   Web App (React)   │   Mobile App (React Native)   │   REST API   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                      API GATEWAY (FastAPI)                           │
│         Auth │ Rate Limiting │ Routing │ Caching (Redis)            │
└───┬──────────────┬──────────────┬──────────────┬───────────────┬────┘
    │              │              │              │               │
┌───▼──┐     ┌────▼────┐    ┌────▼────┐   ┌────▼────┐    ┌────▼────┐
│ Data │     │Technical│    │  Risk   │   │   ML/   │    │  Live   │
│Ingest│     │Analysis │    │Analysis │   │Forecast │    │  NAV    │
│Service│    │ Service │    │ Service │   │ Service │    │ Service │
└───┬──┘     └────┬────┘    └────┬────┘   └────┬────┘    └────┬────┘
    │              │              │              │               │
┌───▼──────────────▼──────────────▼──────────────▼───────────────▼────┐
│                         MESSAGE BROKER (Kafka)                        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                          DATA LAYER                                    │
│  PostgreSQL (historical NAV)  │  InfluxDB (time-series)               │
│  Redis (cache/session)        │  MongoDB (fund metadata)              │
│  S3 / Object Store (models)   │  Elasticsearch (search index)         │
└───────────────────────────────────────────────────────────────────────┘
```

### Microservices Overview

| Service | Responsibility | Language / Framework |
|---|---|---|
| `data-ingestion-service` | Pull NAV from AMFI, MFTool, BSE, NSE APIs | Python / Celery |
| `technical-analysis-service` | Compute all indicators on NAV time series | Python / Pandas / TA-Lib |
| `risk-service` | Compute Alpha, Beta, Sharpe, VaR, Drawdown | Python / NumPy |
| `forecast-service` | ARIMA, Prophet, LSTM, Random Forest, XGBoost | Python / TF / Scikit-learn |
| `live-nav-service` | Intra-day NAV estimation from holdings | Python / asyncio |
| `screener-service` | Filter, rank, and sort funds by criteria | Python / Pandas |
| `portfolio-service` | SIP simulation, optimizer, correlation matrix | Python / SciPy |
| `auth-service` | JWT auth, user management, plan enforcement | Python / FastAPI |
| `notification-service` | Email / WhatsApp / push alerts | Python / Celery |
| `truthlens-service` | Prediction vs. actual comparison ledger | Python / PostgreSQL |

---

## 3. Data Ingestion & Management Layer

### 3.1 Data Sources

| Source | Data Provided | Update Frequency |
|---|---|---|
| **AMFI India API** | End-of-day NAV for all 10,000+ schemes | Daily (post 9 PM IST) |
| **BSE StAR MF API** | Scheme metadata, ISIN, AUM, category | Daily |
| **NSE Data** | Underlying equity prices for equity funds | Real-time during market |
| **MFTool Library** | Historical NAV via Python wrapper | On-demand |
| **SEBI SCORES** | Regulatory data, fund house complaints | Weekly |
| **RBI / CCIL** | Debt security yields, G-Sec data for debt funds | Daily |
| **FII/DII Data** | Institutional flow data (market mood) | Daily |
| **Morningstar / Value Research** | Category benchmarks, peer group data | Weekly |

### 3.2 Data Pipeline Architecture

```
Raw Source → Kafka Producer → Kafka Topic → Kafka Consumer
          → Validation / Schema Check
          → Transformation (clean, normalize, align dates)
          → Feature Engineering
          → Write to PostgreSQL + InfluxDB
          → Invalidate Redis Cache
          → Trigger Model Retraining (if scheduled)
```

### 3.3 Data Preprocessing Module

Inspired by `data_preprocessing.py` from the Satej-Zunjarrao project, this module:

- Loads raw NAV data per scheme code (aligned to AMFI's 5-digit scheme code system)
- Handles missing NAV values using forward-fill (suitable for market holidays)
- Aligns all time-series to a common trading calendar (NSE working days)
- Detects and flags scheme mergers, NFO launches, and category reclassifications
- Normalizes NAV to base 10 or 100 for cross-fund comparison
- Computes daily returns: `r_t = (NAV_t − NAV_{t−1}) / NAV_{t−1}`

### 3.4 Feature Engineering Module

Derived from the `feature_engineering.py` module pattern:

**Rolling Statistics:**
- Rolling Mean: 5-day, 10-day, 20-day, 50-day, 100-day, 200-day windows
- Rolling Standard Deviation (Volatility proxy): 10-day, 30-day, 90-day
- Rolling Sharpe Ratio (annualized): 30-day, 90-day, 1-year
- Rolling Max Drawdown: 30-day, 1-year

**Lag Features (for ML models):**
- NAV lag: t-1, t-3, t-5, t-10, t-21 (1 month), t-63 (quarter)
- Return lag: t-1 through t-10

**Derived Features:**
- `volatility_30d` = 30-day rolling std of daily returns × √252
- `momentum_score` = (NAV_t / NAV_{t-21}) − 1 (1-month momentum)
- `trend_strength` = linear regression slope over last 20 NAV points
- `benchmark_excess_return` = fund return − Nifty 50 return (for equity funds)

---

## 4. Technical Analysis Engine

Inspired by MFShala's TradingView-style charting for mutual funds and the Investopedia technical indicator framework.

### 4.1 Moving Averages

| Indicator | Periods Available | Use Case |
|---|---|---|
| **SMA (Simple Moving Average)** | 10, 20, 50, 100, 200 | Trend direction, support/resistance |
| **EMA (Exponential Moving Average)** | 9, 12, 20, 26, 50 | Faster trend signals, MACD inputs |
| **WMA (Weighted Moving Average)** | 10, 20 | Reduced lag compared to SMA |
| **DEMA (Double EMA)** | 20, 50 | Even faster signal, less lag |
| **VWAP (Volume-Weighted Avg Price)** | Daily, Weekly | Institutional price reference |

**Chart Display:** Multiple SMAs overlaid on the NAV candle chart. Golden Cross (SMA-50 crosses above SMA-200) and Death Cross events are auto-annotated with flags.

### 4.2 Momentum Oscillators

**RSI (Relative Strength Index):**
- Default period: 14-day
- Overbought threshold: RSI > 70 → potential pullback signal
- Oversold threshold: RSI < 30 → potential buying opportunity
- RSI Divergence detection: Flag when NAV makes new highs but RSI doesn't
- Applicable period options: 7, 14, 21 days

**MACD (Moving Average Convergence Divergence):**
- Configuration: 12-day EMA − 26-day EMA = MACD Line
- Signal Line: 9-day EMA of MACD Line
- Histogram: MACD Line − Signal Line
- Bullish signal: MACD crosses above Signal Line
- Bearish signal: MACD crosses below Signal Line
- Zero-line crossover alerts

**Stochastic Oscillator:**
- %K period: 14 days; %D smoothing: 3 days
- Overbought: > 80; Oversold: < 20
- Highlights mean-reversion tendencies in fund NAV

**Rate of Change (ROC):**
- Measures percentage change over a given look-back period
- Periods: 5-day, 10-day, 21-day, 63-day (quarterly)

### 4.3 Volatility Indicators

**Bollinger Bands:**
- Middle Band: 20-day SMA
- Upper Band: SMA + 2 × 20-day standard deviation
- Lower Band: SMA − 2 × 20-day standard deviation
- Bandwidth indicator: `(Upper − Lower) / Middle × 100`
- Squeeze detection: When bandwidth < 10th percentile of its own 6-month range
- %B indicator: `(NAV − Lower) / (Upper − Lower)`

**Average True Range (ATR):**
- Measures market volatility; adapted to NAV daily ranges
- Period: 14 days (default)
- Used to calibrate alert thresholds dynamically

**Keltner Channels:**
- Middle: 20-day EMA; Upper/Lower: ±2 × ATR
- Complementary to Bollinger Bands for breakout confirmation

### 4.4 Volume-Equivalent Indicators (Adapted for Mutual Funds)

Since mutual funds don't have traditional volume, the platform adapts volume proxies:

- **AUM Change (Δ AUM):** Used as a proxy for "demand/volume" in the fund
- **SIP Inflow Data:** Net SIP inflows as a sentiment indicator
- **On-Balance AUM (OBA):** Cumulative AUM when NAV rises vs. falls (OBV equivalent)
- **Fund Flow Momentum:** Net FII+DII inflows weighted by sector exposure

### 4.5 Trend Indicators

**ADX (Average Directional Index):**
- ADX > 25: Strong trend; ADX < 20: Weak/ranging market
- Helps filter out false signals from RSI/MACD in sideways NAV movement

**Parabolic SAR:**
- Trailing stop-loss indicator; dots appear above (bearish) or below (bullish) NAV
- Configurable acceleration factor: 0.02 (default), 0.01 (conservative)

**Ichimoku Cloud:**
- Tenkan-sen (9-period), Kijun-sen (26-period), Senkou Span A & B, Chikou Span
- Cloud color: Green (bullish), Red (bearish)
- Best for medium-to-long-term trend confirmation in equity funds

### 4.6 Chart Engine

- TradingView Lightweight Charts library integration (or Chart.js for open-source)
- Candle, OHLC, Line, Area, and Mountain chart types for NAV
- Multi-timeframe support: Daily, Weekly, Monthly, Quarterly
- Annotation tools: Trendlines, horizontal levels, Fibonacci retracements
- Indicator panels: Up to 4 separate sub-panels below main NAV chart
- Export: PNG, PDF, or SVG of any chart configuration
- Saved chart templates per user

---

## 5. Risk Analysis Module

Inspired by the risk metrics used in the Random Forest project (Alpha, Beta, Sharpe, Std Dev, R-squared) and standard portfolio theory.

### 5.1 Core Risk Metrics

| Metric | Formula / Method | Benchmark |
|---|---|---|
| **Alpha (α)** | Fund Return − [Rf + β × (Rm − Rf)] | Nifty 50, Sensex, or category index |
| **Beta (β)** | Cov(Fund, Market) / Var(Market) | Nifty 50 or category index |
| **Sharpe Ratio** | (Rp − Rf) / σp | Annualized; Rf = 10-yr G-Sec yield |
| **Sortino Ratio** | (Rp − Rf) / σ_downside | Penalizes only downside deviation |
| **Treynor Ratio** | (Rp − Rf) / β | Risk per unit of market risk |
| **R-Squared** | Correlation² between fund & benchmark | 85–100 = closely tracks benchmark |
| **Standard Deviation** | Annualized from daily returns × √252 | Lower = less volatile |
| **Calmar Ratio** | Annualized Return / Max Drawdown | Higher = better risk-adjusted return |
| **Information Ratio** | Active Return / Tracking Error | Manager skill beyond benchmark |
| **Tracking Error** | Std Dev of (Fund Return − Benchmark Return) | Category average |

### 5.2 Drawdown Analysis

- **Maximum Drawdown:** Peak-to-trough decline over full history
- **Current Drawdown:** Distance from all-time high to current NAV
- **Drawdown Duration:** Number of days in current drawdown period
- **Recovery Factor:** Total return / Maximum drawdown
- **Underwater Chart:** Visual of drawdown depth over time

### 5.3 Value at Risk (VaR)

- **Historical VaR (95%, 99%):** Based on empirical return distribution
- **Parametric VaR:** Assumes normal distribution of returns
- **CVaR / Expected Shortfall:** Average loss beyond the VaR threshold
- Rolling VaR: 30-day window updated daily

### 5.4 Good Fund Scoring Criteria

Based on the Random Forest project's selection criteria from Investopedia research:

```
A GOOD FUND satisfies:
  ✅ R-Squared:       85 – 100  (high benchmark correlation)
  ✅ Alpha:           > 0       (positive excess return)
  ✅ Beta:            0.7 – 1.3 (moderate market sensitivity)
  ✅ Sharpe Ratio:    > 1.0     (good risk-adjusted return)
  ✅ Std Deviation:   Below category median
  ✅ Expense Ratio:   Below category median
  ✅ Max Drawdown:    < 20% for equity, < 5% for debt
```

A **composite Risk Score (0–100)** is computed per fund by normalizing and weighting these metrics. Funds are rated as: ⭐ Conservative, ⭐⭐ Moderate, ⭐⭐⭐ Aggressive.

### 5.5 Risk Comparison Views

- **Risk-Return Scatterplot:** All funds in a category plotted; ideal quadrant (high return, low risk) highlighted
- **Correlation Heatmap:** Within a user's watchlist or across category peers
- **Peer Benchmark Table:** Side-by-side risk metrics vs. category average and top-3 peers

### 5.6 Investment Horizon Risk Analysis

Inspired by the Random Forest project's 3/5/10-year investment models:

- Separate risk scores computed for 3-year, 5-year, and 10-year time windows
- Expense Ratio vs. Return scatter by horizon (identifies fee drag)
- Consistent performer tagging: Funds that rank in the top quartile across all three horizons

---

## 6. Time-Series Forecasting Suite

Inspired by the NayakwadiS time-series forecasting project and Satej-Zunjarrao's ARIMA implementation.

### 6.1 Forecasting Horizon Options

| Horizon | Primary Use Case | Recommended Models |
|---|---|---|
| **7-day** | Short-term tactical entry/exit | ARIMA, SARIMA, ETS |
| **30-day** | Monthly SIP timing | Prophet, LSTM, ARIMA |
| **90-day** | Quarterly review and rebalancing | Prophet, XGBoost, Random Forest |
| **1-year** | Annual SIP planning | LSTM, Gradient Boosting, Ensemble |

### 6.2 Classical Time-Series Models

**ARIMA (AutoRegressive Integrated Moving Average):**
- Grid search over (p, d, q) parameters: p ∈ {0..5}, d ∈ {0..2}, q ∈ {0..5}
- Selection by AIC (Akaike Information Criterion) minimization
- Stationarity test: Augmented Dickey-Fuller (ADF) test before fitting
- Differencing applied automatically if ADF p-value > 0.05
- Outputs: Point forecast + 80% & 95% confidence intervals

**SARIMA (Seasonal ARIMA):**
- Extends ARIMA with seasonal component (P, D, Q, m)
- Seasonal period m = 22 (monthly trading days) for monthly patterns
- Auto-SARIMA via `pmdarima` auto_arima() with stepwise search

**ETS (Exponential Smoothing State Space Model):**
- Additive or multiplicative trend and seasonality
- Best for funds with strong seasonal AUM patterns (tax-saving funds in March)
- Implemented via `statsmodels.tsa.holtwinters.ExponentialSmoothing`

**Facebook Prophet:**
- Handles missing values, holidays (NSE calendar), and regime changes
- Built-in Indian market holiday calendar
- Changepoint detection: Auto-detects regime shifts (e.g., COVID crash, policy changes)
- Regressors: Nifty 50 index, FII flow data, interest rate changes
- Outputs: Trend, weekly seasonality, yearly seasonality, holiday effects decomposed separately

### 6.3 Forecast Output Format

Each forecast generates:
- Point estimate per day in the horizon
- Confidence interval bands (80% and 95%)
- Predicted % return from current NAV
- Model accuracy score (MAPE from backtesting last 90 days)
- Comparison with all other models (ensemble view)

### 6.4 Model Evaluation & Backtesting

All models are evaluated using a walk-forward (expanding window) backtest:

| Metric | Description |
|---|---|
| **MAPE** | Mean Absolute Percentage Error (primary metric) |
| **RMSE** | Root Mean Squared Error |
| **MAE** | Mean Absolute Error |
| **SMAPE** | Symmetric MAPE (handles near-zero values better) |
| **Directional Accuracy** | % of times forecast correctly predicted up/down direction |

Backtest window: Last 180 days of NAV data held out; models trained on prior data only.

---

## 7. Machine Learning Forecasting Engine

### 7.1 Tree-Based Models

**Random Forest Regressor (and Classifier):**
Inspired by the rupeshmore85 Random Forest approach.

The Random Forest module runs two complementary analyses:

*Regression Mode:* Predicts future NAV values directly
- n_estimators: Grid search from 1 to 100 decision trees; accuracy vs. n_estimators boxplot shown to user
- Features: All lag features, rolling statistics, technical indicators (RSI, MACD, BB-width), macro features (Nifty 50 momentum, FII flows)
- Cross-Validation: 5-fold time-series CV (no data leakage — future data never used to train)
- Scoring: F1 for classification, RMSE for regression

*Classification Mode:* Predicts fund quality (Top / Mid / Poor)
- Target label: Funds ranked by composite score (Sharpe + Alpha + Drawdown) → Top 25% = Class 1, Bottom 25% = Class 0
- Separate models for 3-year, 5-year, and 10-year horizons
- Feature Importance plot: Bar chart of top 15 contributing features

**Gradient Boosting (XGBoost / LightGBM):**
- XGBoost for NAV prediction; LightGBM for speed on large fund universes
- Hyperparameter tuning via Optuna (Bayesian optimization)
- Early stopping on validation loss

**Decision Tree (baseline):**
- Used as baseline comparison; visualizable as explainable tree diagram

### 7.2 Deep Learning Models

**LSTM (Long Short-Term Memory):**
Implemented following the Satej-Zunjarrao LSTM approach.

Architecture:
```
Input Layer        → Sequence length: 60 days
LSTM Layer 1       → 128 units, return_sequences=True, dropout=0.2
LSTM Layer 2       → 64 units, return_sequences=False, dropout=0.2
Dense Layer 1      → 32 units, ReLU activation
Dense Layer 2      → 1 unit (NAV prediction) or N units (multi-step)
```

Training:
- Loss: Mean Squared Error (MSE)
- Optimizer: Adam (lr=0.001 with ReduceLROnPlateau scheduler)
- Batch size: 32; Epochs: up to 200 with EarlyStopping (patience=15)
- MinMaxScaler normalization: NAV scaled to [0, 1] before training
- Model saved to S3 as `.keras` file; loaded on prediction request

Multi-step LSTM: Predicts 30-day NAV sequence in one shot (many-to-many).

**Bidirectional LSTM:**
- Processes NAV sequence in both forward and backward directions
- Better at capturing long-range dependencies in NAV trends
- Particularly effective for funds with >5 years of history

**GRU (Gated Recurrent Unit):**
- Lighter alternative to LSTM; faster inference
- Used as fallback for schemes with < 3 years of NAV history

**Transformer (Attention-Based):**
- Self-attention over 90-day NAV windows
- Multi-head attention: 4 heads, d_model=64
- Suitable for capturing complex, non-linear NAV dynamics
- Available for Premium tier users only (compute-intensive)

### 7.3 Linear Models

**Linear Regression:**
- Baseline model; NAV predicted from lag features and rolling averages
- Ridge and Lasso variants for regularization
- Polynomial features (degree 2) for capturing curvature
- Visualizes coefficient magnitudes as feature importance

**Support Vector Regression (SVR):**
- RBF kernel; hyperparameters C and γ tuned via grid search
- Scales well on normalized NAV data

### 7.4 Ensemble / Model Stacking

**Weighted Ensemble:**
- All trained models produce a prediction
- Ensemble weight = proportional to (1 / MAPE) on validation set
- Final prediction = weighted average of all model predictions
- Ensemble typically outperforms any single model by 10–20% on MAPE

**Stacking Regressor:**
- Level-1 models: ARIMA, Random Forest, LSTM, XGBoost
- Level-2 meta-learner: Linear Regression on level-1 predictions
- Trained in a time-series cross-validated manner

### 7.5 Hyperparameter Tuning Pipeline

Inspired by `hyperparameter_tuning.py`:

- **Optuna** for Bayesian optimization (Tree-structured Parzen Estimator)
- **TimeSeriesSplit** for all CV splits (prevents data leakage)
- Tuning runs scheduled nightly on the top 500 funds by AUM
- Best parameters stored in PostgreSQL `model_config` table
- Dashboard shows tuning history (objective value vs. trial number)

---

## 8. Live NAV Estimation & Real-Time Tracking

Inspired by MFforecast.com's minute-by-minute NAV estimation during market hours.

### 8.1 How Live NAV Estimation Works

```
Step 1: Fetch fund's portfolio holdings (published monthly by AMC)
Step 2: Get real-time prices of all underlying stocks/bonds from NSE/BSE feed
Step 3: Compute estimated portfolio value:
         LiveNAV_est = Σ (holding_i × live_price_i) + cash_component
                       ─────────────────────────────────────────────
                                    units_outstanding
Step 4: Apply NAV smoothing (5-min EWMA to reduce noise)
Step 5: Publish to Redis pub/sub → WebSocket → client
```

### 8.2 Update Frequency & Coverage

- **Equity Funds:** Updated every 60 seconds during NSE/BSE market hours (9:15 AM – 3:30 PM IST)
- **Hybrid Funds:** Updated every 5 minutes (equity portion live, debt portion daily)
- **Debt Funds:** Updated at 15-minute intervals using bond price proxies
- **Index Funds / ETFs:** Near real-time tracking of the underlying index

### 8.3 Holdings Attribution Analysis

- **Stock-level attribution:** Which individual stocks contributed most to today's estimated NAV change
- **Sector attribution:** Sector-wise breakdown of NAV movement (e.g., "IT sector contributed +0.45% today")
- **Gainers/Losers Table:** Top 5 holdings helping NAV and top 5 dragging it, with % contribution
- **Heatmap View:** Portfolio holdings shown as a treemap sized by weight, colored by today's move

### 8.4 Market Hours Dashboard

- Live intra-day NAV chart (line chart updating every minute)
- Compare estimated NAV vs. previous official NAV (delta shown prominently)
- "Market Pulse" indicator: Bullish/Bearish/Neutral based on Nifty 50 and sector breadth
- Estimated return since last official NAV: `+0.23%` type display with color coding

---

## 9. TruthLens — Prediction Accuracy Tracker

Inspired directly by MFforecast.com's TruthLens feature — a radical transparency mechanism.

### 9.1 Core Concept

Every prediction made by the platform is recorded in a tamper-evident ledger. The next day, when AMFI publishes the official NAV, the platform automatically compares and publishes the accuracy score. Users can audit every prediction ever made.

### 9.2 TruthLens Ledger Schema

```
prediction_ledger
─────────────────
id                  UUID
scheme_code         VARCHAR (AMFI code)
scheme_name         VARCHAR
model_name          VARCHAR  (e.g., 'LSTM', 'ARIMA', 'Ensemble')
prediction_date     DATE     (date on which prediction was made)
prediction_for_date DATE     (date the prediction was for)
predicted_nav       DECIMAL(12, 4)
actual_nav          DECIMAL(12, 4)    (NULL until AMFI publishes)
absolute_error      DECIMAL(8, 4)     (|predicted − actual|)
percentage_error    DECIMAL(6, 4)     (|error| / actual × 100)
direction_correct   BOOLEAN           (predicted direction matches actual?)
verified_at         TIMESTAMP         (when AMFI NAV was ingested)
```

### 9.3 TruthLens Dashboard

- **Overall Accuracy Score:** Rolling 30-day average MAPE across all predictions and all funds
- **Per-Model Leaderboard:** Rank models by accuracy; updated daily
- **Per-Fund Accuracy:** Which fund categories are hardest to predict? (Sectoral > Large Cap > Debt)
- **Accuracy Trend Chart:** Was the model getting better or worse over time?
- **Direction Accuracy %:** Even if the magnitude is off, is the model calling up/down correctly?
- **Best / Worst Predictions of the Day:** Showcase and learn from outliers

### 9.4 User-Facing Display

On every forecast card:
```
┌─────────────────────────────────────────────────────────┐
│  Predicted NAV (Tomorrow): ₹ 58.24                      │
│  Model: Ensemble  |  Confidence: High (MAPE 1.2%)       │
│                                                         │
│  TruthLens Score for This Fund:                         │
│  ████████████░░  83% direction accuracy (last 30 days)  │
│  Avg Error: ±₹ 0.34  |  Avg % Error: 0.58%             │
└─────────────────────────────────────────────────────────┘
```

---

## 10. Fund Screener & Comparison Engine

### 10.1 Screener Filters

**Fundamental Filters:**
- Fund Category: Large Cap, Mid Cap, Small Cap, Flexi Cap, ELSS, Hybrid, Debt, Index, Sectoral, etc.
- Fund House (AMC): Filter by specific AMC
- AUM range: ₹ 100 Cr – ₹ 1,00,000 Cr+
- Expense Ratio: < 0.5%, < 1.0%, < 1.5%, < 2.0%, custom range
- Age of Fund: > 1 yr, > 3 yrs, > 5 yrs, > 10 yrs

**Return-Based Filters:**
- 1-week, 1-month, 3-month, 6-month, 1-year, 3-year, 5-year, 10-year, since inception
- Absolute return or CAGR
- Return vs. benchmark (excess return)
- SIP returns (XIRR)

**Risk-Based Filters:**
- Beta range: 0.5–0.8 (defensive), 0.8–1.2 (neutral), 1.2+ (aggressive)
- Sharpe Ratio: > 0.5, > 1.0, > 1.5, > 2.0
- Maximum Drawdown: < 10%, < 20%, < 30%
- Standard Deviation: < category mean, < 15%, custom range
- Alpha: > 0 (any positive alpha), > 1, > 2

**Technical Filters:**
- RSI range: e.g., RSI 30–50 (near oversold recovery zone)
- Position relative to SMA-200: Above (bullish), below (bearish)
- MACD Signal: Bullish crossover in last 5 days / 10 days
- Bollinger Band position: Near lower band (potential mean reversion)
- Trend strength (ADX): > 25 (strong trend)

**ML Forecast Filters:**
- Predicted 30-day return: > 1%, > 3%, > 5%
- Model confidence level: High only (MAPE < 1%)
- TruthLens accuracy: > 80% direction accuracy

### 10.2 Screener Output Table

Sortable columns: Fund Name, NAV, 1Y Return, 3Y CAGR, Sharpe, Beta, Expense Ratio, RSI, Predicted 30D Return, TruthLens Score.

**Saved Screeners:** Users can name and save any combination of filters for daily re-use.

### 10.3 Fund Comparison Engine

- Select up to 5 funds for side-by-side comparison
- Comparison dimensions:
  - NAV history chart (normalized to same base date)
  - Risk metrics table (all metrics listed in Section 5)
  - Rolling return comparison: 1M, 3M, 6M, 1Y, 3Y, 5Y
  - Expense ratio vs. return efficiency chart
  - Portfolio overlap percentage (if holdings data is available)
  - AI narrative: "Fund A has delivered higher alpha but with 30% more volatility than Fund B"

---

## 11. Portfolio Builder & Optimizer

### 11.1 SIP Simulator

- Input: Fund scheme, monthly SIP amount, start date, end date (or target date)
- Output: XIRR, total invested, current value, absolute return, CAGR
- Inflation-adjusted real return
- Step-up SIP simulation: Annual increment by fixed % or fixed amount
- Lump-sum + SIP combination modeling
- Visual: Investment vs. value chart over time (area chart)

### 11.2 Portfolio Optimizer (Modern Portfolio Theory)

Based on Markowitz Mean-Variance Optimization:

- **Inputs:** User's current or target fund selection (up to 10 funds)
- **Efficient Frontier Plot:** All possible portfolio combinations plotted; optimal Sharpe portfolio highlighted
- **Optimization Goals:**
  - Maximize Sharpe Ratio
  - Minimize Volatility for a target return
  - Maximize return for a given risk tolerance
- **Constraints:** Min/max allocation per fund (e.g., min 5%, max 40%)
- **Output:** Suggested allocation percentages per fund

### 11.3 Portfolio Health Check

- Overall portfolio Sharpe, Beta, Alpha vs. Nifty 50
- Sector concentration: Are you over-exposed to IT or Banking?
- Market cap bias: % in Large / Mid / Small cap
- Portfolio overlap warning: "You hold HDFC Flexi Cap and HDFC Mid Cap — 42% holding overlap"
- Rebalancing suggestions triggered if allocation drifts > 5% from target

### 11.4 Goal-Based Planning

- Retirement corpus calculator
- Child education planning
- Home purchase downpayment timeline
- Each goal links to recommended fund categories and SIP amounts

---

## 12. AI-Powered Insights Layer

Inspired by MFShala's AI health scores and plain-English fund explanations.

### 12.1 AI Fund Health Score

A composite score (0–100) per fund, updated daily:

```
Health Score = w1 × Return_Score
             + w2 × Risk_Score
             + w3 × Technical_Score
             + w4 × Manager_Score
             + w5 × Momentum_Score

Where weights are: 0.30, 0.25, 0.20, 0.15, 0.10
```

Displayed as a circular gauge with color: 🔴 < 40 | 🟡 40–70 | 🟢 > 70

### 12.2 Plain-English Fund Summary (LLM-Powered)

Using an LLM (e.g., GPT-4 API or a fine-tuned open-source model):

> "**Axis Bluechip Fund** is a large-cap equity fund that has been tracking broadly sideways for the past 6 weeks. The RSI is at 48 — neutral territory. Its 200-day SMA is trending upward, suggesting the medium-term trend remains intact. With a Sharpe of 1.3 and a Beta of 0.85, it offers decent risk-adjusted returns with slightly lower market sensitivity than average. Our LSTM model predicts a +1.8% return over the next 30 days with 76% TruthLens accuracy."

### 12.3 Market Mood Engine

A daily sentiment gauge derived from:
- FII/DII net flow data
- Nifty 50 ADX and RSI
- India VIX (volatility index)
- Breadth: % of Nifty 500 stocks above their 200-day SMA
- News sentiment (if NLP pipeline is added in Phase 2)

Output: **Fearful / Cautious / Neutral / Optimistic / Euphoric** with a numerical score and trend chart.

### 12.4 Sector-Wise AI Analysis

10 sectors tracked: IT, Banking & Finance, Pharma, FMCG, Auto, Energy, Infra, Real Estate, Metals, Consumption.

Per sector:
- Live performance today (% change in sector index)
- RSI of sector index (overbought/oversold signal)
- Funds with highest exposure to that sector
- AI verdict: "IT sector is showing exhaustion after a 15% rally; RSI at 72 — consider reducing sectoral exposure"

### 12.5 AI Chatbot Assistant

- Natural language queries: "Which large-cap fund has the best Sharpe ratio right now?"
- "Show me ELSS funds with positive alpha over 5 years"
- "Is my current portfolio well-diversified?"
- Powered by fine-tuned LLM with tool-calling to the platform's own APIs
- Conversation history maintained per user session

---

## 13. Interactive Dashboard & Visualization

Inspired by the Dash dashboard from `dashboard.py` and MFShala's terminal interface.

### 13.1 Home Dashboard

```
┌──────────────────────────────────────────────────────────────────────┐
│  MutualEdge Terminal                   [Market: OPEN ● 11:23 IST]   │
├──────────────┬──────────────────────────────┬────────────────────────┤
│  Market Mood │  Top Gainers Today            │  Top Losers Today      │
│  [OPTIMISTIC]│  1. HDFC Mid Cap +1.2%        │  1. SBI PSU Fund -0.8% │
│  VIX: 14.2   │  2. Mirae Emerging +0.9%      │  2. Invesco Energy -0.6%│
│  Nifty RSI:58│  3. Quant Small Cap +0.8%     │  3. UTI Pharma -0.4%   │
├──────────────┴──────────────────────────────┴────────────────────────┤
│  Your Watchlist                                         All Signals  │
│  Fund Name          NAV     Change   RSI   MACD   AI Score          │
│  Axis Bluechip      58.24   +0.23%   48    BULL   82/100            │
│  Mirae Emerging     98.12   +0.91%   61    BULL   79/100            │
│  HDFC Short Term    26.47   +0.03%   52    NEUT   71/100            │
└──────────────────────────────────────────────────────────────────────┘
```

### 13.2 Individual Fund Terminal

- Tab 1 — **Chart:** Full TradingView-style NAV chart with indicators
- Tab 2 — **Forecast:** All models' 30-day predictions in one overlay chart
- Tab 3 — **Risk:** Full risk metrics table + drawdown chart + VaR
- Tab 4 — **Holdings:** Sector attribution, top holdings, AUM heatmap
- Tab 5 — **TruthLens:** Historical prediction accuracy for this specific fund
- Tab 6 — **Compare:** Quick compare with up to 4 other funds

### 13.3 EDA Visualization Suite

Inspired by `eda_visualization.py`:

- **NAV Trend Chart:** Historical NAV with zoom and pan (1M, 3M, 6M, 1Y, 3Y, 5Y, MAX views)
- **Return Distribution Histogram:** Shape of daily return distribution; normal curve overlay
- **Rolling Return Heatmap:** Calendar heatmap (GitHub contribution graph style) showing monthly returns
- **Correlation Heatmap:** Between any selected set of funds
- **Rolling Volatility Chart:** 30-day rolling annualized volatility over NAV history
- **Benchmark Comparison:** Fund NAV indexed to 100 vs. Nifty 50 vs. category average
- **Feature Correlation Matrix:** Which features best predict future NAV (for ML transparency)

### 13.4 Model Forecast Dashboard

- Unified view of all model predictions for a selected fund
- Chart: Historical NAV + all model forecasts as differently colored lines
- Table: Next 7 / 30 / 90 days predicted NAV from each model with confidence intervals
- Model accuracy badge: Each model shows its last-90-day MAPE score
- "Best Model for This Fund" highlight: Auto-selected based on TruthLens history

### 13.5 Charts & Visualization Library

| Component | Library / Technology |
|---|---|
| NAV Charting (main) | Lightweight Charts (TradingView) or Apache ECharts |
| Technical Indicator Overlays | Custom Python → pre-computed values → JSON to frontend |
| Forecast Charts | Plotly.js (interactive, confidence bands) |
| Risk Scatter Plots | D3.js (efficient frontier, correlation heatmaps) |
| Portfolio Heatmaps | Highcharts Treemap or D3 |
| Calendar Heatmaps | Cal-HeatMap.js |
| Dashboard Layouts | React + Tailwind CSS + shadcn/ui components |

---

## 14. Alerts, Watchlist & Notifications

Inspired by MFShala's alert system.

### 14.1 Alert Types

| Alert Type | Trigger Condition | Channels |
|---|---|---|
| **RSI Alert** | RSI crosses user-defined threshold (e.g., RSI < 30) | Email, Push, WhatsApp |
| **MACD Crossover** | MACD line crosses Signal line (bullish or bearish) | Email, Push |
| **Price Level** | NAV crosses above/below a user-set value | Email, Push, SMS |
| **Moving Average Cross** | SMA-50 crosses SMA-200 (Golden/Death Cross) | Email, Push |
| **Drawdown Alert** | Fund falls X% from recent high | Email, Push |
| **Forecast Alert** | Model predicts > X% return or < Y% return in next 30 days | Email |
| **TruthLens Accuracy** | A fund's prediction accuracy drops below user threshold | Email |
| **AUM Change** | Fund AUM drops by > 20% MoM (potential fund stress) | Email |
| **New NAV Published** | AMFI publishes NAV; compare with prediction | Push |
| **Screener Match** | A new fund matches a saved screener | Email |

### 14.2 Watchlist

- Unlimited funds in watchlist (Free: up to 10; Premium: unlimited)
- Watchlist dashboard with real-time estimated NAV during market hours
- Drag-and-drop reordering; tag/group by strategy or goal
- Watchlist performance summary: Overall portfolio if invested equally across watchlist

### 14.3 Notification Infrastructure

- **Email:** SendGrid / AWS SES (HTML templates, daily digest option)
- **Push Notifications:** Firebase Cloud Messaging (FCM) for web and mobile
- **WhatsApp:** Twilio WhatsApp Business API (Premium tier)
- **Telegram Bot:** Optional bot integration for instant alerts

---

## 15. Automation & Retraining Pipeline

Inspired by `automation_pipeline.py` from the Satej-Zunjarrao project.

### 15.1 Daily Automation Schedule (IST)

| Time | Task |
|---|---|
| 9:00 PM | AMFI NAV published → ingest all NAV data |
| 9:15 PM | Update TruthLens ledger (actual vs. predicted comparison) |
| 9:30 PM | Recompute all technical indicators for all funds |
| 9:45 PM | Recompute all risk metrics (Sharpe, Beta, etc.) |
| 10:00 PM | Run ARIMA / Prophet / ETS forecasts for all funds |
| 10:30 PM | Run ML models (top 1,000 funds by AUM) |
| 11:00 PM | Publish new predictions to prediction_ledger |
| 11:15 PM | Update AI Fund Health Scores |
| 11:30 PM | Send scheduled email digests and alerts |
| 11:45 PM | Refresh Redis cache with updated data |
| 12:00 AM | Screener index rebuild |

### 15.2 Weekly Tasks

- Full model retraining (retrain from scratch on all available history)
- Hyperparameter re-optimization (Optuna) for top 100 funds by AUM
- Feature importance recalculation
- Portfolio holdings refresh (AMC publishes monthly; interim scraping)
- Expense ratio and metadata update from BSE StAR

### 15.3 Pipeline Orchestration

- **Celery** with Redis broker for task queuing and scheduling
- **Celery Beat** for cron-like scheduled tasks
- **Flower** monitoring dashboard for task health
- **Alerting:** If any pipeline task fails, PagerDuty / Slack alert to engineering team
- **Idempotency:** All pipeline tasks are idempotent (safe to re-run if failed)

### 15.4 Model Versioning

- Each trained model artifact saved to S3 with version tag: `lstm_v3.2_20250718.keras`
- Model registry in PostgreSQL: model_name, version, training_date, MAPE, status (active/shadow/retired)
- **Shadow Mode:** New model versions run alongside production model; predictions logged but not shown to users until they beat the incumbent by > 5% MAPE
- **Gradual Rollout:** New model shown to 10% of users first; full rollout if no regression

---

## 16. Technology Stack

### 16.1 Backend

| Component | Technology | Rationale |
|---|---|---|
| **API Framework** | FastAPI (Python) | Async, high performance, auto-docs |
| **Task Queue** | Celery + Redis | Async job processing, scheduling |
| **ML / Data Science** | Python (NumPy, Pandas, Scikit-learn) | Industry standard, extensive libraries |
| **Deep Learning** | TensorFlow / Keras, PyTorch | LSTM, Transformer models |
| **Time-Series ML** | `pmdarima`, `prophet`, `statsmodels` | ARIMA, SARIMA, Prophet |
| **Gradient Boosting** | XGBoost, LightGBM, CatBoost | Fast, accurate tree models |
| **Technical Analysis** | TA-Lib, `pandas-ta`, custom | RSI, MACD, BB, etc. |
| **Optimization** | SciPy, `cvxpy` | Markowitz portfolio optimization |
| **Hyperparameter Tuning** | Optuna | Bayesian optimization |
| **Data Validation** | Pydantic, Great Expectations | Schema enforcement, data quality |

### 16.2 Databases

| Store | Technology | Purpose |
|---|---|---|
| **Primary DB** | PostgreSQL 15+ | Historical NAV, users, predictions |
| **Time-Series DB** | InfluxDB 2.x | Live NAV tick data |
| **Cache** | Redis 7.x | API response cache, sessions, pub/sub |
| **Search** | Elasticsearch 8.x | Full-text fund search, screener queries |
| **Document Store** | MongoDB | Fund metadata, holdings documents |
| **Object Store** | AWS S3 / MinIO | Trained model files, chart exports |

### 16.3 Frontend

| Component | Technology |
|---|---|
| **Framework** | React 18 + TypeScript |
| **State Management** | Zustand or Redux Toolkit |
| **UI Components** | shadcn/ui + Tailwind CSS |
| **Charts** | TradingView Lightweight Charts + Plotly.js + ECharts |
| **Real-Time** | WebSocket (Socket.io or native WS) |
| **Mobile App** | React Native (shared business logic) |

### 16.4 Infrastructure & DevOps

| Component | Technology |
|---|---|
| **Container** | Docker + Docker Compose (dev), Kubernetes (prod) |
| **CI/CD** | GitHub Actions |
| **Cloud** | AWS (EC2, RDS, ElastiCache, S3, CloudFront) or GCP |
| **Monitoring** | Prometheus + Grafana (metrics), Sentry (errors) |
| **Logging** | ELK Stack (Elasticsearch + Logstash + Kibana) |
| **CDN** | AWS CloudFront |
| **DNS / SSL** | AWS Route 53 + ACM |

---

## 17. Database Schema Design

### 17.1 Core Tables (PostgreSQL)

```sql
-- Fund master table
CREATE TABLE funds (
    scheme_code         VARCHAR(20) PRIMARY KEY,   -- AMFI 5-digit code
    scheme_name         VARCHAR(255) NOT NULL,
    amc_name            VARCHAR(100),
    category            VARCHAR(50),               -- Large Cap, Mid Cap, etc.
    sub_category        VARCHAR(100),
    benchmark_index     VARCHAR(100),
    launch_date         DATE,
    aum_crores          DECIMAL(15, 2),
    expense_ratio       DECIMAL(5, 3),
    fund_manager        VARCHAR(255),
    isin_growth         VARCHAR(20),
    isin_dividend       VARCHAR(20),
    is_active           BOOLEAN DEFAULT TRUE,
    updated_at          TIMESTAMP DEFAULT NOW()
);

-- Historical NAV
CREATE TABLE nav_history (
    id                  BIGSERIAL PRIMARY KEY,
    scheme_code         VARCHAR(20) REFERENCES funds(scheme_code),
    nav_date            DATE NOT NULL,
    nav_value           DECIMAL(12, 4) NOT NULL,
    daily_return_pct    DECIMAL(8, 4),
    UNIQUE(scheme_code, nav_date)
);
CREATE INDEX idx_nav_history_scheme_date ON nav_history(scheme_code, nav_date DESC);

-- Technical indicators (pre-computed, stored for speed)
CREATE TABLE technical_indicators (
    id                  BIGSERIAL PRIMARY KEY,
    scheme_code         VARCHAR(20) REFERENCES funds(scheme_code),
    calc_date           DATE NOT NULL,
    rsi_14              DECIMAL(6, 2),
    macd_line           DECIMAL(10, 4),
    macd_signal         DECIMAL(10, 4),
    macd_histogram      DECIMAL(10, 4),
    bb_upper            DECIMAL(12, 4),
    bb_middle           DECIMAL(12, 4),
    bb_lower            DECIMAL(12, 4),
    bb_pct_b            DECIMAL(6, 4),
    sma_20              DECIMAL(12, 4),
    sma_50              DECIMAL(12, 4),
    sma_100             DECIMAL(12, 4),
    sma_200             DECIMAL(12, 4),
    ema_12              DECIMAL(12, 4),
    ema_26              DECIMAL(12, 4),
    adx_14              DECIMAL(6, 2),
    atr_14              DECIMAL(10, 4),
    stoch_k             DECIMAL(6, 2),
    stoch_d             DECIMAL(6, 2),
    UNIQUE(scheme_code, calc_date)
);

-- Risk metrics (computed over different windows)
CREATE TABLE risk_metrics (
    id                  BIGSERIAL PRIMARY KEY,
    scheme_code         VARCHAR(20) REFERENCES funds(scheme_code),
    calc_date           DATE NOT NULL,
    horizon_years       SMALLINT,                  -- 1, 3, 5, 10
    alpha               DECIMAL(8, 4),
    beta                DECIMAL(8, 4),
    sharpe_ratio        DECIMAL(8, 4),
    sortino_ratio       DECIMAL(8, 4),
    treynor_ratio       DECIMAL(8, 4),
    r_squared           DECIMAL(6, 4),
    std_deviation       DECIMAL(8, 4),
    max_drawdown        DECIMAL(8, 4),
    calmar_ratio        DECIMAL(8, 4),
    var_95              DECIMAL(8, 4),
    cvar_95             DECIMAL(8, 4),
    composite_risk_score SMALLINT,                -- 0-100
    UNIQUE(scheme_code, calc_date, horizon_years)
);

-- Prediction ledger (TruthLens)
CREATE TABLE prediction_ledger (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_code         VARCHAR(20) REFERENCES funds(scheme_code),
    model_name          VARCHAR(50),
    prediction_date     DATE NOT NULL,
    prediction_for_date DATE NOT NULL,
    predicted_nav       DECIMAL(12, 4),
    actual_nav          DECIMAL(12, 4),
    absolute_error      DECIMAL(10, 4),
    percentage_error    DECIMAL(8, 4),
    direction_correct   BOOLEAN,
    is_verified         BOOLEAN DEFAULT FALSE,
    verified_at         TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) UNIQUE NOT NULL,
    password_hash       VARCHAR(255),
    full_name           VARCHAR(255),
    plan                VARCHAR(20) DEFAULT 'free', -- free, pro, enterprise
    plan_expires_at     TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- User watchlist
CREATE TABLE watchlist (
    user_id             UUID REFERENCES users(id),
    scheme_code         VARCHAR(20) REFERENCES funds(scheme_code),
    added_at            TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, scheme_code)
);

-- User alerts
CREATE TABLE user_alerts (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES users(id),
    scheme_code         VARCHAR(20) REFERENCES funds(scheme_code),
    alert_type          VARCHAR(50),
    condition_operator  VARCHAR(10),               -- '>', '<', 'crosses_above'
    threshold_value     DECIMAL(12, 4),
    indicator           VARCHAR(50),               -- 'rsi', 'nav', 'macd', etc.
    channels            TEXT[],                    -- ['email', 'push']
    is_active           BOOLEAN DEFAULT TRUE,
    last_triggered_at   TIMESTAMP
);
```

---

## 18. API Design

### 18.1 Core Endpoints

```
Base URL: https://api.mutualedge.in/v1/

Authentication: Bearer JWT token in Authorization header

FUND DATA
──────────
GET  /funds                          List/search all funds (paginated)
GET  /funds/{scheme_code}            Fund metadata and latest snapshot
GET  /funds/{scheme_code}/nav        Historical NAV (with date range params)
GET  /funds/{scheme_code}/live       Live estimated NAV (real-time)
GET  /funds/{scheme_code}/holdings   Portfolio holdings breakdown

TECHNICAL ANALYSIS
──────────────────
GET  /funds/{scheme_code}/indicators         All indicators for latest date
GET  /funds/{scheme_code}/indicators/history  Historical indicator values
GET  /funds/{scheme_code}/chart              Chart-ready OHLC + indicator data

RISK METRICS
────────────
GET  /funds/{scheme_code}/risk               Risk metrics (all horizons)
GET  /funds/{scheme_code}/drawdown           Drawdown history
GET  /funds/{scheme_code}/comparison         Compare vs. peers + benchmark

FORECASTING
────────────
GET  /funds/{scheme_code}/forecast           Latest forecasts (all models)
GET  /funds/{scheme_code}/forecast/{model}   Specific model forecast
POST /funds/{scheme_code}/forecast/custom    Custom horizon forecast (Premium)

TRUTHLENS
──────────
GET  /truthlens/summary                      Platform-wide accuracy summary
GET  /truthlens/fund/{scheme_code}           Per-fund accuracy history
GET  /truthlens/leaderboard                  Model accuracy leaderboard

SCREENER
─────────
POST /screener                               Run screener with filter payload
GET  /screener/saved                         List user's saved screeners
POST /screener/saved                         Save a screener
GET  /screener/presets                       Platform-provided preset screeners

PORTFOLIO
──────────
POST /portfolio/optimize                     Run Markowitz optimization
POST /portfolio/sip-simulate                 SIP return simulation
POST /portfolio/health-check                 Portfolio health analysis

USER
─────
POST /auth/register
POST /auth/login
POST /auth/refresh
GET  /user/profile
GET  /user/watchlist
POST /user/watchlist
DELETE /user/watchlist/{scheme_code}
GET  /user/alerts
POST /user/alerts
DELETE /user/alerts/{id}
```

### 18.2 Websocket Endpoints

```
ws://api.mutualedge.in/ws/live-nav              Subscribe to live NAV updates
ws://api.mutualedge.in/ws/market-pulse          Market mood updates every 5 min
ws://api.mutualedge.in/ws/alerts/{user_id}      Personal alert notifications
```

---

## 19. UI/UX Blueprint

### 19.1 Navigation Structure

```
MutualEdge
├── Home Dashboard             (market overview, watchlist, mood)
├── Fund Terminal              (search → individual fund view)
│   ├── Chart (Technical Analysis)
│   ├── Forecast (All Models)
│   ├── Risk Analysis
│   ├── Holdings & Attribution
│   ├── TruthLens Score
│   └── Compare
├── Screener
│   ├── Filter Builder
│   ├── Results Table
│   └── Saved Screeners
├── Forecasts Hub
│   ├── Top Predicted Gainers (30-day)
│   ├── Model Comparison
│   └── TruthLens Ledger
├── Portfolio
│   ├── My Holdings
│   ├── SIP Simulator
│   ├── Portfolio Optimizer
│   └── Goal Planner
├── Market Intelligence
│   ├── Sector Heatmap
│   ├── FII/DII Flows
│   ├── Market Mood
│   └── AI Insights Feed
├── Watchlist
└── Settings / Alerts
```

### 19.2 Design Principles

- **Dark mode by default** (financial terminal aesthetic)
- **Data density:** Show maximum data without clutter; inspired by Bloomberg terminal UX
- **Color coding:** Green = positive / bullish, Red = negative / bearish, Yellow = neutral / caution
- **Progressive disclosure:** Summary card → click for detail → click for drill-down
- **Mobile-first:** All core features accessible on phone; heavy analysis on desktop
- **Accessibility:** WCAG 2.1 AA compliance; screen reader friendly charts

---

## 20. Deployment Strategy

### 20.1 Environment Architecture

```
Development  →  Staging  →  Production (Blue-Green)
                               │
                       AWS Multi-AZ
                    (ap-south-1 primary,
                     ap-southeast-1 standby)
```

### 20.2 Kubernetes Deployment (Production)

```
Namespace: mutualedge-prod
──────────────────────────
Deployments:
  api-gateway             2 replicas (HPA: 2–10)
  data-ingestion-service  1 replica  (CronJob for scheduled ingestion)
  forecast-service        2 replicas (GPU node pool for LSTM inference)
  live-nav-service        3 replicas (HPA: 3–20, spikes during market open)
  notification-service    1 replica
  frontend                3 replicas (static, served via CloudFront)

Services:
  PostgreSQL              AWS RDS Multi-AZ (r6g.xlarge)
  Redis                   AWS ElastiCache (cluster mode)
  Kafka                   AWS MSK (2 brokers)
  Elasticsearch           AWS OpenSearch (3 nodes)
  InfluxDB                Self-hosted on EBS-backed EC2
```

### 20.3 Scaling Strategy

- **Live NAV Service:** Auto-scales 3× before market open (9:00 AM IST) and scales down after market close
- **Forecast Service:** GPU instances (g4dn.xlarge) for overnight batch; spot instances to reduce cost
- **Database:** Read replicas for historical NAV queries; primary only for writes

---

## 21. Monetization & Access Tiers

| Feature | Free | Pro (₹499/mo) | Enterprise (₹2,499/mo) |
|---|---|---|---|
| Funds tracked | 10 | Unlimited (37,000+) | Unlimited |
| Technical indicators | 3 (RSI, SMA, MACD) | All 15+ | All + custom |
| Forecasting models | 1 (ARIMA) | All models + Ensemble | All + Transformer |
| Forecast horizon | 7 days | 90 days | 1 year |
| TruthLens access | Summary only | Full ledger | Full + export |
| Screener filters | 5 | All filters | All + ML filters |
| Watchlist size | 10 funds | Unlimited | Unlimited |
| Alerts | 2 alerts | 50 alerts | Unlimited |
| Portfolio optimizer | — | Markowitz | Markowitz + Black-Litterman |
| Live NAV estimates | — | ✅ | ✅ |
| AI fund summaries | — | ✅ | ✅ |
| API access | — | — | ✅ (rate limited) |
| Data export (CSV) | — | ✅ | ✅ |
| WhatsApp alerts | — | — | ✅ |

---

## 22. Compliance & Disclaimers

### 22.1 SEBI / AMFI Compliance

- Platform must be **AMFI-registered** (ARN holder) if providing investment advice
- All NAV data sourced from AMFI's official published NAV — cannot be altered or misrepresented
- Fund house names, scheme names, and logos used under fair use / informational purpose
- Required disclaimer on all pages: *"MutualEdge is an educational and analytical tool. Predictions are not investment advice. Mutual fund investments are subject to market risks. Please read all scheme-related documents carefully before investing."*

### 22.2 Prediction Disclaimers

- Every forecast page must clearly state the model's historical MAPE
- TruthLens accuracy prominently shown alongside every prediction
- Language: "Estimated" and "Predicted" — never "Guaranteed" or "Assured"
- Users must accept terms acknowledging the educational nature during signup

### 22.3 Data Privacy

- User data governed by India's DPDP Act 2023
- No selling of user data to third parties
- Models trained on aggregated NAV data — no user-personal data used in training
- HTTPS-only; all PII encrypted at rest (AES-256) and in transit (TLS 1.3)

---

## Appendix A: Phase-Wise Rollout Plan

| Phase | Duration | Deliverables |
|---|---|---|
| **Phase 1 — Core** | Months 1–3 | Data ingestion, historical NAV, ARIMA + Linear Regression forecasts, basic RSI/SMA/MACD charts, fund screener (fundamental filters only), TruthLens MVP |
| **Phase 2 — ML** | Months 4–6 | LSTM + Random Forest + XGBoost models, full technical indicator suite (all 15+), Risk module (all metrics), Portfolio SIP simulator, Ensemble forecasting |
| **Phase 3 — Live** | Months 7–9 | Live NAV estimation (equity funds), real-time dashboard, sector heatmap, WebSocket infrastructure, WhatsApp / Push alerts |
| **Phase 4 — AI** | Months 10–12 | LLM-powered fund summaries, AI Health Score, Market Mood engine, Portfolio optimizer (Markowitz), AI chatbot, Transformer forecasting model |
| **Phase 5 — Scale** | Month 13+ | Mobile app, API tier, Enterprise features, Black-Litterman optimizer, news sentiment NLP, international fund expansion |

---

## Appendix B: Key Libraries & References

```
Data & Analysis:
  mftool                  # Python wrapper for AMFI NAV API
  pandas, numpy           # Core data manipulation
  pandas-ta, ta-lib       # Technical indicators
  scipy, cvxpy            # Portfolio optimization

Time-Series Forecasting:
  statsmodels             # ARIMA, ETS, SARIMA
  pmdarima                # Auto-ARIMA
  prophet (Meta)          # Facebook Prophet
  neuralprophet           # Neural network enhanced Prophet

Machine Learning:
  scikit-learn            # Linear Regression, SVR, cross-validation
  xgboost, lightgbm       # Gradient boosting
  optuna                  # Hyperparameter optimization

Deep Learning:
  tensorflow / keras      # LSTM, GRU, Bidirectional LSTM
  torch                   # Transformer model (optional)

Visualization:
  plotly, dash            # Interactive charts & dashboards
  matplotlib, seaborn     # Static analysis plots

Infrastructure:
  fastapi, uvicorn        # API server
  celery, redis           # Task queue & cache
  sqlalchemy              # ORM for PostgreSQL
  kafka-python            # Message streaming
```

---

*Blueprint prepared for MutualEdge — Mutual Fund Intelligence Platform*
*Version 1.0 | July 2025*
*Sources: Satej-Zunjarrao/Mutual-Fund-Performance-Forecasting, NayakwadiS/Forecasting_Mutual_Funds, MFforecast.com, MFShala.in, rupeshmore85 Random Forest Analytics, Investopedia Technical Indicators Framework*
