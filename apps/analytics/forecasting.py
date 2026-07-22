"""
apps/analytics/forecasting.py
Mutual Fund NAV Forecasting Engine

Three analysis modes, all stateless (no DB writes):
  1. Return/NAV Forecasting  - ARIMA, Holt-ETS, Linear, Momentum, MA
  2. Direction Forecasting   - Logistic Regression, MA Crossover, RSI/MACD Ensemble
  3. Volatility Forecasting  - GARCH(1,1), EWMA, Rolling Std
"""

import warnings
import numpy as np
from datetime import timedelta, datetime
from collections import Counter

warnings.filterwarnings("ignore")


def _log_returns(prices):
    p = np.asarray(prices, dtype=float)
    return np.diff(np.log(np.where(p <= 0, 1e-9, p)))


def _rolling(arr, w, fn):
    out = np.full(len(arr), np.nan)
    for i in range(w - 1, len(arr)):
        out[i] = fn(arr[i - w + 1: i + 1])
    return out


def _nav_to_dates_nav(nav_data):
    if not nav_data:
        return [], np.array([])
    if isinstance(nav_data[0], dict):
        dates = [d["date"] for d in nav_data]
        navs = np.array([float(d["nav"]) for d in nav_data])
    else:
        dates = [str(i) for i in range(len(nav_data))]
        navs = np.array([float(v) for v in nav_data])
    return dates, navs


def _future_dates(last_date_str, horizon):
    try:
        last = datetime.strptime(str(last_date_str)[:10], "%Y-%m-%d")
    except Exception:
        last = datetime.today()
    out = []
    d = last
    for _ in range(horizon):
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append(d.strftime("%Y-%m-%d"))
    return out


