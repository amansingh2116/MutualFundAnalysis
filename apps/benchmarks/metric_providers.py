"""apps/benchmarks/metric_providers.py -- Market metric providers for the enhanced strip."""
from __future__ import annotations
import logging
import re
import requests
from datetime import datetime, timedelta, date as dt_date
import pandas as pd
from django.core.cache import cache
logger = logging.getLogger("mfanalysis")
TTL_PRICES=15*60; TTL_COMPUTED=30*60; TTL_FRED=6*3600
TTL_VALUATION=6*3600; TTL_NSE_SENTIMENT=3600; TTL_AMFI=24*3600
TECHNICAL_KEYS = {"nifty_rsi","nifty_macd","nifty_bb_pct","nifty_dma","nifty_dist_52wh","nifty_dist_ath","midcap_rs"}
FRED_KEYS = {"cpi_india","fed_funds","repo_rate"}
VALUATION_KEYS = {"nifty_pe","nifty_pb","nifty_dy","earnings_yield_gap","buffett_india"}
NSE_SENTIMENT_KEYS = {"nifty_pcr","fii_net","adv_dec","sip_inflows"}
METRIC_CATALOGUE = {
    "nifty50":  {"label":"NIFTY 50","category":"index","unit":"","ticker":"^NSEI","threshold":"Broad market index","tooltip_what":"Nifty 50 is the flagship Indian equity index comprising 50 large-cap stocks.","tooltip_interp":"Primary benchmark for Indian equity mutual funds. Directional moves indicate broad market health."},
    "sensex":   {"label":"SENSEX","category":"index","unit":"","ticker":"^BSESN","threshold":"BSE 30-stock index","tooltip_what":"S&P BSE SENSEX is the oldest and most widely followed Indian equity index.","tooltip_interp":"Tracks 30 large well-established financially sound companies listed on BSE."},
    "nifty200": {"label":"NIFTY 200","category":"index","unit":"","ticker":"^CNX200","threshold":"Top 200 stocks by market cap","tooltip_what":"Nifty 200 covers the top 200 companies by full market capitalisation.","tooltip_interp":"Broader than Nifty 50 — includes large and upper-mid cap. Good proxy for diversified large+mid exposure."},
    "midcap":   {"label":"NIFTY MIDCAP 150","category":"index","unit":"","ticker":"NIFTYMIDCAP150.NS","threshold":"Mid cap index","tooltip_what":"Nifty Midcap 150 tracks 150 mid-cap companies (rank 101-250 by market cap).","tooltip_interp":"Outperforms large cap in bull markets; higher drawdown in bear markets. Used as benchmark for mid-cap funds."},
    "smallcap": {"label":"NIFTY SMLCAP 250","category":"index","unit":"","ticker":"NIFTYSMLCAP250.NS","threshold":"Small cap index","tooltip_what":"Nifty Smallcap 250 tracks 250 small-cap companies (rank 251-500 by market cap).","tooltip_interp":"High-growth but high-risk segment. Benchmark for small-cap mutual funds. Watch for liquidity risk in bear markets."},
    "usdinr":   {"label":"USD/INR","category":"macro","unit":"Rs.","ticker":"USDINR=X","threshold":">5% YoY depreciation = headwind","tooltip_what":"USD/INR exchange rate — how many Indian rupees per US dollar.","tooltip_interp":"Stable or appreciating INR: FII inflows supported, import inflation low. Depreciating >5% YoY: FII exit pressure and higher import costs rise, hurting CAD."},
    "india_vix":{"label":"India VIX","category":"sentiment","unit":"","ticker":"^INDIAVIX","threshold":"<12 complacent | 12-20 normal | >20 fear | >30 panic","tooltip_what":"India VIX is the volatility index of Indian markets, measuring implied volatility of Nifty 50 options.","tooltip_interp":"VIX below 12: Markets complacent, rally may be overextended. VIX 12-20: Normal range. VIX above 20: Fear elevated, mean-reversion buying zone. VIX above 30: Panic mode, often marks short-term bottoms."},
    "nifty_rsi":{"label":"Nifty RSI(14)","category":"technical","unit":"","threshold":"<30 oversold | 30-70 neutral | >70 overbought","tooltip_what":"14-day Relative Strength Index on Nifty 50 daily closing prices.","tooltip_interp":"RSI below 40: Approaching oversold, mean-reversion lump sum zone. RSI 40-70: Neutral. RSI above 70: Overbought, avoid fresh large lump sum."},
    "nifty_macd":{"label":"Nifty MACD","category":"technical","unit":"","threshold":"Histogram positive = bullish | negative = bearish","tooltip_what":"MACD(12,26,9) histogram on Nifty 50. Measures convergence/divergence of 12-day and 26-day EMAs.","tooltip_interp":"MACD crosses above signal line: momentum turning positive. Positive expanding histogram: trend strengthening. Negative histogram: momentum weakening."},
    "nifty_bb_pct":{"label":"Nifty BB %B","category":"technical","unit":"%","threshold":"<20 oversold zone | 20-80 normal | >80 extended","tooltip_what":"Bollinger Bands %B on Nifty 50 (20-day, 2 standard deviation bands). Shows where price is within the bands.","tooltip_interp":"%B below 20: Price near lower band, mean-reversion opportunity zone. %B above 80: Price near upper band, possible pullback zone."},
    "nifty_dma": {"label":"Nifty 50/200 DMA","category":"technical","unit":"%","threshold":"Positive gap = Golden Cross bullish | Negative = Death Cross bearish","tooltip_what":"Gap between 50-day and 200-day Simple Moving Average on Nifty 50, expressed as % of the 200-day SMA.","tooltip_interp":"Positive (Golden Cross): Structural uptrend confirmed. Negative (Death Cross): Structural downtrend signal."},
    "nifty_dist_52wh":{"label":"Nifty Dist 52W High","category":"technical","unit":"%","threshold":">10% mild dip | >20% correction | >30% bear market","tooltip_what":"Percentage drawdown of Nifty 50 from its 52-week high.","tooltip_interp":"Market more than 20% below 52-week high: Meaningful correction, strong SIP step-up zone."},
    "nifty_dist_ath":{"label":"Nifty Dist from ATH","category":"technical","unit":"%","threshold":">20% off ATH = significant correction zone worth watching","tooltip_what":"Percentage drawdown of Nifty 50 from its all-time high (full available history, not just 1 year).","tooltip_interp":"Deep ATH drawdowns above 30% have historically been excellent long-term entry points."},
    "midcap_rs": {"label":"MidCap/LargeCap RS","category":"technical","unit":"x","threshold":">1 midcap outperforming | <1 large cap leading","tooltip_what":"6-month relative strength: Nifty Midcap 150 total return divided by Nifty 50 total return.","tooltip_interp":"RS above 1: Risk-on, consider mid cap allocation. RS below 1: Risk-off, prefer large cap funds."},
    "repo_rate":{"label":"India 10Y Yield","category":"macro","unit":"%","threshold":"<6.5% bond-friendly | 6.5-7% neutral | >7% equity headwind","tooltip_what":"India Long-Term Government Bond Yield: 10-Year (OECD). Source: FRED series INDIRLTLT01STM. Monthly data.","tooltip_interp":"Rising 10Y yield: bond prices fall, borrowing costs rise, equity valuations compress. Falling yield: equity-positive, long-duration debt funds benefit. Earnings yield gap = (1/Nifty PE) − this rate."},
    "cpi_india":{"label":"India CPI (YoY)","category":"macro","unit":"%","threshold":"<4% favorable | 4-6% neutral | >6% adverse (triggers rate hikes)","tooltip_what":"India Consumer Price Index YoY inflation. RBI targets 4%±2%. Source: FRED series INDCPIALLMINMEI.","tooltip_interp":"CPI 2-5%: RBI likely on hold or cutting, equity-friendly. CPI above 6%: Triggers rate hikes, headwind for equities and long-duration debt."},
    "us_vix":   {"label":"US VIX","category":"global","unit":"","ticker":"^VIX","threshold":"<15 risk-on globally | 15-25 normal | >25 fear | >35 crisis","tooltip_what":"CBOE Volatility Index, the global fear gauge. Primary driver of FII risk appetite and EM capital flows.","tooltip_interp":"VIX below 15: Global risk-on, FII inflows to India likely. VIX above 25: Global risk-off, FII outflows. VIX above 35: Crisis mode, historically a medium-term buying opportunity."},
    "dxy":      {"label":"DXY","category":"global","unit":"","ticker":"DX-Y.NYB","threshold":"<100 EM-friendly | 100-105 neutral | >105 significant headwind for EM","tooltip_what":"US Dollar Index measuring USD against a basket of 6 major currencies.","tooltip_interp":"DXY below 100: Dollar soft, EM inflows, INR relatively stable. DXY above 105: Dollar strong, EM capital outflows, INR weakens."},
    "us10y":    {"label":"US 10Y Yield","category":"global","unit":"%","ticker":"^TNX","threshold":"Rising above 4.5% = dollar rally = EM headwind","tooltip_what":"US 10-year Treasury yield. The global risk-free benchmark affecting EM equity valuations.","tooltip_interp":"Falling UST yield: Dollar softens, EM flows improve. Rising above 4.5%: Dollar rises, FII exits India."},
    "brent":    {"label":"Brent Crude","category":"global","unit":"USD","ticker":"BZ=F","threshold":"<70 favorable | 70-90 neutral | >90 headwind (USD/barrel)","tooltip_what":"Brent crude oil price in USD per barrel. India imports ~85% of crude oil.","tooltip_interp":"Crude below 70: Inflation low, CAD improves, equity positive. Crude above 90: Inflation risk, CAD widens."},
    "gold":     {"label":"Gold","category":"global","unit":"USD","ticker":"GC=F","threshold":"Rising sharply = global risk-off | Flat or falling = risk-on","tooltip_what":"Gold spot price in USD per troy ounce. Inverse risk barometer — rising gold signals global flight to safety.","tooltip_interp":"Gold sharply rising: flight to safety underway, equity caution globally. Gold flat or falling: global risk appetite is healthy."},
    "sp500":    {"label":"S&P 500","category":"global","unit":"","ticker":"^GSPC","threshold":"Above 200-day SMA = global risk-on | Below 200-day = caution","tooltip_what":"S&P 500 index. India equity markets correlate ~0.5 with S&P 500 over time.","tooltip_interp":"US in uptrend: global risk appetite high, India likely to perform well. US bear market: India selloff highly likely within 1-3 months."},
    "nasdaq":   {"label":"NASDAQ","category":"global","unit":"","ticker":"^IXIC","threshold":"Tech proxy most relevant for Indian IT and technology fund investors","tooltip_what":"NASDAQ Composite index tracking US technology and growth stocks.","tooltip_interp":"NASDAQ selloff often precedes IT sector underperformance in India by 3-6 months."},
    "fed_funds":{"label":"Fed Funds Rate","category":"global","unit":"%","threshold":"Cutting cycle = EM inflows | Hiking cycle = EM outflows","tooltip_what":"US Federal Funds Rate. Source: FRED series FEDFUNDS.","tooltip_interp":"Fed cutting cycle: Dollar weakens, EM inflows improve. Fed hiking cycle: Dollar strengthens, EM outflows."},
    # ── Valuation metrics ────────────────────────────────────────────────────────
    "nifty_pe":{"label":"Nifty 50 PE","category":"valuation","unit":"x","threshold":"<18 cheap | 18-24 fair | >24 expensive | >28 frothy","tooltip_what":"Nifty 50 trailing Price-to-Earnings ratio. Source: NSE India (nsepython).","tooltip_interp":"PE < 18: Historically cheap — strong long-term entry. PE 18-24: Fair value zone, keep SIPs running. PE > 24: Expensive — avoid large lump sums. PE > 28: Extreme overvaluation, consider trimming equity allocation."},
    "nifty_pb":{"label":"Nifty 50 PB","category":"valuation","unit":"x","threshold":"<2.5 cheap | 2.5-3.5 fair | >3.5 premium | >4 very expensive","tooltip_what":"Nifty 50 Price-to-Book ratio: market price vs net asset value per share. Source: NSE India.","tooltip_interp":"PB < 2.5: Assets undervalued relative to market. PB 2.5-3.5: Normal range for Indian large caps. PB > 4: Premium priced — suitable only for quality compounder strategy with long horizon."},
    "nifty_dy":{"label":"Nifty Div Yield","category":"valuation","unit":"%","threshold":">2% high yield | 1.2-2% fair | <1.2% growth priced in","tooltip_what":"Nifty 50 trailing dividend yield: annual dividends paid as % of total market cap. Source: NSE India.","tooltip_interp":"High yield (>2%): Market depressed, value zone. Low yield (<1.2%): Markets priced for growth; low margin of safety."},
    "earnings_yield_gap":{"label":"EY–Bond Gap","category":"valuation","unit":"%","threshold":">2% equity cheap vs bonds | 0-2% fair | <0% bonds more attractive","tooltip_what":"Earnings Yield (1/PE × 100%) minus India 10-Year G-Sec Yield. Positive gap = equities cheaper than bonds.","tooltip_interp":"Gap > 2%: Strong case for equities over bonds. Gap 0-2%: Equities fairly valued vs bonds. Gap < 0%: Risk-free rate exceeds earnings yield — bonds offer better risk-adjusted return. Requires FRED API key for the 10Y rate."},
    "buffett_india":{"label":"Buffett Indicator","category":"valuation","unit":"%","threshold":"<75% undervalued | 75-100% fair | >100% expensive | >120% significantly overvalued","tooltip_what":"India stock market capitalisation as % of GDP. Source: World Bank (annual data via wbgapi). Named after Warren Buffett's preferred valuation yardstick.","tooltip_interp":"Below 75%: Equities cheap vs economic output — strong long-term buy signal. 75-100%: Fairly valued. Above 100%: Expensive — be selective. Above 120%: Extreme overvaluation, reduce equity allocation."},
    # ── Sentiment metrics (NSE-sourced) ──────────────────────────────────────────
    "nifty_pcr":{"label":"Nifty PCR","category":"sentiment","unit":"","threshold":"<0.7 overbought | 0.7-1.1 neutral | >1.1 oversold/contrarian-bullish","tooltip_what":"Nifty Put/Call Ratio by Open Interest: total PE OI ÷ total CE OI. Source: NSE option chain.","tooltip_interp":"PCR < 0.7: Excessive call buying — overconfidence/overbought. PCR > 1.1: Excessive put buying — fear/oversold — contrarian bullish signal."},
    "fii_net":{"label":"FII Net (₹Cr)","category":"sentiment","unit":"Cr","threshold":"Positive = FII buying | Negative = FII selling | >₹5,000Cr moves are significant","tooltip_what":"Foreign Institutional Investor net activity in Indian equities for the latest trading session (Buy minus Sell). Source: NSE India. In ₹ Crores.","tooltip_interp":"Large FII buying: foreign confidence in India, index support. Large FII selling: global risk-off or INR weakness driving outflows."},
    "adv_dec":{"label":"Advance/Decline","category":"sentiment","unit":"x","threshold":">1.5 broad rally | 0.8-1.5 mixed | <0.8 broad decline","tooltip_what":"Ratio of advancing to declining stocks on NSE (Nifty 500 breadth). Source: NSE India.","tooltip_interp":"A/D > 2: Strong broad-based rally with healthy breadth. A/D < 0.5: Broad decline — most stocks falling even if indices are flat. Index moves are misleading when A/D diverges."},
    "sip_inflows":{"label":"SIP Inflows","category":"sentiment","unit":"Cr","threshold":"Growing trend = healthy retail participation | >₹20,000Cr/month excellent","tooltip_what":"Monthly SIP (Systematic Investment Plan) inflows into Indian mutual funds in ₹ Crores. Source: AMFI. Monthly figure — cached 24 hours.","tooltip_interp":"Rising SIP inflows: retail investor confidence growing, provides systematic buying support ('SIP cushion'). Falling inflows: retail redemption pressure may amplify market declines."},
}
FUND_METRIC_DEFS = {
    "1d_return":     {"label":"1D Return","unit":"%","tooltip_what":"Fund NAV change from previous working day to today's NAV.","tooltip_interp":"Shows daily price movement. Compare against benchmark 1D return for outperformance on any given day."},
    "rolling_3y":    {"label":"Rolling 3Y Return","unit":"%","tooltip_what":"Average 3-year rolling CAGR computed from the fund NAV history.","tooltip_interp":"Higher is better. Compare against benchmark and category peers for the same rolling period."},
    "dist_ath":      {"label":"Fund Dist from ATH","unit":"%","tooltip_what":"Fund NAV drawdown from its all-time high.","tooltip_interp":"Deeper drawdown may signal value opportunity if the fund fundamentals remain strong. High drawdown with poor alpha is a red flag."},
    "max_drawdown":  {"label":"Max Drawdown","unit":"%","tooltip_what":"Largest peak-to-trough NAV decline in the past 3 years.","tooltip_interp":"Closer to zero is better. High max drawdown means longer recovery period needed. Compare to category median."},
    "sharpe_3y":     {"label":"Sharpe (3Y)","unit":"","tooltip_what":"3-year Sharpe ratio: (annualised return minus risk-free rate) divided by annualised standard deviation.","tooltip_interp":"Above 1 is good, above 2 is excellent, below 0.5 is poor. Compare within the same fund category."},
    "sortino_3y":    {"label":"Sortino (3Y)","unit":"","tooltip_what":"Like Sharpe but only penalises downside volatility, not upside volatility. Better metric for equity funds.","tooltip_interp":"Above 1 is good, above 2 is excellent. Sortino higher than Sharpe means better upside-to-downside ratio."},
    "alpha_3y":      {"label":"Alpha (3Y)","unit":"%","tooltip_what":"Annualised excess return above what beta alone would predict (Jensen Alpha).","tooltip_interp":"Positive alpha means the fund manager is adding genuine value. Negative alpha means active fees with no benefit."},
    "beta_3y":       {"label":"Beta (3Y)","unit":"x","tooltip_what":"Sensitivity of fund NAV to Nifty 50 benchmark movements over 3 years.","tooltip_interp":"Below 0.8 is defensive, 0.8-1.2 is market-like, above 1.2 is aggressive."},
    "tracking_error":{"label":"Tracking Error","unit":"%","tooltip_what":"Annualised standard deviation of the fund return minus benchmark return.","tooltip_interp":"Low TE for index funds means tight replication. High TE for active funds is normal; pair with alpha to judge quality."},
    "expense_ratio": {"label":"Expense Ratio","unit":"%","tooltip_what":"Total Expense Ratio charged by the fund annually as percentage of AUM.","tooltip_interp":"Lower is always better. 0.5% saved over 20 years on Rs 10 lakh compounds to Rs 3.5 lakh extra corpus."},
}

