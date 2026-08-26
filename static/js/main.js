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

function isMobileScreen() {
  return typeof window !== 'undefined' && window.innerWidth <= 640;
}

function mergePlotlyLayout(extra={}) {
  const isMob = isMobileScreen();
  const responsiveBase = {
    ...MF_PLOTLY_LAYOUT_BASE,
    font: {
      ...MF_PLOTLY_LAYOUT_BASE.font,
      size: isMob ? 9.5 : 11,
    },
    margin: isMob ? { l: 36, r: 12, t: 24, b: 32 } : { l: 48, r: 16, t: 30, b: 40 },
  };
  return { ...responsiveBase, ...extra };
}

// ── Global Responsive Chart Resize Listener ────────────────────
if (typeof window !== 'undefined') {
  let _chartResizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(_chartResizeTimer);
    _chartResizeTimer = setTimeout(() => {
      if (window.Plotly) {
        document.querySelectorAll('.js-plotly-plot').forEach((chartEl) => {
          try {
            Plotly.Plots.resize(chartEl);
          } catch (e) {}
        });
      }
    }, 150);
  });
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
function renderReturnsChart(el, { trailing, benchmark_name }, catAvg) {
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
  // Category average bars (amber)
  if (catAvg && catAvg.trailing) {
    const catMap = { '1Y': catAvg.trailing['1Y'], '3Y': catAvg.trailing['3Y'], '5Y': catAvg.trailing['5Y'] };
    const catVals = periods.map(p => catMap[p] != null ? catMap[p] : null);
    if (catVals.some(v => v != null)) {
      traces.push({ name: 'Cat Avg', x: periods, y: catVals, type: 'bar', marker: { color: 'rgba(251,191,36,0.55)', line: { color: 'rgba(251,191,36,0.9)', width: 1 } }, hovertemplate: '%{x}: %{y:.2f}%<extra>Cat Avg</extra>' });
    }
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
function renderCalendarChart(el, { calendar, benchmark_name }, catCal) {
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
  // Category average line (amber) — overlay on calendar chart
  if (catCal && typeof catCal === 'object' && Object.keys(catCal).length) {
    const catYears = years.filter(y => catCal[y] != null);
    const catVals = catYears.map(y => catCal[y]);
    if (catYears.length) {
      traces.push({
        name: 'Cat Avg',
        x: catYears, y: catVals,
        type: 'scatter', mode: 'lines+markers',
        line: { color: 'rgba(251,191,36,0.9)', width: 2, dash: 'dot' },
        marker: { color: 'rgba(251,191,36,1)', size: 5 },
        hovertemplate: '%{x}: %{y:.2f}%<extra>Cat Avg</extra>',
      });
    }
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
        // Store in URL hash without triggering scroll
        if (history.replaceState) history.replaceState(null, '', '#' + target);
      });
    });
    // Restore from hash without scrolling to the panel
    const hash = location.hash.replace('#', '');
    if (hash) {
      const target = tabsEl.querySelector(`[data-tab="${hash}"]`);
      if (target) {
        const savedY = window.scrollY;
        target.click();
        // Two rAFs to ensure browser anchor-scroll has fired before we restore
        requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, savedY)));
      }
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
function initSidebar() {
  const layout = document.getElementById('app-layout');
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('sidebar-toggle');
  const closeBtn = document.getElementById('sidebar-close');
  const overlay = document.getElementById('sidebar-overlay');
  if (!layout || !sidebar || !toggle) return;

  if (layout.dataset.sidebarReady === 'true') return;
  layout.dataset.sidebarReady = 'true';

  const mobileQuery = window.matchMedia('(max-width: 1024px)');
  const storage = {
    get(key) {
      try { return window.localStorage.getItem(key); } catch (e) { return null; }
    },
    set(key, value) {
      try { window.localStorage.setItem(key, value); } catch (e) {}
    }
  };

  function isOpen() {
    return layout.classList.contains('sidebar-open');
  }

  function setSidebarOpen(open) {
    layout.classList.toggle('sidebar-open', open);
    layout.classList.toggle('sidebar-closed', !open);
    sidebar.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', String(open));
    sidebar.setAttribute('aria-hidden', String(!open));
    if (overlay) overlay.setAttribute('aria-hidden', String(!open));
    document.body.classList.toggle('sidebar-scroll-lock', mobileQuery.matches && open);
    
    // Trigger dynamic chart resize during and after CSS transition
    [30, 100, 220, 350].forEach(ms => setTimeout(window.triggerAllChartResizes, ms));
  }

  setSidebarOpen(!mobileQuery.matches);

  toggle.addEventListener('click', () => setSidebarOpen(!isOpen()));
  closeBtn?.addEventListener('click', () => setSidebarOpen(false));
  overlay?.addEventListener('click', () => setSidebarOpen(false));
  sidebar.querySelectorAll('.sidebar-nav a').forEach(a => {
    a.addEventListener('click', () => {
      if (mobileQuery.matches) setSidebarOpen(false);
    });
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isOpen() && mobileQuery.matches) setSidebarOpen(false);
  });

  const onMediaChange = () => setSidebarOpen(!mobileQuery.matches);
  if (typeof mobileQuery.addEventListener === 'function') {
    mobileQuery.addEventListener('change', onMediaChange);
  } else if (typeof mobileQuery.addListener === 'function') {
    mobileQuery.addListener(onMediaChange);
  }

  sidebar.querySelectorAll('.nav-item').forEach(link => {
    link.addEventListener('click', () => {
      if (mobileQuery.matches) setSidebarOpen(false);
    });
  });

  sidebar.querySelectorAll('.nav-section').forEach(section => {
    const key = section.dataset.navSection;
    const button = section.querySelector('.nav-section-toggle');
    if (!key || !button) return;

    const storageKey = `mf.nav-section.${key}`;
    const hasActiveItem = Boolean(section.querySelector('.nav-item.active'));
    const collapsed = storage.get(storageKey) === 'collapsed' && !hasActiveItem;

    function setSectionCollapsed(shouldCollapse, persist=true) {
      section.classList.toggle('collapsed', shouldCollapse);
      button.setAttribute('aria-expanded', String(!shouldCollapse));
      if (persist) storage.set(storageKey, shouldCollapse ? 'collapsed' : 'expanded');
    }

    setSectionCollapsed(collapsed, false);
    button.addEventListener('click', () => setSectionCollapsed(!section.classList.contains('collapsed')));
  });
}

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

