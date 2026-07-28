# Project Workflow

> **Status:** This is the detailed feature and interface planning document for
> future implementation. For project orientation, current artifacts, and the
> implementation roadmap, start with the [README](../README.md).

## Introduction

Now we are going to formulate the workflow for the project in detail.

## Vision

We aim to make a mutual fund application that has all the features that helps mutual fund investors to make informed investment decisions. For this we are considering the following features:

1) **Mutual Fund Analysis:** Using APIs and/or web scraping to show complete information about a mutual fund scheme that is needed in order to make investment decision.
2) **Common Mutual Fund Calculators and Tools:**
3) **Comparison Tools:** Compare between two or more funds to choose the best availaable option according to your need.
4) **Personalized Recommendations:** User-questionnaire + AI for suggesting suitable funds according to user's risk profile and return expectations.
5) **Custom Portfolio Analysis:** Analyze uploaded or entered user portfolios and suggest changes like removing a mutual fund from portfolio, portfolio rebalancing, etc.

## Mutual Fund Analysis

The first and maybe the most important feauture is to provide investors with the ability to get complete information about a mutual fund scheme that is needed in order to make investment decision. We have considered the following features for this:

Fund Name
Fund Type: Classification by Structure (Open-Ended Funds, Close-Ended Funds, Interval Funds), Classification by Asset Class (Equity (Small Cap, Mid Cap, Large Cap, Multi Cap, Flexi Cap, Value, Focused, ELSS, etc.), Debt (Liquid, Overnight, Short Term, Long Term, Corporate Bond, Credit Risk, Gilt, etc.), Hybrid (Aggressive, Balanced, Conservative, Multi-Asset Allocation, etc.), Solution Oriented and Other (Retirement,Children, Index Fund and ETF, Fund of Funds), Direct vs Indirect, Active vs Passive, Domestic vs International, Growth vs IDCW)
![alt text](../../images/workflow-image-12.png)
Ranking and rank trend (built in model to rank funds not just based on details like past performance but based on the investors personal details and other factors, a return, recency and stability score model to be developed which leads to overall fund ranking normalized with investors details, also show the trend of the ranking, how it has changed over time, absolute ranking, relative ranking, ranking within category, etc.) (Stabilty is how well fund protect capital during downturns, Returns is how consistent the fund's returns have been over time, Recency is how well a fund has performed in the last 2 years, continuosly backtested framework thast best assesses a fund's future potential developed by experts after studying every mutual fund since its inception) (some funds might not have ratings due to insufficient data or because they belong to certain non-equity categories that are less relevant for retail investors) (to display it we can design a score card with performance risk, cost, composition, red flags, THEN RANKING BY RETURNS, COST AND VOLATILITY) {Our recommendations are continuously back-tested. And they have consistently been able to deliver 3-7% better returns across equity mutual fund categories (compared to category averages). Past data does not guarantee future returns. Neither do we. What we CAN assure you of is that our experts are always on top of the recommendations we make. So you make informed decisions.}
![alt text](../../images/workflow-image-13.png)
Overview (One page fund profile, commentary on whether to invest or not: In form, On track, Off track, Out of form)
![alt text](../../images/workflow-image-14.png)
![alt text](../../images/workflow-image-22.png)
Performance (Trailing 3, 5, 7, 10 years, since inception, Rolling returns for 2, 5, 7, 10 years (maximum, minimum, mean) vs category average and benchmark and vs peers, a time series graph is recommended)
![alt text](../../images/workflow-image-15.png)
![alt text](../../images/workflow-image-16.png)
![alt text](../../images/workflow-image-17.png)
![alt text](../../images/workflow-image-23.png)
![alt text](../../images/workflow-image-36.png)
Returns calculator (SIP vs Lumpsum, Returns before or After tax, input: investment amount, number of years, output: returns, total value, cagr, absolute returns, vs benchmar vs peers, XIRR analysis)
![alt text](../../images/workflow-image-18.png)
![alt text](../../images/workflow-image-4.png)
Portfolio (Equity, Debt, Cash, with time target according to category vs actual weightage with time ,Small, Mid, Large, Overseas vs. Domestic, industry and sector diversification, changes over time to understand how the portfolio has changed over time {it can be shown as two ways: sector distribution [sector diversification with chaging time], sector weightage [or with time changing sector weightage]}) (actual holdings with percentage)
![alt text](../../images/workflow-image-32.png)
![alt text](../../images/workflow-image-19.png)
![alt text](../../images/workflow-image-20.png)
![alt text](../../images/workflow-image-21.png)
![alt text](../../images/workflow-image-27.png)
![alt text](../../images/workflow-image-28.png)
![alt text](../../images/workflow-image-29.png)
![alt text](../../images/workflow-image-30.png)
![alt text](../../images/workflow-image-31.png)
![alt text](../../images/workflow-image-38.png)
![alt text](../../images/workflow-image-39.png)
Peer comparison (ratios {PE ratio, std dev, sharpe ratio, sortino ratio, max drawdown}, returns {cagr, trailing returns, rolling returns}, scheme information {expense ratio, exit load, stamp duty, lock in, minimum SIP & Lumpsum, inception date, tax implications, fund objective, fund house ranking, AUM, launch date})
![alt text](../../images/workflow-image-24.png)
![alt text](../../images/workflow-image-41.png)
Fund Information (NAV with graph, AUM, Expense ratio, Exit Load, Stamp Duty, Lock in, Minimum investment SIP & Lumpsum, Benchmark, Inception Date, Tax Implications {taxable, tax free, tax saving through ELSS investment, STCG, LTCG}, Fund Objective, Fund House {ranking, AUM, launch date})
![alt text](../../images/workflow-image-42.png)
![alt text](../../images/workflow-image-34.png)
![alt text](../../images/workflow-image-35.png)
Fund Managers (Name, Date joined, Qualification, Past experience and years of experience, other funds managed with their returns, AUM managed)
![alt text](../../images/workflow-image-25.png)
![alt text](../../images/workflow-image-26.png)
Ratios (P/E ratio, P/B ratio, Alpha, Beta, Sharpe, Sortino, Standard deviation, R squared, Max Drawdown vs category vs benchmark)
![alt text](../../images/workflow-image-33.png)
![alt text](../../images/workflow-image-37.png)