BENCHMARK_METRIC_DEFS = {
    "1d_return":   {"label":"1D Return","unit":"%","tooltip_what":"Index change from previous trading day.","tooltip_interp":"Shows daily index movement. Useful for comparing fund 1D return against its benchmark."},
    "rolling_3y":  {"label":"Rolling 3Y Return","unit":"%","tooltip_what":"Average 3-year rolling CAGR computed from the index NAV history stored in the database.","tooltip_interp":"Compare against active funds to assess whether they are outperforming their benchmark over rolling windows."},
    "dist_ath":    {"label":"Index Dist from ATH","unit":"%","tooltip_what":"Percentage drawdown of the index from its all-time high.","tooltip_interp":"Deep ATH drawdowns have historically been excellent long-term entry points for index investors."},
    "max_drawdown":{"label":"Max Drawdown (3Y)","unit":"%","tooltip_what":"Largest peak-to-trough drawdown over the past 3 years.","tooltip_interp":"Closer to zero is better. Useful for comparing risk-adjusted drawdown across indices."},
}

def _ok(label,category,unit,value,change=None,change_pct=None,direction=None,signal=None,threshold=""):
    if direction is None:
        direction="up" if (change or 0)>=0 else "down"
    return {"label":label,"category":category,"unit":unit,"value":value,"change":change,
            "change_pct":change_pct,"direction":direction,"signal":signal,"threshold":threshold,
            "stale":False,"error":None}