def _rsi_series(navs, period=14):
    navs = np.asarray(navs, dtype=float)
    rets = np.diff(navs)
    rsi = np.full(len(navs), np.nan)
    if len(rets) < period:
        return rsi
    gains = np.where(rets > 0, rets, 0.0)
    losses = np.where(rets < 0, -rets, 0.0)
    ag = np.mean(gains[:period])
    al = np.mean(losses[:period])
    for i in range(period, len(rets)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        rs = ag / al if al else np.inf
        rsi[i + 1] = 100 - 100 / (1 + rs)
    return rsi


def _ema_series(arr, span):
    arr = np.asarray(arr, dtype=float)
    alpha = 2 / (span + 1)
    out = np.full(len(arr), np.nan)
    first_valid = next((i for i, v in enumerate(arr) if not np.isnan(v)), None)
    if first_valid is None:
        return out
    out[first_valid] = arr[first_valid]
    for i in range(first_valid + 1, len(arr)):
        if np.isnan(arr[i]):
            out[i] = out[i - 1]
        else:
            out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


# ── Mode 1: Return / NAV Forecasting ──────────────────────────────────────────

def _linear_forecast(navs, horizon):
    W = min(60, len(navs))
    sl = np.asarray(navs[-W:], dtype=float)
    xs = np.arange(len(sl), dtype=float)
    slope, intercept = np.polyfit(xs, sl, 1)
    preds = slope * (np.arange(len(sl), len(sl) + horizon, dtype=float)) + intercept
    resid = sl - (slope * xs + intercept)
    return {"name": "Linear Trend", "colour": "#6366f1", "preds": preds.tolist(), "sigma": float(np.std(resid)), "end_nav": float(preds[-1])}


def _holt_forecast(navs, horizon, alpha=0.3, beta=0.15):
    L = float(navs[0])
    T = float(navs[1] - navs[0]) if len(navs) > 1 else 0.0
    fitted = []
    for v in navs[1:]:
        pL, pT = L, T
        L = alpha * v + (1 - alpha) * (pL + pT)
        T = beta * (L - pL) + (1 - beta) * pT
        fitted.append(L + T)
    preds = [L + (i + 1) * T for i in range(horizon)]
    resid = np.array(navs[1:len(fitted) + 1]) - np.array(fitted)
    return {"name": "Holt Smoothing", "colour": "#10b981", "preds": preds, "sigma": float(np.std(resid)), "end_nav": float(preds[-1])}


def _momentum_forecast(navs, horizon):
    W = min(21, len(navs) - 1)
    roc = (navs[-1] - navs[-1 - W]) / navs[-1 - W]
    dr = (1 + roc) ** (1 / W) - 1
    preds, last = [], float(navs[-1])
    for _ in range(horizon):
        last *= 1 + dr
        preds.append(last)
    lr = _log_returns(navs[-30:]) if len(navs) >= 30 else _log_returns(navs)
    return {"name": "Momentum", "colour": "#f59e0b", "preds": preds, "sigma": float(np.std(lr) * navs[-1]), "end_nav": float(preds[-1])}


def _naive_forecast(navs, horizon):
    last = float(navs[-1])
    lr = _log_returns(navs) if len(navs) > 1 else [0]
    return {"name": "Naive (Last Value)", "colour": "#94a3b8", "preds": [last] * horizon, "sigma": float(np.std(lr) * last), "end_nav": last}


def _ma_forecast(navs, horizon, window=20):
    W = min(window, len(navs))
    lr = _log_returns(navs[-W - 1:]) if len(navs) > W else _log_returns(navs)
    mean_ret = float(np.mean(lr))
    last = float(navs[-1])
    preds = []
    for _ in range(horizon):
        last = last * np.exp(mean_ret)
        preds.append(last)
    return {"name": f"MA({W}) Forecast", "colour": "#ec4899", "preds": preds, "sigma": float(np.std(lr) * navs[-1]), "end_nav": float(preds[-1])}


def _arima_forecast(navs, horizon, p=2, d=1, q=1):
    try:
        from statsmodels.tsa.arima.model import ARIMA
        model = ARIMA(navs, order=(p, d, q))
        fit = model.fit()
        fc = fit.forecast(steps=horizon)
        return {"name": f"ARIMA({p},{d},{q})", "colour": "#8b5cf6", "preds": fc.tolist(), "sigma": float(np.std(fit.resid)), "end_nav": float(fc.iloc[-1]), "aic": float(fit.aic), "bic": float(fit.bic)}
    except Exception as e:
        r = _holt_forecast(navs, horizon)
        r["name"] = f"ARIMA({p},{d},{q}) [fallback]"
        r["error"] = str(e)
        return r


def _ets_forecast(navs, horizon):
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(navs, trend="add", seasonal=None, initialization_method="estimated")
        fit = model.fit(optimized=True)
        preds = fit.forecast(horizon).tolist()
        return {"name": "ETS (Additive)", "colour": "#06b6d4", "preds": preds, "sigma": float(np.std(fit.resid)), "end_nav": float(preds[-1])}
    except Exception as e:
        r = _holt_forecast(navs, horizon)
        r["name"] = "ETS [fallback]"
        r["error"] = str(e)
        return r


def _walk_forward_backtest(navs, model_fn, horizon=1, window=90):
    n = len(navs)
    start = max(30, n - window - 1)
    mape_sum = dir_sum = rmse_sum = cnt = 0
    for i in range(start, n - 1):
        try:
            result = model_fn(navs[:i + 1], horizon)
            pred = result["preds"][0]
            actual = navs[i + 1]
            if actual and actual != 0:
                mape_sum += abs(actual - pred) / abs(actual)
                rmse_sum += (actual - pred) ** 2
                dir_sum += int((pred > navs[i]) == (actual > navs[i]))
                cnt += 1
        except Exception:
            continue
    if cnt == 0:
        return {"mape": None, "rmse": None, "dir_acc": None, "n": 0}
    return {"mape": round(mape_sum / cnt * 100, 3), "rmse": round((rmse_sum / cnt) ** 0.5, 4), "dir_acc": round(dir_sum / cnt * 100, 1), "n": cnt}


def run_return_forecast(nav_data, params):
    dates, navs = _nav_to_dates_nav(nav_data)
    if len(navs) < 30:
        return {"error": "Need at least 30 NAV data points"}

    horizon    = int(params.get("horizon", 30))
    models_req = params.get("models", ["arima", "holt", "linear", "momentum"])
    arima_p    = int(params.get("arima_p", 2))
    arima_d    = int(params.get("arima_d", 1))
    arima_q    = int(params.get("arima_q", 1))
    ma_window  = int(params.get("ma_window", 20))
    bt_window  = int(params.get("backtest_window", 90))

    hist_count  = min(180, len(navs))
    future_dates = _future_dates(dates[-1], horizon)
    last_nav    = float(navs[-1])

    model_map = {
        "arima":    lambda n, h: _arima_forecast(n, h, arima_p, arima_d, arima_q),
        "holt":     _holt_forecast,
        "linear":   _linear_forecast,
        "momentum": _momentum_forecast,
        "ma":       lambda n, h: _ma_forecast(n, h, ma_window),
        "ets":      _ets_forecast,
        "naive":    _naive_forecast,
    }

    results = []
    for mkey in models_req:
        if mkey not in model_map:
            continue
        fn = model_map[mkey]
        try:
            r = fn(navs.tolist(), horizon)
        except Exception as e:
            r = {"name": mkey, "error": str(e), "preds": [], "sigma": 0, "end_nav": last_nav}

        chg = (r["end_nav"] - last_nav) / last_nav * 100 if last_nav else 0
        bt = _walk_forward_backtest(navs.tolist(), fn, horizon=1, window=bt_window)

        results.append({
            "key": mkey,
            "name": r["name"],
            "colour": r.get("colour", "#64748b"),
            "end_nav": round(r["end_nav"], 4),
            "change_pct": round(chg, 2),
            "sigma": round(r.get("sigma", 0), 4),
            "preds": [round(v, 4) for v in r["preds"]],
            "aic": r.get("aic"),
            "bic": r.get("bic"),
            "backtest": bt,
            "error": r.get("error"),
        })

    return {
        "hist_dates": dates[-hist_count:],
        "hist_navs": [round(v, 4) for v in navs[-hist_count:].tolist()],
        "future_dates": future_dates,
        "last_nav": round(last_nav, 4),
        "models": results,
    }


# ── Mode 2: Direction Forecasting ─────────────────────────────────────────────

def _direction_label(log_ret, threshold=0.002):
    if log_ret > threshold: return 1
    if log_ret < -threshold: return -1
    return 0


def run_direction_forecast(nav_data, params):
    dates, navs = _nav_to_dates_nav(nav_data)
    if len(navs) < 60:
        return {"error": "Need at least 60 NAV data points"}

    threshold = float(params.get("threshold_pct", 0.3)) / 100
    rsi_p  = int(params.get("rsi_period", 14))
    ma_s   = int(params.get("ma_short", 10))
    ma_l   = int(params.get("ma_long", 30))
    lags   = [1, 3, 5, 10, 20]

    log_ret = _log_returns(navs.tolist())
    rsi_vals = _rsi_series(navs, rsi_p)
    ema_s_v = _ema_series(navs, ma_s)
    ema_l_v = _ema_series(navs, ma_l)
    macd_line = ema_s_v - ema_l_v
    macd_sig_v = _ema_series(np.where(np.isnan(macd_line), 0, macd_line), 9)
    ema12 = _ema_series(navs, 12)
    ema26 = _ema_series(navs, 26)

    n = len(log_ret)
    max_lag = max(lags)

    rows, labels = [], []
    for i in range(max_lag, n - 1):
        row = {}
        for lag in lags:
            row[f"ret_lag{lag}"] = float(log_ret[i - lag])
        row["roll_mean5"] = float(np.mean(log_ret[max(0, i-5):i]))
        row["roll_std5"]  = float(np.std(log_ret[max(0, i-5):i]) or 1e-9)
        rsi_i = rsi_vals[i + 1] if not np.isnan(rsi_vals[i + 1]) else 50.0
        row["rsi"]       = float(rsi_i)
        row["macd"]      = float(macd_line[i+1]) if not np.isnan(macd_line[i+1]) else 0.0
        row["macd_hist"] = float((macd_line - macd_sig_v)[i+1]) if not np.isnan(macd_line[i+1]) else 0.0
        row["ma_cross"]  = float(ema_s_v[i+1] - ema_l_v[i+1]) if not np.isnan(ema_s_v[i+1]) else 0.0
        rows.append(row)
        labels.append(_direction_label(log_ret[i + 1], threshold))

    if len(rows) < 30:
        return {"error": "Not enough features to train"}

    feat_keys = list(rows[0].keys())
    X = np.array([[r[k] for k in feat_keys] for r in rows])
    y = np.array(labels)

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    mu    = X_train.mean(axis=0)
    sigma = X_train.std(axis=0) + 1e-9
    X_train_s = (X_train - mu) / sigma
    X_test_s  = (X_test  - mu) / sigma

    model_results = []
    label_map    = {1: "Up", -1: "Down", 0: "Flat"}
    label_colour = {1: "#10b981", -1: "#ef4444", 0: "#f59e0b"}

    # Logistic Regression
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, f1_score
        lr = LogisticRegression(max_iter=1000, C=1.0)
        lr.fit(X_train_s, y_train)
        y_pred = lr.predict(X_test_s)
        acc = float(accuracy_score(y_test, y_pred))
        f1  = float(f1_score(y_test, y_pred, average="macro", zero_division=0))

        x_cur = np.array([[rows[-1][k] for k in feat_keys]])
        x_cur_s = (x_cur - mu) / sigma
        proba = lr.predict_proba(x_cur_s)[0]
        classes = lr.classes_.tolist()
        pred_class = int(lr.predict(x_cur_s)[0])

        importance = []
        for ci, cls in enumerate(classes):
            if cls == pred_class:
                coefs = lr.coef_[ci] if len(lr.coef_) > 1 else lr.coef_[0]
                importance = sorted(zip(feat_keys, coefs.tolist()), key=lambda x: abs(x[1]), reverse=True)[:8]
                break

        model_results.append({
            "name": "Logistic Regression",
            "pred": pred_class,
            "pred_label": label_map.get(pred_class, "?"),
            "pred_colour": label_colour.get(pred_class, "#94a3b8"),
            "proba": {label_map.get(int(c),"?"): round(float(p), 3) for c, p in zip(classes, proba)},
            "accuracy": round(acc * 100, 1),
            "f1": round(f1, 3),
            "feature_importance": [(k, round(v, 4)) for k, v in importance],
        })
    except Exception as e:
        model_results.append({"name": "Logistic Regression", "error": str(e)})

    # MA Crossover
    try:
        cross = float(ema_s_v[-1] - ema_l_v[-1])
        prev  = float(ema_s_v[-2] - ema_l_v[-2])
        if cross > 0 and prev <= 0: ma_pred = 1
        elif cross < 0 and prev >= 0: ma_pred = -1
        elif cross > 0: ma_pred = 1
        else: ma_pred = -1

        correct = total = 0
        for i in range(max(ma_s, ma_l) + 1, len(navs) - 1):
            sig = 1 if ema_s_v[i] > ema_l_v[i] else -1
            actual_dir = 1 if navs[i+1] > navs[i] else -1
            if sig == actual_dir: correct += 1
            total += 1
        ma_acc = round(correct / total * 100, 1) if total else 0

        model_results.append({
            "name": f"MA Crossover (EMA{ma_s}/EMA{ma_l})",
            "pred": ma_pred,
            "pred_label": label_map.get(ma_pred, "?"),
            "pred_colour": label_colour.get(ma_pred, "#94a3b8"),
            "accuracy": ma_acc,
        })
    except Exception as e:
        model_results.append({"name": "MA Crossover", "error": str(e)})

    # RSI + MACD Ensemble
    try:
        rsi_cur  = float(rsi_vals[-1]) if not np.isnan(rsi_vals[-1]) else 50.0
        macd_h   = float((macd_line - macd_sig_v)[-1]) if not np.isnan(macd_line[-1]) else 0.0
        ema12_cur = ema12[-1]; ema26_cur = ema26[-1]

        score = 0
        if rsi_cur < 30: score += 2
        elif rsi_cur < 50: score += 1
        elif rsi_cur > 70: score -= 2
        elif rsi_cur > 55: score -= 1
        if macd_h > 0: score += 1
        else: score -= 1
        rec_ret = float(np.mean(log_ret[-5:])) if len(log_ret) >= 5 else 0
        if rec_ret > 0: score += 1
        else: score -= 1
        if not np.isnan(ema12_cur) and not np.isnan(ema26_cur):
            if ema12_cur > ema26_cur: score += 1
            else: score -= 1

        ens_pred = 1 if score >= 2 else (-1 if score <= -2 else 0)
        model_results.append({
            "name": "RSI + MACD Ensemble",
            "pred": ens_pred,
            "pred_label": label_map.get(ens_pred, "?"),
            "pred_colour": label_colour.get(ens_pred, "#94a3b8"),
            "score": score,
            "rsi": round(rsi_cur, 2),
            "macd_hist": round(macd_h, 6),
        })
    except Exception as e:
        model_results.append({"name": "RSI+MACD Ensemble", "error": str(e)})

    votes = [r.get("pred") for r in model_results if "pred" in r]
    vote_counts = Counter(votes)
    overall_pred = vote_counts.most_common(1)[0][0] if vote_counts else 0

    return {
        "models": model_results,
        "overall_pred": overall_pred,
        "overall_label": label_map.get(overall_pred, "?"),
        "overall_colour": label_colour.get(overall_pred, "#94a3b8"),
        "vote_counts": {label_map.get(k, "?"): v for k, v in vote_counts.items()},
    }


# ── Mode 3: Volatility Forecasting ────────────────────────────────────────────

def _ewma_vol(returns, lam=0.94):
    out = np.full(len(returns), np.nan)
    if len(returns) < 2:
        return out
    out[0] = returns[0] ** 2
    for i in range(1, len(returns)):
        out[i] = lam * out[i - 1] + (1 - lam) * returns[i] ** 2
    return np.sqrt(np.maximum(out, 0))


def _garch11_series(returns, alpha=0.1, beta=0.85):
    try:
        from arch import arch_model
        scaled = returns * 100
        model = arch_model(scaled, vol="Garch", p=1, q=1, mean="Zero", dist="Normal")
        fit = model.fit(disp="off", show_warning=False)
        cond_vol = (fit.conditional_volatility / 100).tolist()
        params = {
            "omega": round(float(fit.params.get("omega", 0)), 8),
            "alpha": round(float(fit.params.get("alpha[1]", alpha)), 4),
            "beta":  round(float(fit.params.get("beta[1]", beta)), 4),
            "aic": round(float(fit.aic), 2),
        }
        fc = fit.forecast(horizon=1)
        next_vol = float(fc.variance.values[-1, 0] ** 0.5) / 100
        return cond_vol, params, next_vol
    except Exception:
        var0 = float(np.var(returns))
        omega = var0 * (1 - alpha - beta) if (alpha + beta) < 1 else 1e-6
        h = np.full(len(returns), var0)
        for i in range(1, len(returns)):
            h[i] = omega + alpha * returns[i-1]**2 + beta * h[i-1]
        cond_vol = np.sqrt(np.maximum(h, 0)).tolist()
        next_vol = float((omega + alpha * returns[-1]**2 + beta * h[-1]) ** 0.5)
        return cond_vol, {"omega": round(omega, 8), "alpha": alpha, "beta": beta, "note": "fixed params"}, next_vol


def run_volatility_forecast(nav_data, params):
    dates, navs = _nav_to_dates_nav(nav_data)
    if len(navs) < 30:
        return {"error": "Need at least 30 NAV data points"}

    roll_w   = int(params.get("roll_window", 20))
    lam      = float(params.get("ewma_lambda", 0.94))
    g_alpha  = float(params.get("garch_alpha", 0.1))
    g_beta   = float(params.get("garch_beta", 0.85))
    annualise = bool(params.get("annualise", True))
    horizon  = int(params.get("horizon", 30))

    log_ret = _log_returns(navs.tolist())
    n = len(log_ret)
    scale = np.sqrt(252) if annualise else 1.0

    roll_vol   = _rolling(log_ret, roll_w, np.std)
    ewma       = _ewma_vol(log_ret, lam=lam)
    garch_cond, garch_params, garch_next = _garch11_series(log_ret, g_alpha, g_beta)

    cur_roll  = float(roll_vol[-1]) * scale if not np.isnan(roll_vol[-1]) else None
    cur_ewma  = float(ewma[-1]) * scale if not np.isnan(ewma[-1]) else None
    cur_garch = garch_next * scale

    avg_6m = float(np.nanmean(roll_vol[-min(120, n):])) * scale
    regime = ("High Volatility" if (cur_roll or 0) > avg_6m * 1.3 else
              ("Low Volatility"  if (cur_roll or 0) < avg_6m * 0.7 else "Normal"))

    future_dates = _future_dates(dates[-1], horizon)
    v = cur_ewma or avg_6m
    forward_vol = []
    for _ in range(horizon):
        v = v + 0.02 * (avg_6m - v)
        forward_vol.append(round(float(v), 4))

    hist_count = min(252, n)
    tail = -hist_count

    def safe_list(arr):
        return [round(float(v), 6) if v is not None and not np.isnan(v) else None for v in arr]

    return {
        "hist_dates": dates[-hist_count - 1:-1],
        "roll_vol":   safe_list(roll_vol[tail:] * scale),
        "ewma_vol":   safe_list(ewma[tail:] * scale),
        "garch_vol":  safe_list([v * scale for v in garch_cond[tail:]]),
        "future_dates": future_dates,
        "forward_vol": forward_vol,
        "current": {
            "rolling": round(cur_roll, 4) if cur_roll else None,
            "ewma": round(cur_ewma, 4) if cur_ewma else None,
            "garch": round(cur_garch, 4),
        },
        "garch_params": garch_params,
        "regime": regime,
        "avg_vol_6m": round(avg_6m, 4),
        "annualised": annualise,
    }