## Common Mutual Fund Calculators and Tools

Sometimes, investors need just some specific tools to help them make informed decisions. We have considered the following features for this:

## Comparison Tools

To compare between two or more funds to choose the best available option according to your need. We have considered the following features for this:

## Personalized Recommendations

Users, especially who are new to mutual funds, need personalized recommendations to make informed investment decisions. To make sure that user get we will need to get some basic information about the user. We have considered the following features for this:

investing experience
primary source of income
how many people depend on you financially
risk profile (what can you handle as a temporary drop in your portfolio knowing market can take 2 years to stablize)
return expectations

Then we will make a algorithm or train a model to get some basic information about the user. We have considered the following features for this:

> Based on <https://github.com/haritk/MUTUAL-FUND-ANALYSIS> we can classify the user into the following categories:

### Defensive Portfolio

Our defensive portfolio is designed to minimize downside risk while still providing a fair return. Here's how we selected the funds:

1. We prioritized low risk over return for defensive investors.
2. We sorted the funds based on the lower 2-step average standard deviation of their returns. This ensures low volatility.
3. To further minimize downside risk, we selected funds with lower 2-step average Sharpe/Sortino ratio. This signifies funds with a low risk-adjusted return.
4. We prioritized funds with lower beta, which helps in minimizing losses during bear markets.
5. We selected funds with a good balance of equity and debt holdings to ensure liquidity and security.
6. We focused on large-cap funds, as they generally provide a fair amount of growth potential with a lower level of risk.

### Aggressive Portfolio

Our aggressive portfolio is designed to maximize returns with a higher level of risk. Here's how we selected the funds:

1. We prioritized high return over risk for aggressive investors.
2. We sorted the funds based on the higher 2-step average return and alpha. This ensures high return.
3. We selected funds with a lower standard deviation and a high Sharpe/Sortino ratio. This signifies funds with a moderate risk-adjusted return.
4. We prioritized funds with a higher beta, which helps in maximizing profits during bull markets.
5. We selected funds with a good balance of equity and debt holdings, with a focus on mid-cap companies for potential growth.
6. We focused on hybrid equity-oriented funds that provide a fair balance of return and risk.

