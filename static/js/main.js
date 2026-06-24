/* ============================================================
   MF Analysis Platform — Shared JavaScript
   ============================================================ */

// ── Number Formatters ──────────────────────────────────────────
const INR = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 });
const INR_CR = (v) => v >= 1e5 ? `₹${(v/1e5).toFixed(1)}L Cr` : v >= 100 ? `₹${(v/100).toFixed(0)} Cr` : `₹${v} Cr`;
const PCT = (v, d=2) => v == null ? '—' : `${v >= 0 ? '+' : ''}${parseFloat(v).toFixed(d)}%`;
const NUM = (v, d=2) => v == null ? '—' : parseFloat(v).toFixed(d);

// ── Plotly Helpers ─────────────────────────────────────────────
const MF_PLOTLY_CONFIG = { displayModeBar: false, responsive: true };
const MF_PLOTLY_LAYOUT_BASE = {
  template: 'plotly_dark',
  plot_bgcolor: 'rgba(0,0,0,0)',
  paper_bgcolor: 'rgba(0,0,0,0)',
  font: { family: 'Inter, system-ui', color: '#94a3b8', size: 11 },
  margin: { l: 48, r: 16, t: 30, b: 40 },
  xaxis: { gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.07)', zeroline: false },
  yaxis: { gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.07)', zeroline: false },
  legend: { bgcolor: 'rgba(0,0,0,0)', borderwidth: 0, orientation: 'h', yanchor: 'bottom', y: 1.02, x: 0 },
  hoverlabel: { bgcolor: '#1a2035', bordercolor: 'rgba(99,102,241,0.5)', font: { family: 'Inter', color: '#f1f5f9' } },
};

function mergePlotlyLayout(extra={}) {
  return { ...MF_PLOTLY_LAYOUT_BASE, ...extra };
}

async function loadChart(containerId, apiUrl, buildFn) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (el._fullLayout && window.Plotly) Plotly.purge(el);
  el.innerHTML = `<div class="chart-placeholder"><div class="spinner"></div><span style="color:var(--text-muted);font-size:12px">Loading chart…</span></div>`;
  try {
    const r = await fetch(apiUrl);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    el.innerHTML = '';
    buildFn(el, data);
  } catch (e) {
    el.innerHTML = `<div class="chart-placeholder"><span class="placeholder-icon">📉</span><span style="font-size:12px;color:var(--text-muted)">Chart unavailable from the on-demand data source right now.</span></div>`;
  }
}

// ── NAV Chart ─────────────────────────────────────────────────
function renderNavChart(el, { data, scheme_name, benchmark_data, benchmark_name }) {
  if (!data || !data.length) {
    el.innerHTML = `<div class="chart-placeholder"><span class="placeholder-icon">📊</span><span style="font-size:12px;color:var(--text-muted)">No NAV history in database yet.</span></div>`;
    return;
  }
  const dates = data.map(d => d.date);
  const navs = data.map(d => d.nav);
  const traces = [{
    x: dates, y: navs,
    type: 'scatter', mode: 'lines',
    name: 'NAV',
    line: { color: '#6366f1', width: 2 },
    fill: 'tozeroy',
    fillcolor: 'rgba(99,102,241,0.08)',
    hovertemplate: '%{x}<br>₹%{y:.4f}<extra></extra>',
  }];
  if (benchmark_data && benchmark_data.length) {
    traces.push({
      x: benchmark_data.map(d => d.date),
      y: benchmark_data.map(d => d.value),
      customdata: benchmark_data.map(d => d.raw_value),
      type: 'scatter',
      mode: 'lines',
      name: benchmark_name || 'Benchmark',
      line: { color: '#34d399', width: 1.8, dash: 'dot' },
      hovertemplate: '%{x}<br>Rebased: %{y:.4f}<br>Index: %{customdata:.2f}<extra></extra>',
    });
  }
  Plotly.newPlot(el, traces, mergePlotlyLayout({ title: { text: '', font: { size: 0 } } }), MF_PLOTLY_CONFIG);
}

