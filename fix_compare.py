import re

with open('templates/calculators/compare.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Overview tab metrics
overview_old = """    { label: 'Category', key: 'category', fmt: v => v || '—' },
    { label: 'Plan', key: 'plan', fmt: v => v || '—' },
    { label: 'Inception', key: 'inception_date', fmt: v => v ? fmtDate(v) : '—' },
    { label: 'AUM (₹ Cr)', key: 'aum', fmt: v => v ? `₹${Number(v).toLocaleString('en-IN', {maximumFractionDigits:0})}` : '—', higher_better: true },
    { label: 'Expense Ratio', key: 'expense_ratio', fmt: v => v != null ? `${v}%` : '—', lower_better: true },
    { label: 'Benchmark', key: 'benchmark_name', fmt: v => v || '—' },
    { label: 'Fund Manager', key: 'fund_manager', fmt: v => v ? v.replace(/;/g, ', ') : '—' },
    { label: 'Min SIP', key: 'min_sip', fmt: v => v ? `₹${Number(v).toLocaleString('en-IN')}` : '—', lower_better: true },
    { label: 'Min Lumpsum', key: 'min_lumpsum', fmt: v => v ? `₹${Number(v).toLocaleString('en-IN')}` : '—', lower_better: true },
    { label: 'Lock-in', key: 'lock_in_label', fmt: v => v || 'None' },
    { label: 'Tax Period', key: 'tax_period_days', fmt: v => v > 0 ? `${v} days` : 'None' },
    { label: 'Portfolio Turnover', key: 'portfolio_turnover', fmt: v => v != null ? `${v}%` : '—', lower_better: true },
    { label: 'CRISIL Rating', key: 'crisil_rating', fmt: v => v || '—' },
    { label: 'Morningstar', key: 'ms_rating', fmt: v => v ? '★'.repeat(v) + '☆'.repeat(5-v) : '—' },"""

overview_new = """    { label: 'Category', key: 'category', fmt: v => v || '—' },
    { label: 'Plan', key: 'plan', fmt: v => v || '—' },
    { label: 'Inception', key: 'inception_date', fmt: v => v ? fmtDate(v) : '—' },
    { label: 'AUM (₹ Cr) <button class="info-btn" data-t-title="Assets Under Management (AUM)" data-t-what="Total market value of the investments managed by the fund." data-t-interp="Larger AUM indicates popularity, but for Small Cap funds, very large AUM can hinder performance.">ⓘ</button>', key: 'aum', fmt: v => v ? `₹${Number(v).toLocaleString('en-IN', {maximumFractionDigits:0})}` : '—', higher_better: true },
    { label: 'Expense Ratio <button class="info-btn" data-t-title="Expense Ratio" data-t-what="The annual fee charged by the fund house." data-t-interp="Lower is better, as it directly impacts your final returns.">ⓘ</button>', key: 'expense_ratio', fmt: v => v != null ? `${v}%` : '—', lower_better: true },
    { label: 'Benchmark', key: 'benchmark_name', fmt: v => v || '—' },
    { label: 'Fund Manager', key: 'fund_manager', fmt: v => v ? v.replace(/;/g, ', ') : '—' },
    { label: 'Min SIP', key: 'min_sip', fmt: v => v ? `₹${Number(v).toLocaleString('en-IN')}` : '—', lower_better: true },
    { label: 'Min Lumpsum', key: 'min_lumpsum', fmt: v => v ? `₹${Number(v).toLocaleString('en-IN')}` : '—', lower_better: true },
    { label: 'Lock-in', key: 'lock_in_label', fmt: v => v || 'None' },
    { label: 'Tax Period', key: 'tax_period_days', fmt: v => v > 0 ? `${v} days` : 'None' },
    { label: 'Portfolio Turnover <button class="info-btn" data-t-title="Portfolio Turnover Ratio" data-t-what="Measures how frequently the fund manager buys and sells securities." data-t-interp="Lower is better. High turnover (>100%) implies higher trading costs and taxes.">ⓘ</button>', key: 'portfolio_turnover', fmt: v => v != null ? `${v}%` : '—', lower_better: true },
    { label: 'CRISIL Rating <button class="info-btn" data-t-title="CRISIL Rating" data-t-what="Overall rating assigned by CRISIL based on performance and risk." data-t-interp="5-star is highest. 1-star is lowest.">ⓘ</button>', key: 'crisil_rating', fmt: v => v || '—' },
    { label: 'Morningstar <button class="info-btn" data-t-title="Morningstar Rating" data-t-what="Overall rating assigned by Morningstar." data-t-interp="5-star is highest.">ⓘ</button>', key: 'ms_rating', fmt: v => v ? '★'.repeat(v) + '☆'.repeat(5-v) : '—', higher_better: true },"""

html = html.replace(overview_old, overview_new)

# 2. Returns tab rolling metrics
roll_old = """      { k:'mean', l:'Mean', hb:true },
      { k:'median', l:'Median', hb:true },
      { k:'min', l:'Min', hb:true },
      { k:'max', l:'Max', hb:true },
      { k:'win_rate_0', l:'Win Rate (>0%)', hb:true },
      { k:'win_rate_12', l:'Win Rate (>12%)', hb:true },"""

roll_new = """      { k:'mean', l:'Mean Return', hb:true },
      { k:'median', l:'Median Return', hb:true },
      { k:'min', l:'Min Return <button class="info-btn" data-t-title="Minimum Return" data-t-what="The worst return observed in any rolling window of this duration." data-t-interp="Higher is better. Shows the worst-case scenario.">ⓘ</button>', hb:true },
      { k:'max', l:'Max Return', hb:true },
      { k:'win_rate_0', l:'Win Rate (>0%) <button class="info-btn" data-t-title="Win Rate (>0%)" data-t-what="Percentage of times the fund gave positive returns over this rolling window." data-t-interp="Higher is better. Indicates consistency in preserving capital.">ⓘ</button>', hb:true },
      { k:'win_rate_12', l:'Win Rate (>12%) <button class="info-btn" data-t-title="Win Rate (>12%)" data-t-what="Percentage of times the fund gave returns greater than 12% over this rolling window." data-t-interp="Higher is better. Indicates consistency in generating high returns.">ⓘ</button>', hb:true },"""

html = html.replace(roll_old, roll_new)

# 3. Risk metrics tooltips
risk_old = """  const metrics3 = [
    { k:'std_dev',         l:'Std Dev (Volatility)', lb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'sharpe',          l:'Sharpe Ratio', hb:true, fmt: v => v != null ? v : '—' },
    { k:'sortino',         l:'Sortino Ratio', hb:true, fmt: v => v != null ? v : '—' },
    { k:'max_drawdown',    l:'Max Drawdown', lb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'beta',            l:'Beta', fmt: v => v != null ? v : '—' },
    { k:'alpha',           l:'Alpha (Annualised)', hb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'r_squared',       l:'R² (vs Benchmark)', hb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'tracking_error',  l:'Tracking Error', lb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'info_ratio',      l:'Information Ratio', hb:true, fmt: v => v != null ? v : '—' },
    { k:'upside_capture',  l:'Upside Capture', hb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'downside_capture',l:'Downside Capture', lb:true, fmt: v => v != null ? `${v}%` : '—' },
  ];"""

risk_new = """  const metrics3 = [
    { k:'std_dev',         l:'Std Dev (Volatility) <button class="info-btn" data-t-title="Standard Deviation" data-t-what="Measures how much the fund\\'s returns fluctuate from its average return. Higher = more volatile/risky." data-t-interp="Lower is better. A fund with 15% average return and 20% std dev will swing much wildly than one with 15% return and 10% std dev. Compare only within the same category.">ⓘ</button>', lb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'sharpe',          l:'Sharpe Ratio <button class="info-btn" data-t-title="Sharpe Ratio" data-t-what="Measures risk-adjusted return (how much excess return you get for the total risk taken)." data-t-interp="Higher is better. A Sharpe ratio > 1 is generally considered good. It shows whether a fund\\'s high returns are due to smart decisions or just taking excessive risk.">ⓘ</button>', hb:true, fmt: v => v != null ? v : '—' },
    { k:'sortino',         l:'Sortino Ratio <button class="info-btn" data-t-title="Sortino Ratio" data-t-what="Similar to Sharpe ratio, but only penalises downside volatility (returns dropping below risk-free rate) instead of all volatility." data-t-interp="Higher is better. It\\'s often a better metric than Sharpe because investors generally don\\'t care about \\'upside risk\\' (prices going up rapidly).">ⓘ</button>', hb:true, fmt: v => v != null ? v : '—' },
    { k:'max_drawdown',    l:'Max Drawdown <button class="info-btn" data-t-title="Maximum Drawdown" data-t-what="The maximum observed loss from a peak to a trough of a portfolio before a new peak is attained." data-t-interp="Closer to 0% is better. -20% means the fund lost 20% of its value during its worst historical crash in the period. Indicates the absolute worst-case scenario.">ⓘ</button>', hb:true, fmt: v => v != null ? `${v}%` : '—' }, // Changed to hb:true because -10% is better than -30%
    { k:'beta',            l:'Beta <button class="info-btn" data-t-title="Beta" data-t-what="Measures the fund\\'s volatility relative to its benchmark index (which always has a Beta of 1.0)." data-t-interp="Beta = 1: Moves exactly with the market.<br>Beta > 1: More volatile than market (falls harder in crashes, rises faster in rallies).<br>Beta < 1: Less volatile (cushions falls, but lags in rallies).">ⓘ</button>', fmt: v => v != null ? v : '—' },
    { k:'alpha',           l:'Alpha (Annualised) <button class="info-btn" data-t-title="Jensen\\'s Alpha" data-t-what="Measures the extra return generated by the fund manager compared to the benchmark index, given the amount of risk taken." data-t-interp="Positive Alpha (>0): The manager added value and beat the market.<br>Negative Alpha (<0): The manager underperformed the market given the risk taken. Higher is better.">ⓘ</button>', hb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'r_squared',       l:'R² (vs Benchmark) <button class="info-btn" data-t-title="R-Squared" data-t-what="Indicates what percentage of a fund\\'s movements are explained by movements in its benchmark index." data-t-interp="Scale of 0 to 100. A high R² (85-100) means the fund closely tracks the index. A low R² means the fund\\'s returns are disconnected from the index.">ⓘ</button>', hb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'tracking_error',  l:'Tracking Error <button class="info-btn" data-t-title="Tracking Error" data-t-what="Measures how consistently a fund follows its benchmark index." data-t-interp="For Index Funds: Lower is better (should be < 0.5%).<br>For Active Funds: Higher indicates the manager is deviating from the index to generate alpha.">ⓘ</button>', lb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'info_ratio',      l:'Information Ratio <button class="info-btn" data-t-title="Information Ratio" data-t-what="Measures a fund manager\\'s ability to generate excess returns relative to a benchmark, divided by the tracking error (consistency)." data-t-interp="Higher is better. A ratio > 0.5 is good, > 1.0 is exceptional. Shows if the manager is consistently beating the benchmark or just got lucky once.">ⓘ</button>', hb:true, fmt: v => v != null ? v : '—' },
    { k:'upside_capture',  l:'Upside Capture <button class="info-btn" data-t-title="Upside Capture Ratio" data-t-what="Measures the manager\\'s performance in up-markets relative to the index." data-t-interp="Higher is better. > 100% means the fund gained MORE than the benchmark during bull markets.">ⓘ</button>', hb:true, fmt: v => v != null ? `${v}%` : '—' },
    { k:'downside_capture',l:'Downside Capture <button class="info-btn" data-t-title="Downside Capture Ratio" data-t-what="Measures the manager\\'s performance in down-markets relative to the index." data-t-interp="Lower is better. < 100% means the fund lost LESS than the benchmark during bear markets. A great fund has high upside capture and low downside capture.">ⓘ</button>', lb:true, fmt: v => v != null ? `${v}%` : '—' },
  ];"""

html = html.replace(risk_old, risk_new)

# 4. Quarterly Replacement
quarterly_old = """  // Best / worst quarter
  out += `<tr><td class="label-cell">Best Quarter</td>${funds.map(f => {
    const q = f.data?.quarterly?.best;
    return `<td>${q ? `<span class="val-pos">${q.return}%</span><br><span style="font-size:10px;color:var(--text-muted)">${q.label}</span>` : '—'}</td>`;
  }).join('')}</tr>`;
  out += `<tr><td class="label-cell">Worst Quarter</td>${funds.map(f => {
    const q = f.data?.quarterly?.worst;
    return `<td>${q ? `<span class="val-neg">${q.return}%</span><br><span style="font-size:10px;color:var(--text-muted)">${q.label}</span>` : '—'}</td>`;
  }).join('')}</tr>`;"""

quarterly_new = """  // Quarterly overlap (Top 5 / Worst 5)
  let allQ = [];
  funds.forEach(f => {
    if (f.data?.quarterly?.all) allQ.push(...f.data.quarterly.all);
  });
  
  // Find top 5 best quarters across all funds
  let uniqueQuarters = [...new Set(allQ.map(q => q.label))];
  // Calculate average return across funds for each quarter to determine "best" and "worst" globally
  let qStats = uniqueQuarters.map(label => {
    let returns = funds.map(f => f.data?.quarterly?.all?.find(x => x.label === label)?.return).filter(x => x != null);
    let avg = returns.length ? returns.reduce((a,b)=>a+b,0)/returns.length : 0;
    return {label, avg};
  });
  
  qStats.sort((a,b) => b.avg - a.avg);
  let top5 = qStats.slice(0, 5).map(x => x.label).sort();
  let worst5 = qStats.slice(-5).map(x => x.label).sort();

  if (top5.length > 0) {
    out += sectionHeader('🌟 Top Overlapping Best Quarters', funds.length);
    top5.forEach(label => {
      const values = funds.map(f => {
        if (!f.data) return null;
        const q = f.data.quarterly?.all?.find(x => x.label === label);
        return q ? `<span class="${q.return >= 0 ? 'val-pos' : 'val-neg'}">${q.return}%</span>` : '—';
      });
      const numVals = funds.map(f => f.data?.quarterly?.all?.find(x => x.label === label)?.return ?? null);
      const wi = getWinnerIndex(numVals, true);
      out += buildRawRow(`Quarter ${label}`, values, wi, funds);
    });
  }

  if (worst5.length > 0) {
    out += sectionHeader('📉 Top Overlapping Worst Quarters', funds.length);
    worst5.forEach(label => {
      const values = funds.map(f => {
        if (!f.data) return null;
        const q = f.data.quarterly?.all?.find(x => x.label === label);
        return q ? `<span class="${q.return >= 0 ? 'val-pos' : 'val-neg'}">${q.return}%</span>` : '—';
      });
      const numVals = funds.map(f => f.data?.quarterly?.all?.find(x => x.label === label)?.return ?? null);
      // In worst quarters, the one with the highest return (least negative) is the winner
      const wi = getWinnerIndex(numVals, true);
      out += buildRawRow(`Quarter ${label}`, values, wi, funds);
    });
  }"""

html = html.replace(quarterly_old, quarterly_new)

# 5. Portfolio tab
portfolio_old = """  [
    { l:'No. of Holdings', k:'holdings_count', fmt: v => v || '—', hb:false },
    { l:'Top-10 Weight',  k:'top10_weight',  fmt: v => v != null ? `${v}%` : '—' },
    { l:'Avg P/E Ratio',  k:'pe_ratio',      fmt: v => v != null ? v : '—' },
    { l:'Portfolio Turnover', k:'portfolio_turnover', fmt: v => v != null ? `${v}%` : '—', lb:true },
  ]"""

portfolio_new = """  [
    { l:'No. of Holdings <button class="info-btn" data-t-title="Number of Holdings" data-t-what="Total number of distinct stocks/bonds the fund holds." data-t-interp="Fewer holdings (<30) = concentrated/high risk. More holdings (>60) = diversified/lower risk but may lead to average returns.">ⓘ</button>', k:'holdings_count', fmt: v => v || '—', hb:false },
    { l:'Top-10 Weight <button class="info-btn" data-t-title="Top 10 Weight" data-t-what="Percentage of total money invested in the top 10 largest holdings." data-t-interp="Higher % means the fund is heavily dependent on a few companies (concentrated). Lower % means it is widely diversified.">ⓘ</button>',  k:'top10_weight',  fmt: v => v != null ? `${v}%` : '—', lb:true },
    { l:'Avg P/E Ratio <button class="info-btn" data-t-title="Price to Earnings (P/E) Ratio" data-t-what="The weighted average P/E ratio of the stocks in the fund. Measures how expensive the portfolio is." data-t-interp="Value funds typically have low P/E. Growth funds typically have high P/E.">ⓘ</button>',  k:'pe_ratio',      fmt: v => v != null ? v : '—' },
    { l:'Portfolio Turnover <button class="info-btn" data-t-title="Portfolio Turnover Ratio" data-t-what="Measures how frequently the fund manager buys and sells securities within a year." data-t-interp="Lower is generally better. High turnover (>100%) implies higher trading costs and taxes, requiring higher gross returns to compensate.">ⓘ</button>', k:'portfolio_turnover', fmt: v => v != null ? `${v}%` : '—', lb:true },
  ]"""

html = html.replace(portfolio_old, portfolio_new)

sector_asset_old = """  out += sectionHeader('🏭 Sector Allocation Chart', funds.length);
  out += `<tr><td colspan="${funds.length+1}" style="padding:0;"><div id="cmp-sector-chart" style="height:320px;min-height:220px;background:var(--bg-card);border-radius:6px;margin:10px 14px;"></div></td></tr>`;

  out += sectionHeader('📊 Asset Allocation (Equity/Debt/Cash)', funds.length);
  out += `<tr><td colspan="${funds.length+1}" style="padding:0;"><div id="cmp-asset-alloc-chart" style="height:320px;min-height:220px;background:var(--bg-card);border-radius:6px;margin:10px 14px;"></div></td></tr>`;

  // Debt fund metrics
  out += sectionHeader('💳 Debt Fund Metrics', funds.length);
  ['Yield to Maturity (YTM)', 'Modified Duration', 'Average Maturity', 'Credit Quality'].forEach(metric => {
    out += `<tr><td class="label-cell">${metric}</td>${funds.map(f => {
      return `<td style="color:var(--text-muted);font-size:12px">NaN</td>`;
    }).join('')}</tr>`;
  });"""

sector_asset_new = """  out += sectionHeader('🏭 Sector Allocation', funds.length);
  out += `<tr><td class="label-cell">Donut Chart</td>${funds.map((f, i) => {
    if (!f.data || !f.data.sector_alloc?.length) return '<td style="color:var(--text-muted);text-align:center">—</td>';
    return `<td style="padding:10px;"><div id="cmp-sector-donut-${i}" style="height:180px;background:var(--bg-card);border-radius:6px;"></div></td>`;
  }).join('')}</tr>`;
  
  // Sector bars
  out += `<tr><td class="label-cell">Top Sectors</td>${funds.map(f => {
    if (!f.data || !f.data.sector_alloc?.length) return '<td style="color:var(--text-muted);text-align:center">—</td>';
    let bars = f.data.sector_alloc.slice(0, 6).map(s => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;font-size:11px">
        <span style="color:var(--text-secondary);max-width:80px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${escHtml(s.sector)}">${escHtml(s.sector)}</span>
        <div style="display:flex;align-items:center;gap:6px">
          <div style="width:40px"><div class="progress-bar"><div class="progress-fill" style="width:${s.weight}%"></div></div></div>
          <span style="font-weight:600;min-width:30px;text-align:right">${s.weight}%</span>
        </div>
      </div>
    `).join('');
    return `<td style="vertical-align:top;padding:10px 16px;">${bars}</td>`;
  }).join('')}</tr>`;

  out += sectionHeader('📊 Asset Allocation (Equity/Debt/Cash)', funds.length);
  out += `<tr><td class="label-cell">Asset Split</td>${funds.map(f => {
    if (!f.data || !f.data.asset_alloc) return '<td style="color:var(--text-muted);text-align:center">—</td>';
    const a = f.data.asset_alloc;
    let bars = '';
    ['equity', 'debt', 'cash'].forEach(t => {
      if (a[t] > 0) {
        let colorClass = t === 'equity' ? 'indigo' : (t === 'debt' ? 'green' : 'amber');
        bars += `
        <div style="margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px"><span style="color:var(--text-secondary);text-transform:capitalize">${t}</span><strong>${a[t]}%</strong></div>
          <div class="progress-bar"><div class="progress-fill ${colorClass}" style="width:${a[t]}%"></div></div>
        </div>`;
      }
    });
    return `<td style="vertical-align:top;padding:10px 16px;">${bars}</td>`;
  }).join('')}</tr>`;

  // Debt fund metrics
  out += sectionHeader('💳 Debt Fund Metrics <button class="info-btn" data-t-title="Debt Metrics" data-t-what="These metrics are only applicable to Debt and Hybrid mutual funds." data-t-interp="Yield to Maturity (YTM) indicates expected returns. Modified Duration indicates interest rate risk. Average Maturity indicates time to maturity. Credit Quality indicates default risk.">ⓘ</button>', funds.length);
  [
    { l:'Yield to Maturity (YTM) <button class="info-btn" data-t-title="Yield to Maturity" data-t-what="The expected annual rate of return if all bonds in the portfolio are held to maturity." data-t-interp="Higher YTM means higher potential return, but usually comes with higher credit risk (lower quality bonds).">ⓘ</button>'},
    { l:'Modified Duration <button class="info-btn" data-t-title="Modified Duration" data-t-what="Measures the portfolio\\'s sensitivity to interest rate changes." data-t-interp="If duration is 3 years, a 1% rise in interest rates will cause the fund\\'s NAV to drop by ~3%. Lower duration = lower interest rate risk.">ⓘ</button>'},
    { l:'Average Maturity <button class="info-btn" data-t-title="Average Maturity" data-t-what="The weighted average time until the bonds in the portfolio mature and pay back the principal." data-t-interp="Longer maturity funds are more volatile and sensitive to interest rate changes.">ⓘ</button>'},
    { l:'Credit Quality <button class="info-btn" data-t-title="Average Credit Quality" data-t-what="The average credit rating of the bonds in the portfolio (e.g., AAA, AA, SOV)." data-t-interp="AAA and SOV (Sovereign) are the safest. AA and below carry higher default risk.">ⓘ</button>'},
  ].forEach(metric => {
    out += `<tr><td class="label-cell">${metric.l}</td>${funds.map(f => {
      return `<td style="color:var(--text-muted);font-size:12px">NaN</td>`;
    }).join('')}</tr>`;
  });"""

html = html.replace(sector_asset_old, sector_asset_new)

# 6. Update Plotly Helpers
js_old = """    } else if (activeTab === 'portfolio') {
      plotAssetAllocChart(ready);
      plotSectorChart(ready);
    }
  }
}"""

js_new = """    } else if (activeTab === 'portfolio') {
      plotSectorDonuts(ready);
    }
  }
}"""

html = html.replace(js_old, js_new)


plotly_funcs_old = """function plotSectorChart(ready) {
  const allSectors = [...new Set(ready.flatMap(f => (f.data.sector_alloc || []).map(s => s.sector)))].slice(0, 15);
  const traces = ready.map((f, i) => {
    const idx = funds.findIndex(fn => fn.amfi_code === f.amfi_code) % 5;
    const allocMap = {};
    (f.data.sector_alloc || []).forEach(s => allocMap[s.sector] = s.weight);
    return {
      x: allSectors,
      y: allSectors.map(s => allocMap[s] ?? 0),
      name: shortName(f.data.scheme_name),
      type:'bar',
      marker:{ color:FUND_COLORS[idx].line },
      hovertemplate:'%{x}: <b>%{y:.2f}%</b><extra></extra>',
    };
  });
  if (traces.length && document.getElementById('cmp-sector-chart')) {
    Plotly.newPlot('cmp-sector-chart', traces, {...PLOTLY_LAYOUT, barmode:'group', yaxis:{...PLOTLY_LAYOUT.yaxis, ticksuffix:'%'}}, PLOTLY_OPTS);
  }
}

function plotAssetAllocChart(ready) {
  const assetTypes = ['equity', 'debt', 'cash', 'other'];
  const labels = ['Equity', 'Debt', 'Cash', 'Other'];
  
  const traces = ready.map((f, i) => {
    const idx = funds.findIndex(fn => fn.amfi_code === f.amfi_code) % 5;
    return {
      x: labels,
      y: assetTypes.map(t => f.data.asset_alloc?.[t] ?? 0),
      name: shortName(f.data.scheme_name),
      type:'bar',
      marker:{ color:FUND_COLORS[idx].line },
      hovertemplate:'%{x}: <b>%{y:.2f}%</b><extra></extra>',
    };
  });
  if (traces.length && document.getElementById('cmp-asset-alloc-chart')) {
    Plotly.newPlot('cmp-asset-alloc-chart', traces, {...PLOTLY_LAYOUT, barmode:'group', yaxis:{...PLOTLY_LAYOUT.yaxis, ticksuffix:'%'}}, PLOTLY_OPTS);
  }
}"""

plotly_funcs_new = """function plotSectorDonuts(ready) {
  ready.forEach((f) => {
    const i = funds.findIndex(fn => fn.amfi_code === f.amfi_code);
    const containerId = `cmp-sector-donut-${i}`;
    if (!document.getElementById(containerId)) return;
    
    if (!f.data.sector_alloc?.length) return;
    const labels = f.data.sector_alloc.map(s => s.sector);
    const values = f.data.sector_alloc.map(s => s.weight);
    
    const trace = {
      values: values,
      labels: labels,
      type: 'pie',
      hole: 0.6,
      textinfo: 'none',
      hoverinfo: 'label+percent',
      marker: {
        colors: ['#6366f1', '#34d399', '#f59e0b', '#f43f5e', '#38bdf8', '#a855f7', '#fb7185', '#2dd4bf', '#a3e635', '#facc15', '#60a5fa']
      }
    };
    
    const layout = {
      ...PLOTLY_LAYOUT,
      margin: { t:10, r:10, b:10, l:10 },
      showlegend: false,
      annotations: [{
        text: 'Sectors',
        showarrow: false,
        font: { size: 10, color: 'var(--text-muted)' }
      }]
    };
    
    Plotly.newPlot(containerId, [trace], layout, {responsive:true, displayModeBar:false});
  });
}"""

html = html.replace(plotly_funcs_old, plotly_funcs_new)

# Add custom color classes for progress bars
css_new = """.progress-fill.green { background: #10b981; }
.progress-fill.amber { background: #f59e0b; }
.progress-fill.indigo { background: #6366f1; }
</style>"""

html = html.replace("</style>", css_new)


with open('templates/calculators/compare.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("HTML Replaced successfully")