### Moderate Investor Portfolio

Our moderate investor portfolio seeks to provide a fair level of risk and growth potential, yielding a moderate return. Here's how we selected the funds:

1. We selected funds with a combination of high returns, high alpha, and a moderate standard deviation.
2. We prioritized funds with a lower Sharpe/Sortino ratio, which ensures a moderate risk-adjusted return.
3. We selected funds with a moderate beta, which balances potential profits and losses.
4. We focused on funds with a good balance of equity and debt holdings, with a focus on large-cap and mid-cap companies.
5. We prioritized hybrid equity-oriented funds that provide a fair balance of return and risk.

In summary, our portfolios are designed to strike a balance between risk, return, and diversification to meet the needs of different types of investors.

Then custom portfolio is prepared and simulated for 10 years with and without balancing, SIP vs Lumpsum, returns before and after tax and XIRR analysis, time series forecast graph pf portfolio vs benchmark

![alt text](../../images/workflow-image-52.png)

## Custom Portfolio Analysis

For experienced investors and for new investors to track and analyze their portfolio, they require to analyze their mutual fund transactions. We have considered the following features for this:

missed gains identification
critical issues in the portfolio
regular insigts and key alerts and implied actionable points (make sure portfolio is well aligned with the market conditions)
comparsion with benchmark and peers
rebalancing suggestion (what, how much and when, based on market conditions, personal details like risk profile and diversification)
exit funds suggestion, add funds suggestion

current value
1D returns
Total returns
Total invested
XIRR
funds
portfolio performance (overall and fund wise, with time)(in form {among tom performers, great to continue SIP, great to invest more lumpsum}, on track {performing better than most funds, good to continue SIP, good to invest more lumpsum}, off track {falling behind most funds, stop SIP and hold fund and dont buy more}, out of form {among the lowest performers, stop SIP and sell and exit fund})
![alt text](../../images/workflow-image-53.png)
rebalancing recommendation (based on maximizing returns, tax optimization and diversification)
![alt text](../../images/workflow-image-54.png)
portfolio vs market (nifty, benchmark, category average) with time 1D, 1W, 1M, 3M, 6M, 1Y, All
portfolio allocation (equity, debt, cash, small, mid, large, overseas vs. domestic, industry and sector diversification)
portfolio journey (invested vs total value and returns and singularly too)(with time 1D, 1W, 1M, 3M, 6M, 1Y, All)
portfolio fund overlap (stock-level overlap between funds, percentage, number of stocks, low vs high overlap and its implication as good or bad diversification) (stock wise overall weightage in the portfolio)
portfolio turnover (turnover ratio compared to benchmark and category average)
diversification score and commentary (based on last 1 year NAV movement and volatility, correlation based on daily movement of last 1 year for each fund and benchmark, under or over diversified based on number of funds, asset allocation, sectoral distribution)
![alt text](../../images/workflow-image-48.png)
XIRR analysis vs category (each fund compared with each sub category average then calculated returns {compare each fund with benchmark or category average, simulate every past transaction of user portfolio in the benchmark or category average, then compare returns, abs and xirr, missed gains or alpha generated with respect to benchmark or category average} are shown compared to your returns) and benchmark (same for this)
![alt text](../../images/workflow-image-47.png)
Forecasting (forecasting returns for next 1, 3, 6, 12 months) (financial independence age)
red flag analysis (part of ASM/GSM list, high pledged promoter holdings, high probability of default)
![alt text](../../images/workflow-image-50.png)
Total Cost
News and Events (news and events related to the portfolio and the market and thier implication on the portfolio, actionable insights if any)
portfolio review: investors generally get poor returns due to following reasons: no portfolio overview and adjustments, no rebalancing, choosing fund based on past performance, non disciplined investing mindset, one should review the portfolio at least once a quarter becuase of the economicenvironment and market condition, it could be due to regulatory changes, macro economic factors, market conditions, etc., or due to changes in the portfolio itself (like changes in holdings, changes in weights, etc. so overall analysis of fund in this section with actionable insights like rebalancing suggestion, exit funds suggestion, add funds suggestion with reasoning data backed, tax saving/tax harvesting implementation, etc., because past returns does not guarantee future returns and investing is not about choosing past winners but future ones, economic conditions like interest rates and global events affect market cycles and thus portfolio performance, so one should review the portfolio and take some actions accordingly)
![alt text](../../images/workflow-image-43.png)
![alt text](../../images/workflow-image-44.png)
![alt text](../../images/workflow-image-45.png)
![alt text](../../images/workflow-image-46.png)
![alt text](../../images/workflow-image-51.png)
ratios (P/E ratio, P/B ratio, Alpha, Beta, Sharpe, Sortino, Standard deviation, R squared, Max Drawdown vs category vs benchmark)