def _na(label,category,unit,error="Data unavailable",threshold=""):
    return {"label":label,"category":category,"unit":unit,"value":None,"change":None,
            "change_pct":None,"direction":"neutral","signal":None,"threshold":threshold,
            "stale":True,"error":error}

def _stub(key):
    c=METRIC_CATALOGUE.get(key,{})
    return _na(c.get("label",key),c.get("category",""),c.get("unit",""),threshold=c.get("threshold",""))

def _rsi(closes,period=14):
    delta=closes.diff(); up=delta.clip(lower=0); down=-delta.clip(upper=0)
    rs=up.ewm(com=period-1,adjust=False).mean()/down.ewm(com=period-1,adjust=False).mean()
    return float(100-100/(1+rs.iloc[-1]))

def _macd_hist(closes):
    e12=closes.ewm(span=12,adjust=False).mean(); e26=closes.ewm(span=26,adjust=False).mean()
    macd=e12-e26; return float((macd-macd.ewm(span=9,adjust=False).mean()).iloc[-1])

def _bb_pct_b(closes,period=20):
    ma=closes.rolling(period).mean(); std=closes.rolling(period).std()
    upper=ma+2*std; lower=ma-2*std
    p=closes.iloc[-1]; u=float(upper.iloc[-1]); lo=float(lower.iloc[-1])
    return (p-lo)/(u-lo)*100 if u!=lo else 50.0