// ── Returns Bar Chart ──────────────────────────────────────────
function renderReturnsChart(el, { trailing, benchmark_name }) {
  if (!trailing || !trailing.length) {
    el.innerHTML = `<div class="chart-placeholder"><span class="placeholder-icon">📊</span><span style="font-size:12px;color:var(--text-muted)">No on-demand returns data available yet.</span></div>`;
    return;
  }
  const periods = trailing.map(t => t.period);
  const fundVals = trailing.map(t => t.cagr_pct);
  const bmVals = trailing.map(t => t.bm_cagr);
  const traces = [
    { name: 'Fund', x: periods, y: fundVals, type: 'bar', marker: { color: '#6366f1' }, hovertemplate: '%{x}: %{y:.2f}%<extra>Fund</extra>' },
  ];
  if (bmVals.some(v => v != null)) {
    traces.push({ name: benchmark_name || 'Benchmark', x: periods, y: bmVals, type: 'bar', marker: { color: 'rgba(148,163,184,0.4)' }, hovertemplate: '%{x}: %{y:.2f}%<extra>Benchmark</extra>' });
  }
  Plotly.newPlot(el, traces, mergePlotlyLayout({ barmode: 'group', xaxis: { type: 'category' }, yaxis: { ticksuffix: '%' } }), MF_PLOTLY_CONFIG);
}

// ── Drawdown Chart ─────────────────────────────────────────────
function renderDrawdownChart(el, { data }) {
  if (!data || !data.length) { el.innerHTML = `<div class="chart-placeholder"><span class="placeholder-icon">📉</span></div>`; return; }
  const dates = data.map(d => d.date);
  const dds = data.map(d => d.drawdown);
  const trace = {
    x: dates, y: dds,
    type: 'scatter', mode: 'lines',
    name: 'Drawdown',
    line: { color: '#f87171', width: 1.5 },
    fill: 'tozeroy', fillcolor: 'rgba(248,113,113,0.1)',
    hovertemplate: '%{x}<br>%{y:.2f}%<extra></extra>',
  };
  Plotly.newPlot(el, [trace], mergePlotlyLayout({ yaxis: { ticksuffix: '%' } }), MF_PLOTLY_CONFIG);
}

// ── Sector Donut Chart ─────────────────────────────────────────
function renderSectorChart(el, { sectors }) {
  if (!sectors || !sectors.length) { el.innerHTML = `<div class="chart-placeholder" style="min-height:260px"><span class="placeholder-icon">🍩</span></div>`; return; }
  const SECTOR_COLORS = ['#6366f1','#34d399','#f59e0b','#f87171','#38bdf8','#a78bfa','#fb7185','#60a5fa','#4ade80','#facc15'];
  const trace = {
    labels: sectors.map(s => s.sector),
    values: sectors.map(s => s.weight_pct),
    type: 'pie', hole: 0.55,
    textinfo: 'none',
    hovertemplate: '%{label}<br>%{value:.1f}%<extra></extra>',
    marker: { colors: SECTOR_COLORS },
  };
  Plotly.newPlot(el, [trace], { ...mergePlotlyLayout({ margin: { l: 10, r: 140, t: 10, b: 10 } }), showlegend: true, legend: { orientation: 'v', x: 1.05, y: 0.5, yanchor: 'middle', font: { size: 10 } }, height: 260 }, MF_PLOTLY_CONFIG);
}