![inspiration for interactive display](../../images/workflow-image-3.png)
![alt text](../../images/workflow-image-55.png)

## Other considerations

Data Safety: Data should be kept safe of the investors, though it is public app but investors data should be handles with care and make sure that it do not get leaked or used for malicious purposes.
Transparecy: Users should be made aware of the data they are giving to the app and how it will be used. All the algorithms and models should be transparent to the users. Users should be made aware of the data they are giving to the app and how it will be used. All the algorithms and models should be transparent to the users.
Risks: Mutual fund investments are subject to market risks. Always thoroughly research and study the scheme-related documents before making any investment decisions. Our recommendations, views, and opinions are based on our internal research and study, and may change over time. We do not guarantee returns on investments made in any of the funds mentioned herein. Past performance may not be sustainable in the future.

## Structure

### Homepage

Mutual Fund Recommendation, Ranking of Mutual Funds classified on basis of asset class, risk profile, returns, etc., Mutual Fund Portfolio suggestions for Aggressive, Balanced, Conservative, etc., major indices, market mood index, blogs, learn section, news and events, other tabs options

![alt text](../../images/workflow-image-56.png)
![alt text](../../images/workflow-image-49.png)

### Mutual Fund Information

Mutual Fund Information with detailed information on each fund, including performance, risk, fees, etc.
Recommendation based on personal information and questionnaire.
Each fund has a comment section where users can share their views and opinions.inions.
![alt text](../../images/workflow-image-40.png)

### Tools and Calculators

#### Explore Mutual Funds

Top performing funds
Best Rated funds based on Performance, Risk, Fees, etc.
Category-wise top performing funds
Investment Ideas (Portfolio buckets based on risk and performance)

![alt text](../../images/workflow-image-9.png)

![alt text](../../images/workflow-image-10.png)

![alt text](../../images/workflow-image-11.png)

#### Mutual Fund Screener

Sort and Filter Mutual Funds Based on various factors to find the best Mutual Funds for you. Factors like:
Basic (asset class{equity, debt, hybrid}, AUM, age, exit load, expense ratio, horizon{open, closed, interval}, nature{growth, IDCW})
Return (1M, 3M, 6M, 1Y, 3Y, 5Y, returns percentage, alpha 1Y, 3Y, 5Y, SIP returns)
Risk (Volatility, Beta, Sharpe, Sortino, Max Drawdown, , Jensen Alpha, Upside and Downside Capture ratio, Information, Treynor, Active Risk, etc.)
Fund Manager (returns, risk, alpha, sharpe, Information, expertise)
Portfolio (large, small, mid cap, equity, debt, holding percentage filter, sector diversification)
rating (recency, performance, diversification, risk, etc.)

![alt text](../../images/workflow-image-5.png)

And give columns to add or hide to compare like:
Rating, AUM(cr), Age(yr), Mod Dur, Avg Mat, Return(1d), Return(1w), Return(1m), Return(3m), Return(6m), Return(1y), Return(2y), Return(3y), Return(5y), Alpha(1y), Alpha(2y), Alpha(3y), VolatilityBetaSharpe, etc.

![alt text](../../images/workflow-image-6.png)

#### Mutual Fund Comparison