def _fetch_price_metrics():
    ck="mkt_price:v4"; cached=cache.get(ck)
    if cached: return cached
    try:
        import yfinance as yf
        from apps.benchmarks.registry import configure_yfinance_cache
        configure_yfinance_cache(yf)
        ticker_to_key={}
        for key,meta in METRIC_CATALOGUE.items():
            t=meta.get("ticker")
            if t and key not in TECHNICAL_KEYS and key not in FRED_KEYS:
                ticker_to_key[t]=key
        tickers=list(ticker_to_key.keys())
        data=yf.download(tickers,period="5d",interval="1d",auto_adjust=True,progress=False,threads=True)
        results={}
        for ticker,key in ticker_to_key.items():
            meta=METRIC_CATALOGUE[key]
            try:
                if isinstance(data.columns,pd.MultiIndex):
                    col=("Close",ticker)
                    if col not in data.columns: results[key]=_stub(key); continue
                    closes=pd.to_numeric(data[col],errors="coerce").dropna()
                else:
                    closes=pd.to_numeric(data["Close"],errors="coerce").dropna()
                if len(closes)>=2:
                    val=float(closes.iloc[-1]); prev=float(closes.iloc[-2])
                    chg=val-prev; pct=(chg/prev)*100 if prev else 0.0
                elif len(closes)==1:
                    val,chg,pct=float(closes.iloc[-1]),0.0,0.0
                else:
                    results[key]=_stub(key); continue
                results[key]=_ok(meta["label"],meta["category"],meta.get("unit",""),
                                  round(val,4),round(chg,4),round(pct,3),
                                  threshold=meta.get("threshold",""))
            except Exception as exc:
                logger.warning("price %s: %s",key,exc); results[key]=_stub(key)
        cache.set(ck,results,TTL_PRICES); return results
    except Exception as exc:
        logger.error("price batch: %s",exc); return {}


def _fetch_technical_metrics():
    ck="mkt_tech:v4"; cached=cache.get(ck)
    if cached: return cached
    try:
        import yfinance as yf
        from apps.benchmarks.registry import configure_yfinance_cache
        configure_yfinance_cache(yf)
        nifty=yf.download("^NSEI",period="3y",interval="1d",auto_adjust=True,progress=False)
        mid=yf.download("NIFTYMIDCAP150.NS",period="6mo",interval="1d",auto_adjust=True,progress=False)
        results={}
        if not nifty.empty and len(nifty)>=50:
            closes=pd.to_numeric(nifty["Close"].squeeze(),errors="coerce").dropna()
            try:
                v=_rsi(closes)
                results["nifty_rsi"]=_ok("Nifty RSI(14)","technical","",round(v,1),
                    signal="oversold" if v<30 else("overbought" if v>70 else "neutral"),
                    threshold=METRIC_CATALOGUE["nifty_rsi"]["threshold"])
            except: results["nifty_rsi"]=_stub("nifty_rsi")
            try:
                v=_macd_hist(closes)
                results["nifty_macd"]=_ok("Nifty MACD","technical","",round(v,2),
                    signal="bullish" if v>0 else "bearish",
                    threshold=METRIC_CATALOGUE["nifty_macd"]["threshold"])
            except: results["nifty_macd"]=_stub("nifty_macd")
            try:
                v=_bb_pct_b(closes)
                results["nifty_bb_pct"]=_ok("Nifty BB %B","technical","%",round(v,1),
                    signal="oversold" if v<20 else("overbought" if v>80 else "neutral"),
                    threshold=METRIC_CATALOGUE["nifty_bb_pct"]["threshold"])
            except: results["nifty_bb_pct"]=_stub("nifty_bb_pct")
            try:
                if len(closes)>=200:
                    s50=float(closes.rolling(50).mean().iloc[-1]); s200=float(closes.rolling(200).mean().iloc[-1])
                    gap=(s50-s200)/s200*100
                    results["nifty_dma"]=_ok(METRIC_CATALOGUE["nifty_dma"]["label"],"technical","%",round(gap,2),
                        signal="bullish" if s50>s200 else "bearish",
                        threshold=METRIC_CATALOGUE["nifty_dma"]["threshold"])
                else: results["nifty_dma"]=_stub("nifty_dma")
            except: results["nifty_dma"]=_stub("nifty_dma")
            try:
                recent=closes.iloc[-252:]; high52=float(recent.max()); last=float(closes.iloc[-1])
                dist=(last-high52)/high52*100
                results["nifty_dist_52wh"]=_ok(METRIC_CATALOGUE["nifty_dist_52wh"]["label"],"technical","%",round(dist,2),
                    signal="bullish" if dist<-20 else("bearish" if dist>-5 else "neutral"),
                    threshold=METRIC_CATALOGUE["nifty_dist_52wh"]["threshold"])
            except: results["nifty_dist_52wh"]=_stub("nifty_dist_52wh")
            try:
                ath=float(closes.max()); last=float(closes.iloc[-1]); dist=(last-ath)/ath*100
                results["nifty_dist_ath"]=_ok(METRIC_CATALOGUE["nifty_dist_ath"]["label"],"technical","%",round(dist,2),
                    signal="bullish" if dist<-20 else "neutral",
                    threshold=METRIC_CATALOGUE["nifty_dist_ath"]["threshold"])
            except: results["nifty_dist_ath"]=_stub("nifty_dist_ath")
        else:
            for k in ("nifty_rsi","nifty_macd","nifty_bb_pct","nifty_dma","nifty_dist_52wh","nifty_dist_ath"):
                results[k]=_stub(k)
        try:
            if not nifty.empty and not mid.empty:
                nc=pd.to_numeric(nifty["Close"].squeeze(),errors="coerce").dropna().iloc[-126:]
                mc=pd.to_numeric(mid["Close"].squeeze(),errors="coerce").dropna().iloc[-126:]
                if len(nc)>=60 and len(mc)>=60:
                    nr=nc.iloc[-1]/nc.iloc[0]-1; mr=mc.iloc[-1]/mc.iloc[0]-1
                    rs=(1+mr)/(1+nr)
                    results["midcap_rs"]=_ok("MidCap/LargeCap RS","technical","x",round(float(rs),3),
                        signal="bullish" if rs>1 else "bearish",
                        threshold=METRIC_CATALOGUE["midcap_rs"]["threshold"])
                else: results["midcap_rs"]=_stub("midcap_rs")
            else: results["midcap_rs"]=_stub("midcap_rs")
        except: results["midcap_rs"]=_stub("midcap_rs")
        cache.set(ck,results,TTL_COMPUTED); return results
    except Exception as exc:
        logger.error("technicals: %s",exc); return {k:_stub(k) for k in TECHNICAL_KEYS}