// ── Calendar Return Chart ──────────────────────────────────────
function renderCalendarChart(el, { calendar, benchmark_name }) {
  if (!calendar || !calendar.length) { el.innerHTML = `<div class="chart-placeholder"><span class="placeholder-icon">📅</span></div>`; return; }
  const years = calendar.map(c => c.year.toString());
  const rets = calendar.map(c => c.return_pct);
  const bmRets = calendar.map(c => c.bm_return);
  const colors = rets.map(r => r >= 0 ? '#34d399' : '#f87171');
  const traces = [{
    name: 'Fund',
    x: years, y: rets, type: 'bar',
    marker: { color: colors },
    hovertemplate: '%{x}: %{y:.2f}%<extra>Fund</extra>',
  }];
  if (bmRets.some(v => v != null)) {
    traces.push({
      name: benchmark_name || 'Benchmark',
      x: years,
      y: bmRets,
      type: 'bar',
      marker: { color: 'rgba(148,163,184,0.45)' },
      hovertemplate: '%{x}: %{y:.2f}%<extra>Benchmark</extra>',
    });
  }
  Plotly.newPlot(el, traces, mergePlotlyLayout({ barmode: 'group', xaxis: { type: 'category' }, yaxis: { ticksuffix: '%' } }), MF_PLOTLY_CONFIG);
}

// ── SIP Result Chart ───────────────────────────────────────────
function renderSIPChart(el, { invested, current_value }) {
  const data = [{
    values: [invested, Math.max(0, current_value - invested)],
    labels: ['Invested', 'Gain'],
    type: 'pie', hole: 0.65,
    marker: { colors: ['rgba(99,102,241,0.5)', '#34d399'] },
    textinfo: 'none',
    hovertemplate: '%{label}: ₹%{value:,.0f}<extra></extra>',
  }];
  Plotly.newPlot(el, data, { ...mergePlotlyLayout({ margin: { l: 0, r: 0, t: 0, b: 0 } }), height: 220, showlegend: true, legend: { orientation: 'h', y: -0.1 } }, MF_PLOTLY_CONFIG);
}

// ── Tabs ───────────────────────────────────────────────────────
function initTabs(containerSelector='.tabs') {
  document.querySelectorAll(containerSelector).forEach(tabsEl => {
    const btns = tabsEl.querySelectorAll('.tab-btn');
    btns.forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        btns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        const panel = document.getElementById(target);
        if (panel) panel.classList.add('active');
        // Store in URL hash
        if (history.replaceState) history.replaceState(null, '', '#' + target);
      });
    });
    // Restore from hash
    const hash = location.hash.replace('#', '');
    if (hash) {
      const target = tabsEl.querySelector(`[data-tab="${hash}"]`);
      if (target) target.click();
    }
  });
}

// ── Toast ──────────────────────────────────────────────────────
function showToast(msg, type='info') {
  const container = document.getElementById('toast-container') || (() => {
    const el = document.createElement('div');
    el.id = 'toast-container';
    document.body.appendChild(el);
    return el;
  })();
  const colors = { success: '#34d399', error: '#f87171', info: '#6366f1', warning: '#fbbf24' };
  const t = document.createElement('div');
  t.className = 'toast';
  t.style.borderLeft = `3px solid ${colors[type] || colors.info}`;
  t.textContent = msg;
  container.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ── Search ─────────────────────────────────────────────────────
function initSearch() {
  const inp = document.getElementById('global-search');
  const dropdown = document.getElementById('search-dropdown');
  if (!inp || !dropdown) return;
  let timer;
  inp.addEventListener('input', () => {
    clearTimeout(timer);
    const q = inp.value.trim();
    if (q.length < 2) { dropdown.classList.remove('open'); return; }
    timer = setTimeout(() => {
      fetch(`/funds/search/?q=${encodeURIComponent(q)}&limit=8`)
        .then(r => r.json())
        .then(({ results }) => {
          if (!results.length) { dropdown.classList.remove('open'); return; }
          dropdown.innerHTML = results.map(f => `
            <div class="search-result-item" onclick="location.href='/funds/${f.amfi_code}/'">
              <div class="sri-name">${f.scheme_name}</div>
              <div class="sri-meta">${f.fund_house} &middot; ${f.scheme_category}</div>
            </div>`).join('');
          dropdown.classList.add('open');
        }).catch(() => {});
    }, 250);
  });
  document.addEventListener('click', e => { if (!inp.contains(e.target)) dropdown.classList.remove('open'); });
}

// ── Range display ──────────────────────────────────────────────
function initRangeInputs() {
  document.querySelectorAll('input[type="range"]').forEach(inp => {
    const display = document.getElementById(inp.id + '_display');
    if (display) display.textContent = inp.value;
    inp.addEventListener('input', () => { if (display) display.textContent = inp.value; });
  });
}

// ── Calculator AJAX ────────────────────────────────────────────
function initCalculator(formId, resultContainerId, renderFn) {
  const form = document.getElementById(formId);
  const result = document.getElementById(resultContainerId);
  if (!form || !result) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]');
    btn.classList.add('btn-loading');
    try {
      const r = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
      });
      const data = await r.json();
      renderFn(result, data);
    } catch (err) {
      result.innerHTML = `<div class="alert alert-danger">Calculation failed. Please try again.</div>`;
    } finally {
      btn.classList.remove('btn-loading');
    }
  });
}