// ── Global Dynamic Chart Resize Helper ─────────────────────────
window.triggerAllChartResizes = function() {
  if (window.Plotly) {
    const plotlyContainers = document.querySelectorAll('.js-plotly-plot, [id*="-chart"], .chart-container');
    plotlyContainers.forEach(el => {
      try {
        if (el && el._fullLayout) {
          Plotly.Plots.resize(el);
        }
      } catch (e) {}
    });
  }
  if (window.ci && typeof window.ci === 'object') {
    Object.values(window.ci).forEach(chartInstance => {
      try {
        if (chartInstance && typeof chartInstance.resize === 'function') {
          chartInstance.resize();
        }
      } catch (e) {}
    });
  }
};

// Debounced resize listener
let _resizeDebounceTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(_resizeDebounceTimer);
  _resizeDebounceTimer = setTimeout(window.triggerAllChartResizes, 60);
});

// ── Global Multi-Platform Share Widget ─────────────────────────
function initShareWidget() {
  const widget = document.getElementById('global-share-widget');
  const fab = document.getElementById('global-share-fab');
  const modal = document.getElementById('global-share-modal');
  const closeBtn = document.getElementById('global-share-close');
  const copyBtn = document.getElementById('share-copy-btn');
  const copyText = document.getElementById('share-copy-text');
  const linkInput = document.getElementById('share-link-input');
  const titlePreview = document.getElementById('share-context-title');
  const urlPreview = document.getElementById('share-context-url');

  if (!widget || !fab || !modal) return;

  function getPageShareData() {
    const rawTitle = document.title || 'Mutual Fund Analysis';
    const cleanTitle = rawTitle.replace(/\s*—\s*MutualFundAnalysis\s*$/i, '').trim();
    const url = window.location.href;
    const shareText = `Check out "${cleanTitle}" on Indian Mutual Fund Analysis platform:\n${url}`;
    return { title: cleanTitle, url, text: shareText };
  }

  function updateShareLinks() {
    const data = getPageShareData();
    if (titlePreview) titlePreview.textContent = data.title;
    if (urlPreview) urlPreview.textContent = data.url;
    if (linkInput) linkInput.value = data.url;

    // WhatsApp
    const wa = document.getElementById('share-opt-whatsapp');
    if (wa) wa.href = `https://api.whatsapp.com/send?text=${encodeURIComponent(data.text)}`;

    // LinkedIn
    const li = document.getElementById('share-opt-linkedin');
    if (li) li.href = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(data.url)}`;

    // SMS
    const sms = document.getElementById('share-opt-sms');
    if (sms) sms.href = `sms:?&body=${encodeURIComponent(data.text)}`;

    // Mail
    const mail = document.getElementById('share-opt-mail');
    if (mail) mail.href = `mailto:?subject=${encodeURIComponent(data.title)}&body=${encodeURIComponent(data.text)}`;
  }

  function openShareModal() {
    updateShareLinks();
    widget.classList.add('open');
    fab.setAttribute('aria-expanded', 'true');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeShareModal() {
    widget.classList.remove('open');
    fab.setAttribute('aria-expanded', 'false');
    modal.setAttribute('aria-hidden', 'true');
  }

  function toggleShareModal() {
    if (widget.classList.contains('open')) {
      closeShareModal();
    } else {
      openShareModal();
    }
  }

  fab.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleShareModal();
  });

  closeBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeShareModal();
  });

  // Copy Link Action
  copyBtn?.addEventListener('click', async (e) => {
    e.stopPropagation();
    const data = getPageShareData();
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(data.url);
      } else if (linkInput) {
        linkInput.select();
        document.execCommand('copy');
      }
      copyBtn.classList.add('copied');
      if (copyText) copyText.textContent = 'Copied!';
      toast('Link copied to clipboard!', 'success');
      setTimeout(() => {
        copyBtn.classList.remove('copied');
        if (copyText) copyText.textContent = 'Copy';
      }, 2000);
    } catch (err) {
      toast('Failed to copy link', 'error');
    }
  });

  // Instagram Action
  const igBtn = document.getElementById('share-opt-instagram');
  igBtn?.addEventListener('click', async (e) => {
    e.stopPropagation();
    const data = getPageShareData();
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(data.text);
      }
      toast('Link & summary copied! Opening Instagram…', 'info');
      setTimeout(() => {
        window.open('https://www.instagram.com/', '_blank', 'noopener,noreferrer');
      }, 600);
    } catch (err) {
      window.open('https://www.instagram.com/', '_blank', 'noopener,noreferrer');
    }
  });

  // Native Web Share Action
  const nativeBtn = document.getElementById('share-opt-native');
  nativeBtn?.addEventListener('click', async (e) => {
    e.stopPropagation();
    const data = getPageShareData();
    if (navigator.share) {
      try {
        await navigator.share({
          title: data.title,
          text: `Check out ${data.title} on Mutual Fund Analysis`,
          url: data.url
        });
        closeShareModal();
      } catch (err) {
        if (err.name !== 'AbortError') {
          toast('Sharing not supported on this browser', 'info');
        }
      }
    } else {
      try {
        await navigator.clipboard.writeText(data.url);
        toast('Link copied! Paste anywhere to share.', 'success');
      } catch (err) {
        toast('Share: ' + data.url, 'info');
      }
    }
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (widget.classList.contains('open') && !widget.contains(e.target)) {
      closeShareModal();
    }
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && widget.classList.contains('open')) {
      closeShareModal();
    }
  });
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initSidebar();
  initSearch();
  initRangeInputs();
  initInfoTooltips();
  initShareWidget();

  // Attach ResizeObserver to main content container to handle sidebar animations & layout changes
  const mainContent = document.querySelector('.main-content');
  if (mainContent && typeof ResizeObserver !== 'undefined') {
    let roTimer = null;
    const ro = new ResizeObserver(() => {
      clearTimeout(roTimer);
      roTimer = setTimeout(window.triggerAllChartResizes, 40);
    });
    ro.observe(mainContent);
  }
});

// ── Info Tooltip Engine ────────────────────────────────────────
// Powers all ⓘ buttons. Reads data-t-* attributes and renders
// a smart positioned popup with structured content.
window.TOOLTIP_REGISTRY = {
  cagr: {
    title: "CAGR (Compound Annual Growth Rate)",
    what: "The annualized rate at which an investment grows, smoothing out fluctuations over time to show steady compounded growth.",
    interp: "Higher is better. Best for comparing long-term historical returns (>3 years) across different funds or benchmarks.",
    formula: "((End Value / Start Value) ^ (1 / Years)) - 1",
    link: "what is compound annual growth rate cagr mutual funds"
  },
  sharpe: {
    title: "Sharpe Ratio (Risk-Adjusted Return)",
    what: "Measures excess return earned per unit of total risk (volatility). It shows if a fund's high returns are due to smart investment decisions or taking excessive risk.",
    interp: "Higher is better. > 1.0 is good, > 2.0 is very good, > 3.0 is excellent. Only compare funds within the same category.",
    formula: "(Fund Return - Risk-Free Rate) / Standard Deviation",
    link: "sharpe ratio mutual funds definition"
  },
  sortino: {
    title: "Sortino Ratio (Downside Risk-Adjusted Return)",
    what: "Similar to Sharpe, but only penalizes downside (negative) volatility. It ignores upside volatility, which is generally positive for investors.",
    interp: "Higher is better. Often preferred over Sharpe for equity funds since upside volatility (surges) shouldn't count as risk.",
    formula: "(Fund Return - Risk-Free Rate) / Downside Standard Deviation",
    link: "sortino ratio mutual funds definition"
  },
  alpha: {
    title: "Alpha (Outperformance)",
    what: "Measures the excess return generated by a fund relative to its benchmark index return. It represents the value added by the fund manager's active strategies.",
    interp: "Positive alpha (>0) means the fund beat its benchmark after adjusting for risk. Higher is better.",
    formula: "Fund Return - [Risk-Free Rate + Beta * (Benchmark Return - Risk-Free Rate)]",
    link: "alpha mutual funds definition"
  },
  beta: {
    title: "Beta (Market Sensitivity)",
    what: "Measures a fund's volatility relative to its benchmark index. It shows how much the fund is expected to react to general market movements.",
    interp: "Beta = 1.0 matches the benchmark volatility. Beta > 1.0 means the fund is more volatile (aggressive). Beta < 1.0 is less volatile (defensive).",
    link: "beta mutual funds definition"
  },
  aum: {
    title: "AUM (Assets Under Management)",
    what: "The total market value of all financial assets managed by this mutual fund scheme.",
    interp: "Higher AUM indicates strong investor trust and scale. However, very large AUM in Small-Cap funds can limit the manager's ability to buy/sell small stocks quickly without impacting prices.",
    link: "assets under management aum mutual funds"
  },
  expense_ratio: {
    title: "Expense Ratio",
    what: "The annual fee charged by the mutual fund scheme to cover management fees, administrative costs, and marketing. It is deducted from the fund's NAV.",
    interp: "Lower is better. Every decimal point saved in the expense ratio directly increases your compounding return over the years.",
    link: "expense ratio mutual funds impact"
  },
  max_drawdown: {
    title: "Maximum Drawdown (Peak-to-Trough Loss)",
    what: "The maximum percentage drop in a fund's value from its peak to its lowest point (trough) before recovering. It measures the worst-case historical loss.",
    interp: "Lower (closer to 0%) is better. It represents the potential loss you could experience during a severe market correction or bear market.",
    link: "maximum drawdown mutual funds"
  },
  tracking_error: {
    title: "Tracking Error",
    what: "Measures the divergence between an Index/ETF fund's returns and the performance of the benchmark index it aims to replicate.",
    interp: "For passive funds (Index/ETFs), lower is better (aim for < 0.2%). For active funds, a higher tracking error shows the manager is taking active bets relative to the index.",
    link: "tracking error index funds"
  },
  info_ratio: {
    title: "Information Ratio",
    what: "Measures a fund manager's ability to generate excess returns relative to a benchmark index per unit of tracking error.",
    interp: "Higher is better. > 0.5 is good, > 1.0 is excellent. Shows consistency in beating the benchmark.",
    formula: "(Fund Return - Benchmark Return) / Tracking Error",
    link: "information ratio mutual funds"
  },
  sip: {
    title: "SIP (Systematic Investment Plan)",
    what: "An investment method where you invest a fixed sum at regular intervals (monthly/quarterly) rather than a one-time lumpsum.",
    interp: "Helps in Rupee Cost Averaging (buying more units when prices are low and fewer when high) and builds regular investing discipline.",
    link: "systematic investment plan sip benefits"
  },
  lumpsum: {
    title: "Lumpsum Investment",
    what: "Investing a large one-time amount into a mutual fund scheme all at once.",
    interp: "Ideal when you have surplus funds and the markets are corrected or fairly valued. Carries higher short-term risk compared to SIP.",
    link: "lumpsum investment vs sip mutual funds"
  },
  swp: {
    title: "SWP (Systematic Withdrawal Plan)",
    what: "Allows you to withdraw a fixed amount regularly (monthly/quarterly) from your mutual fund scheme, providing a steady stream of income.",
    interp: "Ideal for retirees. Highly tax-efficient compared to interest income or dividends, as withdrawals are treated as capital gains.",
    link: "systematic withdrawal plan swp mutual funds"
  },
  stp: {
    title: "STP (Systematic Transfer Plan)",
    what: "Allows you to transfer a fixed amount or gains from one mutual fund scheme (usually debt/liquid) to another (usually equity) within the same fund house.",
    interp: "Helps in parking lump sum money in a low-risk fund and gradually moving it into equities to avoid market-timing risks.",
    link: "systematic transfer plan stp mutual funds"
  },
  step_up: {
    title: "Step-up SIP",
    what: "An option to increase your monthly SIP contribution by a fixed percentage or amount every year (e.g., in line with salary hikes).",
    interp: "Drastically boosts wealth creation and reduces the time needed to meet long-term financial goals due to the power of compounding.",
    link: "step up sip benefits calculator"
  },
  xirr: {
    title: "XIRR (Extended Internal Rate of Return)",
    what: "The true annualised rate of return for a series of cash flows (investments and redemptions) occurring at irregular intervals.",
    interp: "This is the most accurate way to measure personal portfolio or SIP performance, as standard CAGR assumes one-time investment.",
    link: "what is xirr in mutual funds"
  },
  net_worth: {
    title: "Net Worth",
    what: "The total value of everything you own (assets) minus everything you owe (liabilities).",
    interp: "The ultimate metric of financial health. It should grow steadily over time as you invest more and pay down debt.",
    link: "how to calculate personal net worth"
  },
  turnover: {
    title: "Portfolio Turnover Ratio",
    what: "The percentage of a fund's holdings that have been replaced or bought/sold by the fund manager over the past year.",
    interp: "Lower turnover (<30%) implies a buy-and-hold strategy. Higher turnover indicates active trading, which can increase transaction costs.",
    link: "portfolio turnover ratio mutual funds"
  },
  pe_ratio: {
    title: "P/E Ratio (Price-to-Earnings)",
    what: "The weighted average valuation ratio of the companies in the fund's portfolio. It compares the stock price to its earnings per share.",
    interp: "High P/E indicates growth-oriented stocks (premium valuation). Low P/E indicates value-oriented stocks (cheaper valuation).",
    link: "price to earnings pe ratio mutual funds"
  },
  pb_ratio: {
    title: "P/B Ratio (Price-to-Book)",
    what: "Compares the portfolio companies' stock market value relative to their book value (assets minus liabilities).",
    interp: "Used to assess valuation. Lower P/B can indicate value investing style, while high P/B is typical for technology or service sector growth funds.",
    link: "price to book pb ratio mutual funds"
  },
  volatility: {
    title: "Volatility (Standard Deviation)",
    what: "Measures the dispersion of a fund's returns relative to its average return. It quantifies how widely the fund's price swings up and down.",
    interp: "Lower volatility is preferred by conservative investors as it indicates a steadier, less bumpy investment journey.",
    link: "volatility standard deviation mutual funds"
  },
  rating: {
    title: "CRISIL Mutual Fund Rating",
    what: "A rank-based rating from CRISIL (1 to 5 stars) evaluating mutual funds based on return, risk-adjusted performance, and liquidity.",
    interp: "5 Stars is best (top 10% of category). 4 Stars is next 22.5%. A higher rating indicates better category performance.",
    link: "crisil mutual fund ratings methodology"
  },
  rank: {
    title: "Percentile / Quartile Rank",
    what: "Indicates how a fund's performance ranks relative to all other funds in the exact same category over a specific period.",
    interp: "Lower rank (e.g. 1st out of 20) or Q1 (Quartile 1) is best. Shows consistent outperformance compared to immediate peers.",
    link: "mutual fund quartile rankings explained"
  },
  lock_in: {
    title: "Lock-in Period",
    what: "The minimum time duration during which you cannot redeem or withdraw your invested capital from the mutual fund scheme.",
    interp: "Common in ELSS (Equity Linked Savings Schemes) tax-saving funds (3-year lock-in) and retirement/children's solution funds.",
    link: "lock in period mutual funds"
  },
  risk: {
    title: "Riskometer Level",
    what: "A standardized pictorial depiction of the risk level of the mutual fund scheme, ranging from Low to Very High, mandated by SEBI.",
    interp: "Ensure the riskometer level matches your personal risk tolerance (e.g. Equities are usually Very High; Liquid/Debt is Low to Moderate).",
    link: "sebi mutual fund riskometer rules"
  },
  exit_load: {
    title: "Exit Load",
    what: "A fee charged by the fund house when you redeem or sell your mutual fund units before a specified timeframe (e.g., 1% if redeemed within 1 year).",
    interp: "Discourages short-term withdrawals. Always review exit load details to avoid unnecessary deduction during emergency withdrawals.",
    link: "exit load mutual funds rules"
  },
  downside_capture: {
    title: "Downside Capture Ratio",
    what: "Shows how much a fund lost relative to its benchmark index during periods when the benchmark was down.",
    interp: "Lower is better (e.g., < 80% means the fund lost only 80% as much as the market index during downturns).",
    link: "downside capture ratio mutual funds"
  },
  upside_capture: {
    title: "Upside Capture Ratio",
    what: "Shows how much a fund gained relative to its benchmark index during periods when the benchmark was up.",
    interp: "Higher is better (e.g., > 110% means the fund gained 110% of what the index gained during positive market phases).",
    link: "upside capture ratio mutual funds"
  },
  portfolio_overlap: {
    title: "Portfolio Overlap",
    what: "The percentage of common stock holdings between two mutual fund schemes.",
    interp: "Lower overlap is better for diversification (aim for < 30%). High overlap (> 50%) means you are holding identical stocks under two different names.",
    link: "portfolio overlap mutual funds diversification"
  },
  rolling_returns: {
    title: "Rolling Returns",
    what: "Calculates returns for all possible overlapping holding periods (e.g., daily 3-year returns) over a long timeline, rather than just trailing returns.",
    interp: "Eliminates point-to-point bias and shows the actual probability of getting a specific return at any random point in time.",
    link: "rolling returns mutual funds importance"
  },
  solvency_ratio: {
    title: "Solvency Ratio",
    what: "Measures an individual's ability to cover long-term debt liabilities using their net worth (excluding mortgage/primary home if possible).",
    interp: "Solvency Ratio = Net Worth / Total Assets. Higher is better (aim for > 50%). It shows how vulnerable you are to debt defaults.",
    link: "solvency ratio personal finance"
  },
  funds_that_matter: {
    title: "Funds That Matter",
    what: "We filter out regular schemes and dividend payout schemes, focusing only on active Direct-Growth funds and ETFs. This simplifies your research by focusing on what matters.",
    interp: "Direct growth funds save commission fees, compounding to higher returns over time. ETFs offer low-cost stock index tracking.",
    link: "direct vs regular mutual funds commission difference"
  },
  benchmark_monitor: {
    title: "Benchmark Monitor",
    what: "Tracks the performance of major stock market indices (like Nifty 50, Nifty Midcap, Nifty Smallcap, etc.) over different time horizons.",
    interp: "Helps you see how different market segments are performing. A mutual fund is generally expected to beat its respective benchmark index over the long term.",
    link: "what is mutual fund benchmark comparison index"
  },
  category_return_meter: {
    title: "Category Return Meter",
    what: "Shows performance metrics (minimum, average, median, and maximum returns) for different mutual fund categories over a selected period (1Y, 3Y, or 5Y).",
    interp: "Helps you see the range of returns generated within a category, highlighting both the average performance and the dispersion between the best and worst performing funds.",
    link: "mutual fund category returns analysis"
  },
  category_analysis: {
    title: "Category Analysis",
    what: "Aggregates key metrics like total fund count, average proprietary model score, average returns, best returns, average Sharpe ratio, and score distribution for each mutual fund sub-category.",
    interp: "Allows you to compare different sub-categories (e.g. Large Cap vs Small Cap) to see which groups offer better risk-adjusted returns and a higher density of strong performers.",
    link: "mutual fund category performance comparison"
  },
  funds: {
    title: "Fund Count",
    what: "The total number of active direct growth mutual fund schemes and ETFs within this specific category or sub-category.",
    interp: "Allows you to see how many choices are available in this peer group. More options means more competition, but can also lead to choice paralysis.",
    link: "mutual fund categories list and classification"
  },
  category_min: {
    title: "Category Minimum Return",
    what: "The worst-performing fund's return in this category over the selected timeframe.",
    interp: "Highlights the downside risk and potential underperformance if you pick the wrong fund in this category."
  },
  category_avg: {
    title: "Category Average Return",
    what: "The mathematical average return of all funds within this category.",
    interp: "Serves as a baseline benchmark. A good active fund manager should consistently beat this average."
  },
  category_median: {
    title: "Category Median Return",
    what: "The midpoint return value of the category—exactly half the funds performed better, and half performed worse.",
    interp: "More representative of a typical investor experience than the average, as it is not skewed by single outlier funds."
  },
  category_max: {
    title: "Category Maximum Return",
    what: "The best-performing fund's return in this category over the selected timeframe.",
    interp: "Shows the maximum potential return generated by the top fund manager in this peer group."
  },
  model_score: {
    title: "Model Score",
    what: "Our proprietary composite score evaluating a fund's risk-adjusted performance, consistency, and fees relative to its sub-category peers.",
    interp: "Higher is better. 80+ is excellent, 70-80 is good, 50-70 is fair, and <50 is weak. It provides a simple single metric to filter out underperforming schemes."
  },
  fund_age: {
    title: "Fund Age",
    what: "The number of years since the inception of the mutual fund scheme.",
    interp: "Older funds (>5 years) are generally preferred as their performance has been tested across different market cycles."
  }
};

(function() {
  let activeBtn = null;
  let tooltip = null;
  function buildTooltip(btn) {
    const key = btn.getAttribute('data-t-link-key') || btn.getAttribute('data-t-key');
    const reg = (key && window.TOOLTIP_REGISTRY && window.TOOLTIP_REGISTRY[key]) || {};

    const title   = btn.getAttribute('data-t-title')   || reg.title || btn.getAttribute('aria-label') || 'Info';
    const what    = btn.getAttribute('data-t-what')    || reg.what;
    const interp  = btn.getAttribute('data-t-interp')  || reg.interp;
    const formula = btn.getAttribute('data-t-formula') || reg.formula;
    const range   = btn.getAttribute('data-t-range')   || reg.range;
    const note    = btn.getAttribute('data-t-note')    || reg.note;
    const link    = btn.getAttribute('data-t-link')    || reg.link;

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
        const items = typeof range === 'string' ? JSON.parse(range) : range;
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
    if (link) {
      const href = link.startsWith('http') ? link : `https://www.google.com/search?q=${encodeURIComponent(link)}`;
      sections += `<div class="tooltip-divider"></div><div class="tooltip-section" style="margin-top: 4px; text-align: center;">
        <a href="${href}" target="_blank" rel="noopener noreferrer" class="tooltip-readmore-btn">Read more &rarr;</a>
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
    if (activeBtn === btn && (tooltip || document.querySelector('.info-tooltip'))) {
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
      if (tooltip) {
        positionTooltip(btn, tooltip);
        requestAnimationFrame(() => {
          if (tooltip) tooltip.classList.add('visible');
        });
      }
    });
  }

  function hideTooltip() {
    document.querySelectorAll('.info-tooltip').forEach(el => el.remove());
    tooltip = null;
    if (activeBtn) {
      activeBtn.classList.remove('active');
      activeBtn = null;
    }
  }

  window.openMsiTooltip = function(btn) {
    if (btn) showTooltipFor(btn);
  };
  window.closeMsiTooltip = hideTooltip;

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
    if (tooltip && !tooltip.contains(e.target) && !e.target.closest('.info-btn')) hideTooltip();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') hideTooltip();
  });
  // Tooltip mouseleave
  document.addEventListener('mouseleave', e => {
    if (tooltip && e.target === tooltip) hideTooltip();
  }, true);
})();