def _get_fred_key_info(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None, "MISSING"
    try:
        from apps.benchmarks.models import UserAPIKey
        obj = UserAPIKey.objects.filter(user=user, provider="fred").first()
        if not obj or not obj.api_key:
            return None, "MISSING"
        if not obj.is_valid:
            return obj.api_key, "INVALID"
        return obj.api_key, "VALID"
    except Exception as exc:
        logger.warning("_get_fred_key_info error: %s", exc)
        return None, "MISSING"

FRED_SERIES = {
    "cpi_india": ("INDCPIALLMINMEI", "India CPI (YoY)", "macro", "%"),
    "fed_funds": ("FEDFUNDS", "Fed Funds Rate", "global", "%"),
    "repo_rate": ("INDIRLTLT01STM", "India 10Y Yield", "macro", "%")
}

def _fetch_fred_metrics(user=None):
    api_key, status = _get_fred_key_info(user)
    if status == "MISSING":
        return {
            k: {**_stub(k), "error": "FRED API Key Required: Add a free FRED API key in Settings/Manage Strip.", "fred_status": "MISSING"}
            for k in FRED_KEYS
        }
    elif status == "INVALID":
        return {
            k: {**_stub(k), "error": "Valid FRED API Key Required: Your FRED API key is invalid. Update in Settings/Manage Strip.", "fred_status": "INVALID"}
            for k in FRED_KEYS
        }
    ck = "mkt_fred:v4:{}".format(getattr(user, "id", "anon"))
    cached = cache.get(ck)
    if cached:
        return cached
    results = {}
    try:
        from fredapi import Fred
        fred = Fred(api_key=api_key)
        for key, (sid, label, category, unit) in FRED_SERIES.items():
            try:
                s = fred.get_series(sid, observation_start="2020-01-01").dropna()
                if s.empty:
                    results[key] = {**_stub(key), "error": "FRED returned no data for key. Add a valid FRED API key.", "fred_status": "INVALID"}
                    continue
                val = float(s.iloc[-1])
                prev = float(s.iloc[-2]) if len(s) >= 2 else val
                chg = val - prev
                pct = (chg / abs(prev)) * 100 if prev else 0.0
                results[key] = {**_ok(label, category, unit, round(val, 3), round(chg, 3), round(pct, 2), threshold=METRIC_CATALOGUE.get(key, {}).get("threshold", "")), "fred_status": "VALID"}
            except Exception as e:
                logger.warning("FRED %s: %s", sid, e)
                results[key] = {**_stub(key), "error": "FRED API error or invalid key. Update FRED API key.", "fred_status": "INVALID"}
    except Exception as exc:
        logger.error("FRED: %s", exc)
        for k in FRED_KEYS:
            results[k] = {**_stub(k), "error": "FRED error: {}. Update FRED API key.".format(exc), "fred_status": "INVALID"}
    cache.set(ck, results, TTL_FRED)
    return results



def validate_fred_key(api_key):
    try:
        from fredapi import Fred
        s=Fred(api_key=api_key).get_series("FEDFUNDS",observation_start="2024-01-01")
        if s is not None and not s.empty: return True,"Key validated successfully"
        return False,"Key returned no data, check and retry."
    except Exception as exc:
        return False,"Validation failed: {}".format(exc)


def _fund_signal_meta(metric_key, rv):
    if rv is None: return "neutral", None, None
    direction, signal, chg_pct = "up", None, None
    if metric_key == "1d_return":
        chg_pct = rv; direction = "up" if rv >= 0 else "down"; signal = "bullish" if rv >= 0 else "bearish"
    elif metric_key == "rolling_3y":
        direction = "up" if rv >= 10 else ("down" if rv < 0 else "neutral")
        signal = "bullish" if rv >= 12 else ("neutral" if rv >= 8 else "bearish")
    elif metric_key == "sharpe_3y":
        direction = "up" if rv >= 1.0 else ("down" if rv < 0.5 else "neutral")
        signal = "excellent" if rv >= 1.5 else ("bullish" if rv >= 1.0 else ("bearish" if rv < 0.5 else "neutral"))
    elif metric_key == "sortino_3y":
        direction = "up" if rv >= 1.2 else ("down" if rv < 0.8 else "neutral")
        signal = "excellent" if rv >= 1.8 else ("bullish" if rv >= 1.2 else ("bearish" if rv < 0.8 else "neutral"))
    elif metric_key == "alpha_3y":
        direction = "up" if rv >= 0 else "down"; signal = "bullish" if rv > 0 else "bearish"
    elif metric_key == "beta_3y":
        direction = "up" if rv <= 1.0 else "down"
        signal = "defensive" if rv < 0.85 else ("aggressive" if rv > 1.15 else "neutral")
    elif metric_key == "max_drawdown":
        direction = "up" if rv >= -15 else "down"
        signal = "bullish" if rv >= -15 else ("caution" if rv >= -25 else "bearish")
    elif metric_key == "dist_ath":
        direction = "up" if rv >= -10 else "down"
        signal = "bullish" if rv >= -10 else ("dip" if rv >= -25 else "bearish")
    elif metric_key == "expense_ratio":
        direction = "up" if rv <= 1.0 else "down"
        signal = "low cost" if rv <= 0.75 else ("moderate" if rv <= 1.5 else "high fee")
    elif metric_key == "tracking_error":
        direction = "up" if rv <= 1.5 else "down"
        signal = "tight" if rv <= 1.0 else ("moderate" if rv <= 3.0 else "high te")
    return direction, signal, chg_pct


def get_fund_metric(scheme_code, metric_key):
    ck="fm:{}:{}:v4".format(scheme_code,metric_key); cached=cache.get(ck)
    if cached: return cached
    meta=FUND_METRIC_DEFS.get(metric_key,{}); label=meta.get("label",metric_key); unit=meta.get("unit","")
    base={"scheme_code":scheme_code,"metric_key":metric_key,"tooltip_what":meta.get("tooltip_what",""),"tooltip_interp":meta.get("tooltip_interp","")}
    try:
        from apps.funds.models import NAVHistory, Scheme
        from apps.benchmarks.registry import configure_yfinance_cache
        scheme=Scheme.objects.filter(amfi_code=scheme_code).first()
        if not scheme: return {**_na(label,"fund",unit,"Fund not found"),**base}
        cutoff=datetime.now().date()-timedelta(days=3*365+30)
        navs=NAVHistory.objects.filter(scheme=scheme,date__gte=cutoff).order_by("date").values_list("date","nav")
        if not navs: return {**_na(label,"fund",unit,"Insufficient NAV history"),**base}
        nav_df=pd.DataFrame(navs,columns=["date","nav"])
        nav_df["nav"]=pd.to_numeric(nav_df["nav"],errors="coerce")
        nav_df=nav_df.dropna().set_index("date").sort_index()
        ns=nav_df["nav"]; dr=ns.pct_change().dropna(); rf=0.065/252; rv=None
        if metric_key=="1d_return":
            if len(ns)>=2: rv=round(float((ns.iloc[-1]-ns.iloc[-2])/ns.iloc[-2]*100),4)
        elif metric_key=="expense_ratio": rv=float(scheme.expense_ratio) if getattr(scheme,"expense_ratio",None) else None
        elif metric_key=="dist_ath": rv=round((float(ns.iloc[-1])-float(ns.max()))/float(ns.max())*100,2)
        elif metric_key=="max_drawdown":
            rm=ns.expanding().max(); rv=round(float(((ns-rm)/rm).min())*100,2)
        elif metric_key in ("sharpe_3y","sortino_3y","alpha_3y","beta_3y","tracking_error"):
            import yfinance as yf; configure_yfinance_cache(yf)
            bm=yf.download("^NSEI",period="3y",interval="1d",auto_adjust=True,progress=False)
            if not bm.empty:
                br=bm["Close"].squeeze().pct_change().dropna()
                comb=pd.concat({"f":dr,"b":br},axis=1).dropna()
                if len(comb)<60: return {**_na(label,"fund",unit,"Insufficient aligned data"),**base}
                fr=comb["f"]; br2=comb["b"]
                annf=float(fr.mean()*252); annrf=rf*252; annv=float(fr.std()*252**0.5)
                if metric_key=="sharpe_3y": rv=round((annf-annrf)/annv,3) if annv else None
                elif metric_key=="sortino_3y":
                    ds=float(fr[fr<0].std()*252**0.5); rv=round((annf-annrf)/ds,3) if ds else None
                elif metric_key=="beta_3y":
                    cov=float(pd.DataFrame({"f":fr,"b":br2}).cov().iloc[0,1]); var=float(br2.var()); rv=round(cov/var,3) if var else None
                elif metric_key=="alpha_3y":
                    beta=float(pd.DataFrame({"f":fr,"b":br2}).cov().iloc[0,1])/max(float(br2.var()),1e-9)
                    annbm=float(br2.mean()*252); rv=round(((annf-annrf)-beta*(annbm-annrf))*100,3)
                elif metric_key=="tracking_error": rv=round(float((fr-br2).std()*252**0.5)*100,3)
            else: return {**_na(label,"fund",unit,"Benchmark unavailable"),**base}
        elif metric_key=="rolling_3y":
            window=252*3
            if len(ns)>=window:
                rets=[]; step=max(1,window//100)
                for i in range(0,len(ns)-window,step):
                    sn=ns.iloc[i]; en=ns.iloc[i+window]
                    if sn>0: rets.append((en/sn)**(1/3)-1)
                rv=round(float(pd.Series(rets).mean())*100,2) if rets else None
            elif len(ns)>=30:
                years=max((ns.index[-1]-ns.index[0]).days/365.25,0.1)
                rv=round(((float(ns.iloc[-1])/float(ns.iloc[0]))**(1/years)-1)*100,2)
        if rv is None: return {**_na(label,"fund",unit,"Could not compute"),**base}
        direction, signal, chg_pct = _fund_signal_meta(metric_key, rv)
        res={**_ok(label,"fund",unit,rv,change_pct=chg_pct,direction=direction,signal=signal),"scheme_name":scheme.scheme_name,**base}
        cache.set(ck,res,TTL_COMPUTED); return res
    except Exception as exc:
        logger.error("fund metric %s/%s: %s",scheme_code,metric_key,exc)
        return {**_na(label,"fund",unit,str(exc)),**base}


def get_benchmark_metric(index_name, metric_key):
    """Compute a metric for a BenchmarkIndex using its stored NAV history."""
    ck="bm:{}:{}:v2".format(index_name,metric_key); cached=cache.get(ck)
    if cached: return cached
    meta=BENCHMARK_METRIC_DEFS.get(metric_key,{}); label=meta.get("label",metric_key); unit=meta.get("unit","")
    base={"index_name":index_name,"metric_key":metric_key,"tooltip_what":meta.get("tooltip_what",""),"tooltip_interp":meta.get("tooltip_interp","")}
    try:
        from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV
        idx=BenchmarkIndex.objects.filter(name=index_name,is_active=True).first()
        if not idx: return {**_na(label,"benchmark",unit,"Index not found"),**base}
        cutoff=datetime.now().date()-timedelta(days=3*365+30)
        navs=BenchmarkNAV.objects.filter(index=idx,date__gte=cutoff).order_by("date").values_list("date","close")
        if not navs: return {**_na(label,"benchmark",unit,"No history"),**base}
        df=pd.DataFrame(navs,columns=["date","close"])
        df["close"]=pd.to_numeric(df["close"],errors="coerce")
        df=df.dropna().set_index("date").sort_index()
        ns=df["close"]; rv=None
        if metric_key=="1d_return":
            if len(ns)>=2: rv=round(float((ns.iloc[-1]-ns.iloc[-2])/ns.iloc[-2]*100),4)
        elif metric_key=="dist_ath": rv=round((float(ns.iloc[-1])-float(ns.max()))/float(ns.max())*100,2)
        elif metric_key=="max_drawdown":
            rm=ns.expanding().max(); rv=round(float(((ns-rm)/rm).min())*100,2)
        elif metric_key=="rolling_3y":
            window=252*3
            if len(ns)>=window:
                rets=[]; step=max(1,window//100)
                for i in range(0,len(ns)-window,step):
                    sn=ns.iloc[i]; en=ns.iloc[i+window]
                    if sn>0: rets.append((en/sn)**(1/3)-1)
                rv=round(float(pd.Series(rets).mean())*100,2) if rets else None
            elif len(ns)>=30:
                years=max((ns.index[-1]-ns.index[0]).days/365.25,0.1)
                rv=round(((float(ns.iloc[-1])/float(ns.iloc[0]))**(1/years)-1)*100,2)
        if rv is None: return {**_na(label,"benchmark",unit,"Could not compute"),**base}
        direction, signal, chg_pct = _fund_signal_meta(metric_key, rv)
        res={**_ok(label,"benchmark",unit,rv,change_pct=chg_pct,direction=direction,signal=signal),"index_name":index_name,**base}
        cache.set(ck,res,TTL_COMPUTED); return res
    except Exception as exc:
        logger.error("benchmark metric %s/%s: %s",index_name,metric_key,exc)
        return {**_na(label,"benchmark",unit,str(exc)),**base}


def get_all_metric_values(user=None):
    price      = _fetch_price_metrics()
    tech       = _fetch_technical_metrics()
    fred       = _fetch_fred_metrics(user)
    valuation  = _fetch_valuation_metrics()
    nse_sent   = _fetch_nse_sentiment_metrics()
    return {**price, **tech, **fred, **valuation, **nse_sent}


# ── NSE session helper (mirrors nsepython_adapter, kept local to avoid circular import) ──
_NSE_STRIP_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _make_nse_strip_session() -> requests.Session:
    """Create an NSE-cookie session for the market strip sentiment fetchers."""
    import time
    s = requests.Session()
    s.headers.update(_NSE_STRIP_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.3)
        s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)
        time.sleep(0.3)
    except Exception as exc:
        logger.debug("NSE strip session warmup: %s", exc)
    return s


def _fetch_valuation_metrics() -> dict:
    """Fetch Nifty 50 PE/PB/DY and compute derived valuation metrics.

    Sources
    -------
    - PE/PB/DY: NSE India via ``/api/allIndices`` (with yfinance NIFTYBEES fallback).
    - Earnings Yield Gap: (1/PE)*100 minus India 10Y G-Sec yield (from FRED cache).
    - Buffett Indicator: India Market Cap / GDP from World Bank (wbgapi, 1-week cache).
    """
    ck = "mkt_valuation:v3"
    cached = cache.get(ck)
    if cached:
        return cached

    results = {k: _stub(k) for k in VALUATION_KEYS}
    pe_val: float | None = None
    pb_val: float | None = None
    dy_val: float | None = None

    # --- 1. Nifty 50 PE / PB / Dividend Yield via NSE allIndices ---
    try:
        session = _make_nse_strip_session()
        resp = session.get("https://www.nseindia.com/api/allIndices", timeout=12)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            for item in data:
                if str(item.get("index", "")).strip().upper() == "NIFTY 50":
                    try:
                        raw_pe = str(item.get("pe", "")).replace(",", "").strip()
                        if raw_pe and raw_pe != "-":
                            pe_val = float(raw_pe)
                    except Exception:
                        pass
                    try:
                        raw_pb = str(item.get("pb", "")).replace(",", "").strip()
                        if raw_pb and raw_pb != "-":
                            pb_val = float(raw_pb)
                    except Exception:
                        pass
                    try:
                        raw_dy = str(item.get("dy", "")).replace(",", "").strip()
                        if raw_dy and raw_dy != "-":
                            dy_val = float(raw_dy)
                    except Exception:
                        pass
                    break
    except Exception as exc:
        logger.warning("NSE allIndices PE/PB fetch: %s", exc)

    # Fallback for PE via yfinance NIFTY ETF if NSE is unreachable
    if pe_val is None:
        try:
            import yfinance as yf
            bees = yf.Ticker("NIFTYBEES.NS")
            t_pe = bees.info.get("trailingPE")
            if t_pe and float(t_pe) > 0:
                pe_val = float(t_pe)
        except Exception as exc:
            logger.debug("yfinance NIFTYBEES PE fallback: %s", exc)

    if pe_val is not None:
        results["nifty_pe"] = _ok(
            METRIC_CATALOGUE["nifty_pe"]["label"], "valuation", "x", round(pe_val, 2),
            signal="cheap" if pe_val < 18 else ("fair" if pe_val < 24 else "expensive"),
            threshold=METRIC_CATALOGUE["nifty_pe"]["threshold"],
        )
    if pb_val is not None:
        results["nifty_pb"] = _ok(
            METRIC_CATALOGUE["nifty_pb"]["label"], "valuation", "x", round(pb_val, 2),
            signal="cheap" if pb_val < 2.5 else ("fair" if pb_val < 3.5 else "premium"),
            threshold=METRIC_CATALOGUE["nifty_pb"]["threshold"],
        )
    if dy_val is not None:
        results["nifty_dy"] = _ok(
            METRIC_CATALOGUE["nifty_dy"]["label"], "valuation", "%", round(dy_val, 2),
            signal="high" if dy_val > 2 else ("fair" if dy_val > 1.2 else "low yield"),
            threshold=METRIC_CATALOGUE["nifty_dy"]["threshold"],
        )

    # --- 2. Earnings Yield Gap: (1/PE)*100 - India 10Y Yield ---
    if pe_val is not None and pe_val > 0:
        try:
            ey = (1.0 / pe_val) * 100.0
            india_10y: float | None = None
            for suffix in ("anon",):
                fred_c = cache.get(f"mkt_fred:v4:{suffix}")
                if isinstance(fred_c, dict):
                    v = (fred_c.get("repo_rate") or {}).get("value")
                    if v is not None:
                        india_10y = float(v)
                        break
            if india_10y is not None:
                gap = round(ey - india_10y, 2)
                results["earnings_yield_gap"] = _ok(
                    METRIC_CATALOGUE["earnings_yield_gap"]["label"], "valuation", "%", gap,
                    signal="equity cheap" if gap > 2 else ("fair" if gap > 0 else "bonds better"),
                    threshold=METRIC_CATALOGUE["earnings_yield_gap"]["threshold"],
                )
        except Exception as exc:
            logger.warning("earnings yield gap: %s", exc)

    # --- 3. Buffett Indicator: India Market Cap / GDP (World Bank, 1-week cache) ---
    try:
        buffett_ck = "mkt_buffett_india:v2"
        b_cached = cache.get(buffett_ck)
        if b_cached:
            results["buffett_india"] = b_cached
        else:
            import wbgapi as wb  # type: ignore[import]
            df_mcap = wb.data.DataFrame("CM.MKT.LCAP.CD", "IND", mrv=5)
            df_gdp  = wb.data.DataFrame("NY.GDP.MKTP.CD", "IND", mrv=5)
            mcap_val = float(df_mcap.dropna(axis=1).iloc[0].values[-1]) if not df_mcap.empty else None
            gdp_val  = float(df_gdp.dropna(axis=1).iloc[0].values[-1]) if not df_gdp.empty else None
            if mcap_val and gdp_val and gdp_val > 0:
                ratio = round((mcap_val / gdp_val) * 100.0, 1)
                r = _ok(
                    METRIC_CATALOGUE["buffett_india"]["label"], "valuation", "%", ratio,
                    signal="undervalued" if ratio < 75 else ("fair" if ratio < 100 else "overvalued"),
                    threshold=METRIC_CATALOGUE["buffett_india"]["threshold"],
                )
                r["data_note"] = "Annual estimate via World Bank."
                cache.set(buffett_ck, r, 7 * 24 * 3600)
                results["buffett_india"] = r
    except Exception as exc:
        logger.warning("buffett indicator: %s", exc)

    cache.set(ck, results, TTL_VALUATION)
    return results


def _fetch_nse_sentiment_metrics() -> dict:
    """Fetch NSE-sourced sentiment metrics: PCR, FII Net, Advance/Decline, and SIP Inflows.

    Sources
    -------
    - PCR:     NSE live derivatives via ``/api/liveEquity-derivatives?index=nse50_opt``.
    - FII Net: NSE FII/DII activity via ``/api/fiidiiTradeReact``.
    - Adv/Dec: NSE Nifty 500 market breadth via ``/api/allIndices``.
    - SIP:     AMFI monthly trends page (monthly; separate 24-hour cache).
    """
    ck = "mkt_nse_sentiment:v3"
    cached = cache.get(ck)
    if cached:
        results = dict(cached)
        sip_cached = cache.get("mkt_sip:v2")
        if sip_cached:
            results["sip_inflows"] = sip_cached
        return results

    results = {k: _stub(k) for k in NSE_SENTIMENT_KEYS}

    try:
        session = _make_nse_strip_session()

        # ── 1. Put/Call Ratio (PCR) ──────────────────────────────────────────
        try:
            resp = session.get(
                "https://www.nseindia.com/api/liveEquity-derivatives?index=nse50_opt",
                timeout=12,
            )
            if resp.status_code == 200:
                opt_data = resp.json().get("data", [])
                ce_oi, pe_oi = 0.0, 0.0
                for item in opt_data:
                    opt_type = str(item.get("optionType", "")).upper()
                    try:
                        oi = float(str(item.get("openInterest", 0)).replace(",", "") or 0)
                    except Exception:
                        oi = 0.0
                    if opt_type == "CE" or "CALL" in opt_type:
                        ce_oi += oi
                    elif opt_type == "PE" or "PUT" in opt_type:
                        pe_oi += oi
                if ce_oi > 0:
                    pcr = round(pe_oi / ce_oi, 2)
                    results["nifty_pcr"] = _ok(
                        METRIC_CATALOGUE["nifty_pcr"]["label"], "sentiment", "", pcr,
                        signal="oversold" if pcr > 1.1 else ("overbought" if pcr < 0.7 else "neutral"),
                        threshold=METRIC_CATALOGUE["nifty_pcr"]["threshold"],
                    )
        except Exception as exc:
            logger.warning("NSE PCR fetch: %s", exc)

        # ── 2. FII Net Activity ──────────────────────────────────────────────
        try:
            resp = session.get(
                "https://www.nseindia.com/api/fiidiiTradeReact",
                timeout=12,
            )
            if resp.status_code == 200:
                fii_data = resp.json()
                for entry in (fii_data if isinstance(fii_data, list) else []):
                    cat = str(entry.get("category", "")).upper()
                    if "FII" in cat or "FPI" in cat:
                        raw_net = str(entry.get("netPurchasesSales", entry.get("netValue", "0")))
                        try:
                            net = float(raw_net.replace(",", "").replace("\u2212", "-").strip() or "0")
                        except Exception:
                            net = 0.0
                        results["fii_net"] = _ok(
                            METRIC_CATALOGUE["fii_net"]["label"], "sentiment", "Cr",
                            round(net, 0), change=None, change_pct=None,
                            direction="up" if net >= 0 else "down",
                            signal="buying" if net > 2000 else ("selling" if net < -2000 else "neutral"),
                            threshold=METRIC_CATALOGUE["fii_net"]["threshold"],
                        )
                        break
        except Exception as exc:
            logger.warning("NSE FII/DII fetch: %s", exc)

        # ── 3. Advance / Decline Ratio (Nifty 500 Breadth) ────────────────────
        try:
            resp = session.get(
                "https://www.nseindia.com/api/allIndices",
                timeout=12,
            )
            if resp.status_code == 200:
                items = resp.json().get("data", [])
                advances, declines = 0, 0
                for item in items:
                    sym = str(item.get("index", "")).upper().strip()
                    if sym == "NIFTY 500":
                        try:
                            advances = int(item.get("advances", 0) or 0)
                            declines = int(item.get("declines", 0) or 0)
                        except Exception:
                            pass
                        break
                if advances and declines and declines > 0:
                    ratio = round(advances / declines, 2)
                    results["adv_dec"] = _ok(
                        METRIC_CATALOGUE["adv_dec"]["label"], "sentiment", "x", ratio,
                        direction="up" if ratio >= 1 else "down",
                        signal="bullish" if ratio > 1.5 else ("bearish" if ratio < 0.8 else "neutral"),
                        threshold=METRIC_CATALOGUE["adv_dec"]["threshold"],
                    )
        except Exception as exc:
            logger.warning("NSE Adv/Dec fetch: %s", exc)

    except Exception as exc:
        logger.warning("NSE sentiment session failed: %s", exc)

    cache.set(ck, results, TTL_NSE_SENTIMENT)

    # ── 4. SIP Inflows (AMFI, separate long-lived cache) ─────────────────────
    sip_ck = "mkt_sip:v2"
    sip_cached = cache.get(sip_ck)
    if sip_cached:
        results["sip_inflows"] = sip_cached
    else:
        try:
            sip_result = _fetch_sip_inflows_amfi()
            if sip_result:
                cache.set(sip_ck, sip_result, TTL_AMFI)
                results["sip_inflows"] = sip_result
        except Exception as exc:
            logger.warning("SIP inflows: %s", exc)

    return results


def _fetch_sip_inflows_amfi() -> dict | None:
    """Scrape latest monthly SIP inflow figure from AMFI's monthly trends page.

    Returns an ``_ok(...)`` dict on success or None if scraping fails.
    """
    try:
        resp = requests.get(
            "https://www.amfiindia.com/research-information/amfi-monthly",
            headers={"User-Agent": "Mozilla/5.0 (compatible; MFAnalysis/1.0; "
                                   "+https://github.com/amansingh2116/MutualFundAnalysis)"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        text = resp.text
        # Look for numbers in the current monthly SIP range (₹18,000–₹45,000 Cr)
        candidates: list[float] = []
        for m in re.finditer(r'(?:Rs\.?|INR|₹)?\s*([1-9][0-9],[0-9]{3}(?:\.[0-9]{1,2})?|[1-9][0-9]{4}(?:\.[0-9]{1,2})?)\s*(?:crore|cr)?', text, re.IGNORECASE):
            raw = m.group(1).replace(",", "")
            try:
                v = float(raw)
                if 18000 <= v <= 45000:
                    candidates.append(v)
            except Exception:
                pass
        if not candidates:
            return None
        sip_val = round(max(candidates), 0)
        meta = METRIC_CATALOGUE["sip_inflows"]
        return _ok(
            meta["label"], "sentiment", "Cr", sip_val,
            signal="excellent" if sip_val > 22000 else ("strong" if sip_val > 18000 else "growing"),
            threshold=meta["threshold"],
        )
    except Exception as exc:
        logger.warning("AMFI SIP scrape: %s", exc)
    return None