function getCookie(name) {
  return document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name+'='))?.split('=')[1] || '';
}

// ── File Upload Drag & Drop ────────────────────────────────────
function initDropZone(zoneId, inputId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  if (!zone || !input) return;
  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length) {
      input.files = files;
      zone.querySelector('.dz-title').textContent = files[0].name;
      zone.querySelector('.dz-sub').textContent = `${(files[0].size / 1024).toFixed(0)} KB`;
    }
  });
  input.addEventListener('change', () => {
    if (input.files.length) {
      zone.querySelector('.dz-title').textContent = input.files[0].name;
      zone.querySelector('.dz-sub').textContent = `${(input.files[0].size / 1024).toFixed(0)} KB`;
    }
  });
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initSearch();
  initRangeInputs();
  initInfoTooltips();
});

// ── Info Tooltip Engine ────────────────────────────────────────
// Powers all ⓘ buttons. Reads data-t-* attributes and renders
// a smart positioned popup with structured content.
(function() {
  let activeBtn = null;
  let tooltip = null;

  function buildTooltip(btn) {
    const title   = btn.dataset.tTitle   || btn.getAttribute('aria-label') || 'Info';
    const what    = btn.dataset.tWhat;
    const interp  = btn.dataset.tInterp;
    const formula = btn.dataset.tFormula;
    const range   = btn.dataset.tRange;   // JSON string of [{dot,label,text}] or simple string
    const note    = btn.dataset.tNote;

    let sections = '';

    if (what) {
      sections += `<div class="tooltip-section">
        <div class="tooltip-section-label">What is it?</div>
        <div class="tooltip-section-text">${what}</div>
      </div>`;
    }
    if (interp) {
      sections += `<div class="tooltip-divider"></div><div class="tooltip-section">
        <div class="tooltip-section-label">How to interpret</div>
        <div class="tooltip-section-text">${interp}</div>
      </div>`;
    }
    if (formula) {
      sections += `<div class="tooltip-divider"></div><div class="tooltip-section">
        <div class="tooltip-section-label">Formula</div>
        <div class="tooltip-formula">${formula}</div>
      </div>`;
    }
    if (range) {
      let rangeHtml = '';
      try {
        const items = JSON.parse(range);
        rangeHtml = items.map(item =>
          `<div class="tooltip-range-item">
            <div class="tooltip-range-dot dot-${item.dot || 'neutral'}"></div>
            <span style="color:var(--text-muted);min-width:60px">${item.label}</span>
            <span style="color:var(--text-secondary)">${item.text}</span>
          </div>`
        ).join('');
      } catch(e) {
        // Plain string fallback
        rangeHtml = `<div style="color:var(--text-secondary);font-size:11px">${range}</div>`;
      }
      sections += `<div class="tooltip-divider"></div><div class="tooltip-section">
        <div class="tooltip-section-label">Good / Bad</div>
        <div class="tooltip-range">${rangeHtml}</div>
      </div>`;
    }
    if (note) {
      sections += `<div class="tooltip-divider"></div><div class="tooltip-section">
        <div class="tooltip-section-text" style="color:var(--amber-400);font-size:11px">⚠️ ${note}</div>
      </div>`;
    }

    return `
      <div class="info-tooltip-header">
        <div class="info-tooltip-title">${title}</div>
        <button class="info-tooltip-close" aria-label="Close">✕</button>
      </div>
      <div class="info-tooltip-body">${sections || '<div class="tooltip-section-text">No additional information available.</div>'}</div>
    `;
  }

  function positionTooltip(btn, tip) {
    const rect = btn.getBoundingClientRect();
    const tw = tip.offsetWidth || 300;
    const th = tip.offsetHeight || 200;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 8;

    // Prefer showing below the button, right-aligned to button
    let left = rect.left;
    let top  = rect.bottom + margin;

    // Flip right if overflows right edge
    if (left + tw > vw - margin) {
      left = Math.max(margin, rect.right - tw);
    }
    // Flip up if overflows bottom
    if (top + th > vh - margin) {
      top = rect.top - th - margin;
    }
    // Clamp left
    left = Math.max(margin, Math.min(left, vw - tw - margin));
    // Clamp top
    top  = Math.max(margin, top);

    tip.style.left = left + 'px';
    tip.style.top  = top  + 'px';
  }

  function showTooltipFor(btn) {
    if (activeBtn === btn && tooltip && tooltip.classList.contains('visible')) {
      hideTooltip();
      return;
    }
    hideTooltip();

    activeBtn = btn;
    btn.classList.add('active');

    tooltip = document.createElement('div');
    tooltip.className = 'info-tooltip';
    tooltip.innerHTML = buildTooltip(btn);
    document.body.appendChild(tooltip);

    // Position off-screen first to measure
    tooltip.style.left = '-9999px';
    tooltip.style.top  = '-9999px';

    // Close button
    tooltip.querySelector('.info-tooltip-close')?.addEventListener('click', hideTooltip);

    // Trigger reflow then show
    requestAnimationFrame(() => {
      positionTooltip(btn, tooltip);
      requestAnimationFrame(() => {
        tooltip.classList.add('visible');
      });
    });
  }

  function hideTooltip() {
    if (tooltip) {
      tooltip.classList.remove('visible');
      tooltip.addEventListener('transitionend', () => tooltip.remove(), { once: true });
      tooltip = null;
    }
    if (activeBtn) {
      activeBtn.classList.remove('active');
      activeBtn = null;
    }
  }

  window.initInfoTooltips = function(root) {
    const container = root || document;
    container.querySelectorAll('.info-btn').forEach(btn => {
      // Prevent double-binding
      if (btn._tooltipBound) return;
      btn._tooltipBound = true;

      btn.addEventListener('click', e => {
        e.stopPropagation();
        showTooltipFor(btn);
      });
      btn.addEventListener('mouseenter', () => {
        if (!('ontouchstart' in window)) showTooltipFor(btn);
      });
      btn.addEventListener('mouseleave', () => {
        if (!('ontouchstart' in window)) {
          // Delay hide to allow moving into tooltip
          setTimeout(() => {
            if (tooltip && !tooltip.matches(':hover')) hideTooltip();
          }, 120);
        }
      });
      btn.setAttribute('tabindex', '0');
      btn.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          showTooltipFor(btn);
        }
      });
    });
  };

  // Global close on outside click / Escape
  document.addEventListener('click', e => {
    if (tooltip && !tooltip.contains(e.target)) hideTooltip();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') hideTooltip();
  });
  // Tooltip mouseleave
  document.addEventListener('mouseleave', e => {
    if (tooltip && e.target === tooltip) hideTooltip();
  }, true);
})();