Compare Mutual Funds Based on various factors to find the best Mutual Funds for you. Factors like:

Risk-Adjusted Performance

Returns over various time periods (6 months, 1 year, 3 years, etc.).
Performance of a Systematic Investment Plan (SIP).
Monthly Outperformance against a benchmark.
Volatility (how much the fund's return fluctuates).
Beta (sensitivity to market movements).
Sharpe Ratio (return per unit of risk).
Jensen's Alpha (outperformance over the expected return).

Fund Manager's Performance

Returns generated by the fund manager.
Monthly Outperformance achieved by the manager.
Volatility under the manager's tenure.
Sharpe Ratio during their management period.

Fund Management Skills

Index Alpha: How much the fund's performance differs from the index due to investments inside vs. outside the index.
Sector & Stock Skills: How much performance is due to choosing the right sectors versus picking the right stocks within those sectors.
Bull's Eye: The success rate of the manager's stock picks.

Holdings & Concentration

Portfolio Concentration: The percentage weight of the top 5 and top 10 holdings.
Asset Allocation: The fund's breakdown across different asset classes (e.g., Equity, Bonds, Cash).
Sector Holdings: The percentage allocation to different industry sectors (e.g., Financials, IT, Health Care).

![alt text](../../images/workflow-image-7.png)

![alt text](../../images/workflow-image-8.png)

#### Calculators

Various mutual fund related calculators that are required by investors on regular basis:

- Mutual Fund Trailing Returns
- Mutual Fund Annual Returns
- Best Performing Funds
- Mutual Fund Quartile Ranking
- Downside Volatility Ranking
- Mutual Fund Category Monitor
- Mutual Fund Benchmark Monitor
- PPF vs ELSS
- Benchmark Return
- SIP Return Calculator
- Step SIP Return Calculator
- STP Return Calculator
- STP Calculator Profit Transfer
- SWP calculator
- Top SWP Funds
- SWP Return Calculator
- Liquid Funds vs Savings Bank
- Mutual Fund Category Returns
- Market Capture Ratio
- Mutual Fund Latest NAV
- Mutual Fund Information
- Mutual Fund Selector
- Mutual Fund Portfolio Overlap
- Highest Dividend Paying Funds
- Consistent Dividend Paying Funds
- Categorywise Dividends
- Dividend comparison of schemes
- Historical Dividends
- Compare Mutual Funds
- Performance Risk ratio of MFs
- ELSS calculator
- Goal Calculator
- Investment Calculator
- Tax calculator
- Market Indices
- Rating

![alt text](../../images/workflow-image-57.png)

### Mutual Fund Recommendation

Interactive Quetionaire form and then detailed analysis of each fund based on the answers then custom portfolio recommendation and forecasting.

### Mutual Fund Portfolio Analysis

Input Mutual Fund excel sheets with transaction details or manual entries update or connecting to MF Central using PAN tp fetch data automatically, then perform detailed analysis and recommendations.

---

### Mutual Fund Portfolio Backtesting

Input mutual funds (respective benchmark indices), their weightage in the portfolio, investment amount, investment frequency (monthly, quarterly, yearly), investment type (SIP, Lumpsum) and then backtest the portfolio for last 10 years with detailed analysis.

![alt text](../../images/workflow-image-58.png)

Index Fund Portfolio construction and rebalancing details (this is just to enhance the output look by writing text and explaining things in the output, at the start of the output I want to show as output the information about the current strategy backtesting basically the details about the funds/indices, respective benchmark indexes, and weightage and rebalancing rules that is yearly and 5 strategic rebalancing)

#### Metrics & Analysis

- CAGR of strategies
- Trailing returns (trend of yearly returns and their comparative performances)
- Min, Max, Average5 year rolling returns
- Standard Deviation (Volatility) of returns
- Downside quarters analysis (for the quarters with returns, time, individual index performance)
- SIP assumption and analysis results (SIP XIRR)
- with all 5 rebalancing strategies

#### Rebalancing strategies

**1) For each equity sleeve (Momentum, Midcap, Nasdaq):**

- If 12-month total return > 0, allow debt → equity switch
- If 12-month return ≤ 0, stay in debt

**2) For each equity index:**

- If index price > 10-month moving average → equity ON
- Else → debt

**3) Estimate 6-month realized volatility.**

- If volatility > threshold → shift debt → debt
- If volatility normal → allow equit

**4) If PE \> long-term 90th percentile -> pause new equity SIP**

- Redirect incremental SIP to debt

**5) Signal = average of:**

- Trend signal (12M return)
- MA filter

**Note:** check [backtest.py](backtest.py) file for sample python implementation.

Refer to the following videos for more details on mutual fund backtesting and comparison of different strategies:

- [https://www.youtube.com/watch?v=ppxnjQ86T-Q&t=152s](https://www.youtube.com/watch?v=ppxnjQ86T-Q&t=152s)
- [https://youtu.be/ZAKdP5FcFio?si=8gbq_4B-lDibScDj](https://youtu.be/ZAKdP5FcFio?si=8gbq_4B-lDibScDj)
- [https://youtu.be/8SfVk8P4Bxs?si=9aC6LWwCBPkNrGZC](https://youtu.be/8SfVk8P4Bxs?si=9aC6LWwCBPkNrGZC)
- [https://youtu.be/JWgHNLsdRUY?si=eHCvs9cPceTawkUt](https://youtu.be/JWgHNLsdRUY?si=eHCvs9cPceTawkUt)

### Mutual Fund Portfolio AI Quantitative and Qualitative Analysis

This module performs a comprehensive analysis of the mutual fund portfolio, providing insights into the quantitative and qualitative aspects of the portfolio.

#### Quantitative Analysis

This section provides a detailed analysis of the quantitative aspects of the portfolio, including:

- XIRR calculation: calculates the internal rate of return of the portfolio
- Absolute returns: calculates the absolute returns of the portfolio
- SIP pattern analysis: analyzes the Systematic Investment Plan (SIP) pattern of the portfolio
- Market timing efficiency: analyzes the efficiency of the market timing strategy employed by the portfolio manager
- Diversification metrics: calculates the diversification metrics of the portfolio, including the Sharpe ratio, Sortino ratio, and Information ratio

#### Psychological Analysis

This section provides a detailed analysis of the qualitative aspects of the portfolio, including:

- Investor archetype identification: identifies the investor archetype based on their risk tolerance, investment goals, and investment horizon
- Risk evolution tracking: analyzes the risk evolution of the portfolio over time
- Behavioral pattern detection: detects behavioral patterns in the portfolio, such as overconfidence, loss aversion, and framing effects
- Consistency scoring: scores the consistency of the portfolio manager's decisions based on their investment philosophy and risk tolerance

#### Comparative Analysis

This section provides a detailed comparison of the portfolio with various benchmarks and peer groups, including:

- Benchmark comparison (Nifty): compares the performance of the portfolio with the Nifty index
- Peer-relative positioning: compares the performance of the portfolio with its peer group
- Historical performance analysis: analyzes the historical performance of the portfolio and its peer group

#### Visualization

This section provides a detailed visualization of the portfolio, including:

- Cumulative investment plot: plots the cumulative investment of the portfolio over time
- Monthly investment patterns: plots the monthly investment patterns of the portfolio
- Portfolio allocation pie chart: plots the portfolio allocation as a pie chart
- Risk evolution timeline: plots the risk evolution of the portfolio over time

#### Actionable Insights

This section provides actionable insights based on the analysis, including:

- Personalized recommendations: provides personalized recommendations based on the investor's risk tolerance, investment goals, and investment horizon
- Key strengths identification: identifies the key strengths of the portfolio manager
- Improvement areas: identifies areas for improvement in the portfolio manager's decision-making process

#### Strategic Suggestions to Adapt to Your Data

This section provides strategic suggestions to adapt the system to your data, including:

- Replace sample data with your actual transaction history
- Update CSV parsing in CSVAdapter class to match your file formats
- Add your benchmark data for accurate comparison
- Set AI_ENABLED = True if you want AI insights (requires API key)

**Note:** check [analysis.py](analysis.py) file for sample python implementation.

## Workflow
