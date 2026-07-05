
const ALL_INDICES = 1;


/* ═══════════════════════════════════════════════════════════════════════════
   BACKTESTER V2 — Client-Side Logic
   ═══════════════════════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────────────────────
let assetType = 'scheme';
let selectedSearchResult = null;
let assets = [];           // [{label, source_type, source_id, inception_date, rules:[]}]
let latestResult = null;   // last backtest result for ledger filtering
let allTransactions = [];

// Trigger modal state
let editingTrigger = { assetIdx: null, ruleIdx: null };
let triggerConditions = [];  // [{signal_type, params, operator, value}]

// Benchmark selection
let benchmarkResult = null;

// ── Asset type toggle ──────────────────────────────────────────────────────
function setAssetType(type) {
  assetType = type;
  document.getElementById('toggleMF').classList.toggle('active', type === 'scheme');
  document.getElementById('toggleIdx').classList.toggle('active', type === 'index');
  document.getElementById('assetSearch').value = '';
  document.getElementById('searchDropdown').classList.remove('open');
  selectedSearchResult = null;
  document.getElementById('btnAddAsset').disabled = true;
}

// ── Search logic ───────────────────────────────────────────────────────────
let searchTimer = null;
const searchInput = document.getElementById('assetSearch');
const searchDropdown = document.getElementById('searchDropdown');

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  const q = searchInput.value.trim();
  selectedSearchResult = null;
  document.getElementById('btnAddAsset').disabled = true;
  if (q.length < 2) { searchDropdown.classList.remove('open'); return; }
  searchDropdown.innerHTML = '<div class="search-loading">🔍 Searching…</div>';
  searchDropdown.classList.add('open');
  searchTimer = setTimeout(() => doSearch(q, 'searchDropdown', onSearchSelect), 350);
});

searchInput.addEventListener('keydown', e => {
  if (e.key === 'Escape') { searchDropdown.classList.remove('open'); }
});

document.addEventListener('click', e => {
  if (!document.getElementById('searchWrap').contains(e.target)) {
    searchDropdown.classList.remove('open');
  }
  if (!document.getElementById('benchmarkSearch')?.parentElement.contains(e.target)) {
    document.getElementById('benchmarkDropdown')?.classList.remove('open');
  }
});

async function doSearch(q, dropdownId, onSelect, typeOverride) {
  const type = typeOverride || assetType;
  const dd = document.getElementById(dropdownId);
  try {
    const res = await fetch(`/portfolio/backtester/fund-search/?q=${encodeURIComponent(q)}&type=${type}`);
    const data = await res.json();
    renderSearchDropdown(data.results || [], dd, onSelect);
  } catch {
    dd.innerHTML = '<div class="search-empty">Error fetching results.</div>';
  }
}

function renderSearchDropdown(results, dd, onSelect) {
  if (!results.length) {
    dd.innerHTML = '<div class="search-empty">No results found.</div>';
    return;
  }
  dd.innerHTML = results.map((r, i) => `
    <div class="search-result-item" onclick='onSelectItem(${JSON.stringify(r).replace(/'/g,"&#39;")})'>
      <span class="sri-badge ${r.type === 'scheme' ? 'mf' : 'idx'}">${r.type === 'scheme' ? 'MF' : 'IDX'}</span>
      <div>
        <div class="sri-name">${r.name}</div>
        <div class="sri-sub">${r.sub || ''}${r.inception_date ? ' · Since ' + r.inception_date : ''}</div>
      </div>
    </div>`).join('');
  dd.classList.add('open');
  // Store onSelect callback on the dropdown
  dd._onSelect = onSelect;
}

// Global dispatcher for onclick in rendered HTML
function onSelectItem(r) {
  // Determine which dropdown is open
  const sd = document.getElementById('searchDropdown');
  const bd = document.getElementById('benchmarkDropdown');
  if (sd.classList.contains('open') && sd._onSelect) {
    sd._onSelect(r);
  } else if (bd && bd.classList.contains('open') && bd._onSelect) {
    bd._onSelect(r);
  }
}

function onSearchSelect(result) {
  selectedSearchResult = result;
  document.getElementById('assetSearch').value = result.name;
  searchDropdown.classList.remove('open');
  document.getElementById('btnAddAsset').disabled = false;
}

// ── Add asset ─────────────────────────────────────────────────────────────
function addSelectedAsset() {
  if (!selectedSearchResult) return;
  const r = selectedSearchResult;
  // Prevent duplicates
  if (assets.find(a => a.source_id === r.id)) {
    alert('This asset is already in your list.');
    return;
  }
  assets.push({
    label: r.name,
    source_type: r.type === 'scheme' ? 'scheme' : 'index',
    source_id: r.id,
    inception_date: r.inception_date || null,
    rules: [],
  });
  selectedSearchResult = null;
  document.getElementById('assetSearch').value = '';
  document.getElementById('btnAddAsset').disabled = true;
  renderAssets();
}

function removeAsset(idx) {
  assets.splice(idx, 1);
  renderAssets();
}

// ── Render asset list ─────────────────────────────────────────────────────
function renderAssets() {
  const list = document.getElementById('assetList');
  const empty = document.getElementById('assetEmpty');
  if (!assets.length) {
    empty.style.display = '';
    list.innerHTML = '';
    list.appendChild(empty);
    updateAddRebalanceVisibility();
    return;
  }
  empty.style.display = 'none';
  updateAddRebalanceVisibility();
  list.innerHTML = assets.map((a, ai) => `
    <div class="asset-card" id="assetCard-${ai}">
      <div class="asset-card-header">
        <div class="asset-card-icon ${a.source_type === 'scheme' ? 'mf' : 'idx'}">
          ${a.source_type === 'scheme' ? '📈' : '📊'}
        </div>
        <div class="asset-card-info">
          <div class="asset-card-name" title="${a.label}">${a.label}</div>
          <div class="asset-card-meta">
            <span>${a.source_type === 'scheme' ? 'Mutual Fund' : 'Index'}</span>
            ${a.inception_date ? `<span>· Since ${a.inception_date}</span>` : ''}
            <span>· ${a.source_id}</span>
          </div>
        </div>
        <div class="asset-card-actions">
          <button class="btn-remove-asset" onclick="removeAsset(${ai})" title="Remove">✕</button>
        </div>
      </div>

      <!-- STEP 2: Rules -->
      <div class="asset-rules" id="rules-${ai}">
        <div class="bt-step-label" style="margin-bottom:6px">
          <span class="step-num">2</span> Rules for this asset
        </div>
        ${a.rules.map((r, ri) => renderRuleCard(ai, ri, r)).join('')}
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
          <button class="btn-add-rule" onclick="addRule(${ai}, 'sip')">+ SIP</button>
          <button class="btn-add-rule" onclick="addRule(${ai}, 'lumpsum')">+ Lumpsum</button>
          <button class="btn-add-rule" onclick="addRule(${ai}, 'swp')">+ SWP</button>
          <button class="btn-add-rule" onclick="addRule(${ai}, 'sell')">+ Sell</button>
          <button class="btn-add-rule" onclick="addRule(${ai}, 'switch')">+ Switch</button>
        </div>
      </div>
    </div>`).join('');
}

// ── Rules ──────────────────────────────────────────────────────────────────
function addRule(assetIdx, ruleType) {
  const a = assets[assetIdx];
  if (ruleType === 'sip') {
    a.rules.push({ rule_type: 'sip', amount: 5000, frequency: 'monthly',
      start_date: '', end_date: '', step_up: null, trigger: null });
  } else if (ruleType === 'lumpsum') {
    a.rules.push({ rule_type: 'lumpsum', amount: 50000, lumpsum_date: '', trigger: null });
  } else if (ruleType === 'swp') {
    a.rules.push({ rule_type: 'swp', amount: 5000, amount_type: 'amount',
      frequency: 'monthly', start_date: '', end_date: '', trigger: null });
  } else if (ruleType === 'sell') {
    a.rules.push({ rule_type: 'sell', amount: 100, amount_type: 'pct',
      lumpsum_date: '', trigger: null });
  } else if (ruleType === 'switch') {
    a.rules.push({ rule_type: 'switch', amount: 100, amount_type: 'pct',
      switch_from_id: a.source_id, switch_to_id: '', switch_date: '', trigger: null });
  }
  renderAssets();
  setTimeout(() => {
    document.getElementById(`assetCard-${assetIdx}`)?.scrollIntoView({behavior:'smooth', block:'nearest'});
  }, 50);
}

function removeRule(assetIdx, ruleIdx) {
  assets[assetIdx].rules.splice(ruleIdx, 1);
  renderAssets();
}

function renderRuleCard(ai, ri, rule) {
  const triggerLabel = rule.trigger
    ? `⚡ Trigger set (${rule.trigger.conditions?.length || 1} condition${rule.trigger.conditions?.length > 1 ? 's' : ''})`
    : '+ Add Trigger Condition';
  const hasTrigger = !!rule.trigger;

  if (rule.rule_type === 'sip') {
    const su = rule.step_up;
    return `
    <div class="rule-card">
      <div class="rule-card-header">
        <span class="rule-type-badge sip">SIP</span>
        <button class="btn-remove-rule" onclick="removeRule(${ai},${ri})">✕</button>
      </div>
      <div class="rule-fields">
        <div class="field-group">
          <label>Amount (₹)</label>
          <input type="number" value="${rule.amount}" min="1"
            onchange="updateRule(${ai},${ri},'amount',+this.value)" />
        </div>
        <div class="field-group">
          <label>Frequency</label>
          <select onchange="updateRule(${ai},${ri},'frequency',this.value)">
            <option value="daily" ${rule.frequency==='daily'?'selected':''}>Daily</option>
            <option value="weekly" ${rule.frequency==='weekly'?'selected':''}>Weekly</option>
            <option value="monthly" ${rule.frequency==='monthly'?'selected':''}>Monthly</option>
            <option value="quarterly" ${rule.frequency==='quarterly'?'selected':''}>Quarterly</option>
          </select>
        </div>
        <div class="field-group">
          <label>Start Date</label>
          <input type="date" value="${rule.start_date||''}"
            onchange="updateRule(${ai},${ri},'start_date',this.value)" />
        </div>
        <div class="field-group">
          <label>End Date</label>
          <input type="date" value="${rule.end_date||''}"
            onchange="updateRule(${ai},${ri},'end_date',this.value)" />
        </div>
      </div>
      <label class="stepup-toggle">
        <input type="checkbox" ${su?'checked':''} onchange="toggleStepUp(${ai},${ri},this.checked)">
        Step-up SIP
      </label>
      <div class="stepup-fields ${su?'open':''}" id="stepup-${ai}-${ri}">
        <div class="field-group">
          <label>Type</label>
          <select onchange="updateStepUp(${ai},${ri},'step_type',this.value)">
            <option value="pct" ${su?.step_type==='pct'?'selected':''}>% per period</option>
            <option value="abs" ${su?.step_type==='abs'?'selected':''}>₹ per period</option>
          </select>
        </div>
        <div class="field-group">
          <label>Amount</label>
          <input type="number" value="${su?.step_amount||10}" min="0"
            onchange="updateStepUp(${ai},${ri},'step_amount',+this.value)" />
        </div>
        <div class="field-group">
          <label>Frequency</label>
          <select onchange="updateStepUp(${ai},${ri},'step_frequency',this.value)">
            <option value="annual" ${su?.step_frequency==='annual'?'selected':''}>Annually</option>
            <option value="6month" ${su?.step_frequency==='6month'?'selected':''}>Every 6 months</option>
          </select>
        </div>
      </div>
      <button class="btn-trigger ${hasTrigger?'has-trigger':''}"
        onclick="openTriggerModal(${ai},${ri})">
        ⚡ ${triggerLabel}
      </button>
    </div>`;
    } else if (rule.rule_type === 'swp') {
    return `
    <div class="rule-card">
      <div class="rule-card-header">
        <span class="rule-type-badge sip">SWP</span>
        <button class="btn-remove-rule" onclick="removeRule(${ai},${ri})">✕</button>
      </div>
      <div class="rule-fields">
        <div class="field-group">
          <label>Withdrawal Type</label>
          <select onchange="updateRule(${ai},${ri},'swp_type',this.value)">
            <option value="amount" ${rule.swp_type==='amount'?'selected':''}>Amount (₹)</option>
            <option value="units" ${rule.swp_type==='units'?'selected':''}>Units</option>
            <option value="pct" ${rule.swp_type==='pct'?'selected':''}>% of holding</option>
          </select>
        </div>
        <div class="field-group">
          <label>Amount/Units/%</label>
          <input type="number" value="${rule.amount||0}" min="1" onchange="updateRule(${ai},${ri},'amount',+this.value)" />
        </div>
        <div class="field-group">
          <label>Frequency</label>
          <select onchange="updateRule(${ai},${ri},'frequency',this.value)">
            <option value="monthly" ${rule.frequency==='monthly'?'selected':''}>Monthly</option>
            <option value="quarterly" ${rule.frequency==='quarterly'?'selected':''}>Quarterly</option>
            <option value="annually" ${rule.frequency==='annually'?'selected':''}>Annually</option>
          </select>
        </div>
        <div class="field-group">
          <label>Start Date</label>
          <input type="date" value="${rule.start_date||''}" onchange="updateRule(${ai},${ri},'start_date',this.value)" />
        </div>
      </div>
      <button class="btn-trigger ${hasTrigger?'has-trigger':''}" onclick="openTriggerModal(${ai},${ri})">⚡ ${triggerLabel}</button>
    </div>`;
  } else if (rule.rule_type === 'sell') {
    return `
    <div class="rule-card">
      <div class="rule-card-header">
        <span class="rule-type-badge" style="background:var(--red-400);color:white">SELL</span>
        <button class="btn-remove-rule" onclick="removeRule(${ai},${ri})">✕</button>
      </div>
      <div class="rule-fields">
        <div class="field-group">
          <label>Sell Type</label>
          <select onchange="updateRule(${ai},${ri},'sell_type',this.value)">
            <option value="amount" ${rule.sell_type==='amount'?'selected':''}>Amount (₹)</option>
            <option value="units" ${rule.sell_type==='units'?'selected':''}>Units</option>
            <option value="pct" ${rule.sell_type==='pct'?'selected':''}>% of holding</option>
          </select>
        </div>
        <div class="field-group">
          <label>Amount/Units/%</label>
          <input type="number" value="${rule.amount||0}" min="1" onchange="updateRule(${ai},${ri},'amount',+this.value)" />
        </div>
        <div class="field-group">
          <label>Date (or trigger)</label>
          <input type="date" value="${rule.lumpsum_date||''}" onchange="updateRule(${ai},${ri},'lumpsum_date',this.value)" />
        </div>
      </div>
      <button class="btn-trigger ${hasTrigger?'has-trigger':''}" onclick="openTriggerModal(${ai},${ri})">⚡ ${triggerLabel}</button>
    </div>`;
  } else if (rule.rule_type === 'switch') {
    return `
    <div class="rule-card">
      <div class="rule-card-header">
        <span class="rule-type-badge" style="background:var(--indigo-400);color:white">SWITCH</span>
        <button class="btn-remove-rule" onclick="removeRule(${ai},${ri})">✕</button>
      </div>
      <div class="rule-fields">
        <div class="field-group">
          <label>Switch To</label>
          <select onchange="updateRule(${ai},${ri},'switch_to_id',this.value)">
            <option value="">-- Select Asset --</option>
            ${assets.map((a, i) => i !== ai ? `<option value="${a.source_id}" ${rule.switch_to_id===a.source_id?'selected':''}>${a.label}</option>` : '').join('')}
          </select>
        </div>
        <div class="field-group">
          <label>Amount Type</label>
          <select onchange="updateRule(${ai},${ri},'amount_type',this.value)">
            <option value="amount" ${rule.amount_type==='amount'?'selected':''}>Amount (₹)</option>
            <option value="units" ${rule.amount_type==='units'?'selected':''}>Units</option>
            <option value="pct" ${rule.amount_type==='pct'?'selected':''}>% of holding</option>
          </select>
        </div>
        <div class="field-group">
          <label>Value</label>
          <input type="number" value="${rule.amount||0}" min="1" onchange="updateRule(${ai},${ri},'amount',+this.value)" />
        </div>
        <div class="field-group">
          <label>Date (or trigger)</label>
          <input type="date" value="${rule.switch_date||''}" onchange="updateRule(${ai},${ri},'switch_date',this.value)" />
        </div>
      </div>
      <button class="btn-trigger ${hasTrigger?'has-trigger':''}" onclick="openTriggerModal(${ai},${ri})">⚡ ${triggerLabel}</button>
    </div>`;
  } else {
    // Lumpsum
    return `
    <div class="rule-card">
      <div class="rule-card-header">
        <span class="rule-type-badge lumpsum">LUMPSUM</span>
        <button class="btn-remove-rule" onclick="removeRule(${ai},${ri})">✕</button>
      </div>
      <div class="rule-fields">
        <div class="field-group">
          <label>Amount (₹)</label>
          <input type="number" value="${rule.amount}" min="1"
            onchange="updateRule(${ai},${ri},'amount',+this.value)" />
        </div>
        <div class="field-group">
          <label>Date (leave blank if triggered)</label>
          <input type="date" value="${rule.lumpsum_date||''}"
            onchange="updateRule(${ai},${ri},'lumpsum_date',this.value)" />
        </div>
      </div>
      <button class="btn-trigger ${hasTrigger?'has-trigger':''}"
        onclick="openTriggerModal(${ai},${ri})">
        ⚡ ${triggerLabel}
      </button>
    </div>`;
  }
}

function updateRule(ai, ri, key, val) {
  assets[ai].rules[ri][key] = val;
}

function toggleStepUp(ai, ri, enabled) {
  if (enabled) {
    assets[ai].rules[ri].step_up = { step_type: 'pct', step_amount: 10, step_frequency: 'annual' };
  } else {
    assets[ai].rules[ri].step_up = null;
  }
  document.getElementById(`stepup-${ai}-${ri}`).classList.toggle('open', enabled);
}

function updateStepUp(ai, ri, key, val) {
  if (!assets[ai].rules[ri].step_up) return;
  assets[ai].rules[ri].step_up[key] = val;
}

// ── Settings toggles ───────────────────────────────────────────────────────
const toggleStates = { exitload: false, tax: false, inflation: false, mc: false };
function toggleSetting(key) {
  toggleStates[key] = !toggleStates[key];
  const row = document.getElementById(`toggle${key.charAt(0).toUpperCase()+key.slice(1)}`);
  if (row) row.classList.toggle('on', toggleStates[key]);
  if (key === 'tax')       document.getElementById('taxExpanded').classList.toggle('open', toggleStates.tax);
  if (key === 'inflation') document.getElementById('inflationExpanded').classList.toggle('open', toggleStates.inflation);
  if (key === 'mc')        document.getElementById('mcExpanded').classList.toggle('open', toggleStates.mc);
}

function onInflationModeChange() {
  const mode = document.getElementById('inflationMode').value;
  document.getElementById('inflationRateGroup').style.display = mode === 'manual' ? '' : 'none';
  document.getElementById('inflationWBNote').style.display = mode === 'wbgapi' ? '' : 'none';
}

// ── Rebalance ─────────────────────────────────────────────────────────────
let rebalanceRule = null;

function updateAddRebalanceVisibility() {
  const wrap = document.getElementById('addRebalanceWrap');
  const step = document.getElementById('stepRebalance');
  if (!wrap) return;
  if (assets.length >= 2 && !rebalanceRule) {
    wrap.style.display = '';
    step.style.display = 'none';
  } else if (rebalanceRule) {
    wrap.style.display = 'none';
    step.style.display = '';
    renderRebalanceWeights();
  } else {
    wrap.style.display = 'none';
    step.style.display = 'none';
  }
}

function addRebalance() {
  // Default equal weights
  const weights = {};
  const equalW = assets.length > 0 ? Math.round(100 / assets.length * 10) / 10 : 50;
  assets.forEach(a => weights[a.source_id] = equalW);
  rebalanceRule = { target_weights: weights, mode: 'frequency',
    frequency: 'annually', anchor_month: 1, drift_threshold: 5, drift_type: 'absolute' };
  updateAddRebalanceVisibility();
}

function removeRebalance() {
  rebalanceRule = null;
  updateAddRebalanceVisibility();
}

function renderRebalanceWeights() {
  if (!rebalanceRule) return;
  const table = document.getElementById('rebalanceWeightsTable');
  if (!table) return;
  const weights = rebalanceRule.target_weights;
  const total = Object.values(weights).reduce((s, v) => s + v, 0);
  table.innerHTML = `
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">Target Weights — must sum to 100% (currently ${total.toFixed(1)}%)</div>
    ${assets.map(a => `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span style="flex:1;font-size:11px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${a.label}</span>
        <input type="number" min="0" max="100" step="0.5"
          value="${weights[a.source_id] || 0}"
          style="width:70px"
          onchange="rebalanceRule.target_weights['${a.source_id}']=+this.value;renderRebalanceWeights()" />
        <span style="font-size:11px;color:var(--text-muted)">%</span>
      </div>`).join('')}
    <div style="border-top:1px solid var(--border);margin-top:6px;padding-top:6px;font-size:11px;color:${Math.abs(total-100)>0.5?'var(--red-400)':'var(--emerald-400)'};font-weight:600">
      Total: ${total.toFixed(1)}%
    </div>`;
}

// ── Benchmark search ───────────────────────────────────────────────────────
const benchSearch = document.getElementById('benchmarkSearch');
const benchDropdown = document.getElementById('benchmarkDropdown');
let benchTimer = null;

benchSearch.addEventListener('input', () => {
  clearTimeout(benchTimer);
  const q = benchSearch.value.trim();
  if (q.length < 2) { benchDropdown.classList.remove('open'); return; }
  benchDropdown.innerHTML = '<div class="search-loading">🔍 Searching…</div>';
  benchDropdown.classList.add('open');
  benchTimer = setTimeout(() => doSearch(q, 'benchmarkDropdown', onBenchSelect, 'all'), 350);
});

function onBenchSelect(result) {
  document.getElementById('benchmarkId').value = result.id;
  document.getElementById('benchmarkType').value = result.type === 'scheme' ? 'scheme' : 'index';
  benchSearch.value = result.name;
  const sel = document.getElementById('benchmarkSelected');
  sel.textContent = `✓ ${result.name}`;
  sel.style.display = '';
  benchDropdown.classList.remove('open');
  // benchDropdown._onSelect = null;
}

// ── Build plan payload ─────────────────────────────────────────────────────
function buildPlan() {
  const simStart = document.getElementById('simStart').value || null;
  const simEnd = document.getElementById('simEnd').value || null;
  const benchId = document.getElementById('benchmarkId').value;
  const benchType = document.getElementById('benchmarkType').value || 'index';

  const settings = {
    start_date: simStart,
    end_date: simEnd,
    benchmark_type: benchType || 'index',
    benchmark_id: benchId || '',
    synthetic_debt_rate: parseFloat(document.getElementById('debtRate').value) || 7,
    transaction_cost: parseFloat(document.getElementById('txCost').value) || 0,
    exit_load_enabled: toggleStates.exitload,
    // Tax (Phase 4)
    tax_enabled: toggleStates.tax,
    tax_equity_stcg: parseFloat(document.getElementById('stcgRate').value) || 20,
    tax_equity_ltcg: parseFloat(document.getElementById('ltcgRate').value) || 12.5,
    tax_ltcg_exemption: parseFloat(document.getElementById('ltcgExemption').value) || 125000,
    tax_debt_rate: parseFloat(document.getElementById('debtTaxRate').value) || 30,
    // Inflation (Phase 4)
    inflation_enabled: toggleStates.inflation,
    inflation_mode: document.getElementById('inflationMode').value,
    inflation_rate: parseFloat(document.getElementById('inflationRate').value) || 5,
    // Monte Carlo (Phase 5)
    mc_enabled: toggleStates.mc,
    mc_simulations: parseInt(document.getElementById('mcSimulations')?.value) || 500,
    mc_horizon_years: parseInt(document.getElementById('mcHorizon')?.value) || 10,
  };

  const planAssets = assets.map(a => ({
    label: a.label,
    source_type: a.source_type,
    source_id: a.source_id,
    rules: a.rules.map(r => ({
      rule_type: r.rule_type,
      amount: r.amount || 0,
      frequency: r.frequency || 'monthly',
      start_date: r.start_date || null,
      end_date: r.end_date || null,
      step_up: r.step_up || null,
      lumpsum_date: r.lumpsum_date || null,
      amount_type: r.amount_type || 'amount',
      switch_from_id: r.switch_from_id || null,
      switch_to_id: r.switch_to_id || null,
      switch_date: r.switch_date || null,
      trigger: r.trigger || null,
    })),
  }));

  const rebalance = rebalanceRule ? {
    target_weights: rebalanceRule.target_weights,
    mode: document.getElementById('rbMode')?.value || 'frequency',
    frequency: document.getElementById('rbFrequency')?.value || 'annually',
    anchor_month: parseInt(document.getElementById('rbAnchorMonth')?.value || '1'),
    drift_threshold: parseFloat(document.getElementById('rbDrift')?.value || '5'),
    drift_type: 'absolute',
  } : null;

  return { assets: planAssets, settings, rebalance };
}

// ── Validation (client-side) ───────────────────────────────────────────────
function validatePlan() {
  const errors = [];
  if (!assets.length) errors.push('Add at least one asset.');
  assets.forEach((a, ai) => {
    if (!a.rules.length) errors.push(`Asset "${a.label}" has no rules — add a SIP or Lumpsum.`);
    a.rules.forEach((r, ri) => {
      if ((r.amount || 0) <= 0) errors.push(`Rule ${ri+1} on "${a.label}": amount must be > 0.`);
      if (r.rule_type === 'lumpsum' && !r.lumpsum_date && !r.trigger) {
        errors.push(`Lumpsum rule on "${a.label}" needs a date or a trigger condition.`);
      }
    });
  });

  const errEl = document.getElementById('validationErrors');
  const errList = document.getElementById('errorList');
  if (errors.length) {
    errList.innerHTML = errors.map(e => `<li>${e}</li>`).join('');
    errEl.classList.add('visible');
    return false;
  }
  errEl.classList.remove('visible');
  return true;
}

// ── Run backtest ───────────────────────────────────────────────────────────
async function runBacktest() {
  if (!validatePlan()) return;
  const btn = document.getElementById('btnRun');
  btn.classList.add('running');
  btn.disabled = true;

  // Show results pane with progress
  document.getElementById('btPrerun').style.display = 'none';
  document.getElementById('btResultsWrap').style.display = '';
  document.getElementById('btProgress').classList.add('visible');
  document.getElementById('resultTabsWrap').style.display = 'none';
  document.getElementById('resultPanels').style.display = 'none';
  document.getElementById('considerations').style.display = 'none';
  setProgress(10, 'Validating plan…');

  try {
    setProgress(30, 'Fetching NAV & index data…');
    const plan = buildPlan();
    const resp = await fetch('/portfolio/backtester/v2/run/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify(plan),
    });
    setProgress(70, 'Running simulation…');
    const data = await resp.json();
    setProgress(90, 'Computing analytics…');

    if (data.error) throw new Error(data.error);

    setProgress(100, 'Done!');
    setTimeout(() => {
      document.getElementById('btProgress').classList.remove('visible');
      renderResults(data);
    }, 400);

  } catch (e) {
    document.getElementById('btProgress').classList.remove('visible');
    showError(e.message);
  } finally {
    btn.classList.remove('running');
    btn.disabled = false;
  }
}

function setProgress(pct, label) {
  document.getElementById('progressBar').style.width = pct + '%';
  document.getElementById('progressLabel').textContent = label;
}

function showError(msg) {
  const errEl = document.getElementById('validationErrors');
  const errList = document.getElementById('errorList');
  errList.innerHTML = `<li>${msg}</li>`;
  errEl.classList.add('visible');
  document.getElementById('btResultsWrap').style.display = 'none';
  document.getElementById('btPrerun').style.display = '';
}


// ── Render results ──────────────────────────────────────────────────────────
function renderResults(data) {
  latestResult = data;
  allTransactions = data.transactions || [];

  // Warnings
  const warnEl = document.getElementById('dataWarnings');
  if (data.data_warnings?.length) {
    warnEl.innerHTML = '⚠️ ' + data.data_warnings.join('<br>⚠️ ');
    warnEl.classList.add('visible');
  } else {
    warnEl.classList.remove('visible');
  }

  // Show tabs + panels
  document.getElementById('resultTabsWrap').style.display = '';
  document.getElementById('resultPanels').style.display = '';
  document.getElementById('considerations').style.display = '';
  switchTab('summary');

  // ── Summary meta ──────────────────────────────────────────────────────
  document.getElementById('summaryMeta').innerHTML = `
    <span>📅 ${data.start_date} → ${data.end_date}</span>
    <span>|</span>
    <span>${data.plan_summary?.length || 0} asset(s)</span>`;

  // ── Metrics grid ──────────────────────────────────────────────────────
  const gainPositive = (data.absolute_gain || 0) >= 0;
  const xirrPositive = (data.xirr || 0) >= 0;

  document.getElementById('metricsGrid').innerHTML = `
    ${metricCard('Total Invested', fmt(data.total_invested), '', 'Total capital deployed')}
    ${metricCard('Final Value', fmt(data.final_value), 'accent', 'Market value on end date')}
    ${metricCard('Absolute Gain', (gainPositive?'+':'')+fmt(data.absolute_gain), gainPositive?'positive':'negative', 'Final value − invested')}
    ${metricCard('XIRR', fmtPct(data.xirr), xirrPositive?'positive':'negative', 'Annualised IRR on actual cashflows')}
    ${metricCard('CAGR', fmtPct(data.cagr), (data.cagr||0)>=0?'positive':'negative', 'Compound annual growth rate')}
    ${data.benchmark_cagr != null ? metricCard('Benchmark CAGR', fmtPct(data.benchmark_cagr), '', 'Benchmark buy-and-hold return') : ''}
    ${data.max_drawdown != null ? metricCard('Max Drawdown', fmtPct(data.max_drawdown,1), 'negative', 'Largest peak-to-trough fall') : ''}
    ${data.sharpe != null ? metricCard('Sharpe', (data.sharpe||0).toFixed(2), '', 'Risk-adjusted return') : ''}
    ${data.volatility != null ? metricCard('Volatility (ann.)', fmtPct(data.volatility,1), '', 'Annualised std dev of daily returns') : ''}`;

  // ── Per-asset table ────────────────────────────────────────────────────
  const tbody = document.getElementById('perAssetBody');
  tbody.innerHTML = (data.per_asset || []).map(pa => `
    <tr>
      <td>${pa.label}</td>
      <td class="mono">${fmt(pa.total_invested)}</td>
      <td class="mono accent">${fmt(pa.current_value)}</td>
      <td class="mono ${(pa.xirr||0)>=0?'pos':'neg'}">${fmtPct(pa.xirr)}</td>
      <td class="mono">${(pa.contribution_pct||0).toFixed(1)}%</td>
    </tr>`).join('');

  // ── Consistency charts ─────────────────────────────────────────────────
  renderEquityChart(data);
  renderDrawdownChart(data);
  renderAnnualChart(data);
  renderHeatmap(data);

  // ── Risk panel ────────────────────────────────────────────────────────
  // Drawdown metrics
  document.getElementById('ddMetricsGrid').innerHTML = `
    ${metricCard('Max Drawdown', fmtPct(data.max_drawdown,1), 'negative', 'Largest peak-to-trough fall')}
    ${metricCard('DD Start', data.max_dd_start||'—', '', 'When peak was set')}
    ${metricCard('DD Trough', data.max_dd_trough||'—', '', 'Lowest point date')}
    ${metricCard('DD Recovery', data.max_dd_recovery||'—', '', 'When prior peak was reclaimed')}
    ${data.max_dd_days!=null ? metricCard('Days to Trough', data.max_dd_days+'d', '', 'Peak to trough duration') : ''}
    ${data.recovery_days!=null ? metricCard('Recovery Days', data.recovery_days+'d', '', 'Trough to recovery duration') : ''}`;

  // Volatility & tail risk
  document.getElementById('riskMetricsGrid').innerHTML = `
    ${data.volatility!=null ? metricCard('Volatility', fmtPct(data.volatility,1), '', 'Annualised std dev') : ''}
    ${data.downside_deviation!=null ? metricCard('Downside Dev.', fmtPct(data.downside_deviation,1), '', 'Std dev of losing days') : ''}
    ${data.worst_month!=null ? metricCard('Worst Month', fmtPct(data.worst_month,2), 'negative', 'Worst 1-month return') : ''}
    ${data.worst_quarter!=null ? metricCard('Worst Quarter', fmtPct(data.worst_quarter,2), 'negative', 'Worst 3-month return') : ''}
    ${data.var_95!=null ? metricCard('VaR (95%)', fmtPct(data.var_95,3), 'negative', '5th-percentile daily loss') : ''}
    ${data.cvar_95!=null ? metricCard('CVaR (95%)', fmtPct(data.cvar_95,3), 'negative', 'Avg of days worse than VaR') : ''}`;

  // Risk ratios
  document.getElementById('ratioMetricsGrid').innerHTML = `
    ${data.sharpe!=null ? metricCard('Sharpe', (data.sharpe||0).toFixed(2), (data.sharpe||0)>=1?'positive':'', '(XIRR−rf) ÷ volatility') : ''}
    ${data.sortino!=null ? metricCard('Sortino', (data.sortino||0).toFixed(2), (data.sortino||0)>=1?'positive':'', '(XIRR−rf) ÷ downside dev') : ''}
    ${data.calmar!=null ? metricCard('Calmar', (data.calmar||0).toFixed(2), (data.calmar||0)>=0.5?'positive':'', 'CAGR ÷ |Max DD|') : ''}
    ${data.romad!=null ? metricCard('ROMAD', (data.romad||0).toFixed(2), (data.romad||0)>=0.5?'positive':'', 'XIRR ÷ |Max DD|') : ''}`;

  // Rolling returns box plot
  renderRollingChart(data);

  // ── Attribution panel ─────────────────────────────────────────────────
  const attrBody = document.getElementById('attributionBody');
  const attrData = data.rule_attribution || [];
  attrBody.innerHTML = attrData.length
    ? attrData.map(r => `<tr>
        <td><span class="rule-type-badge ${r.rule_type.toLowerCase()}">${r.rule_type}</span></td>
        <td>${r.asset_id}</td>
        <td class="mono">${r.fire_count}</td>
        <td class="mono">${fmt(r.total_invested)}</td>
        <td class="mono">${fmt(r.total_redeemed)}</td>
      </tr>`).join('')
    : '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px">No attribution data.</td></tr>';

  // Fund contribution chart
  renderContributionChart(data);

  // Trigger event timeline (Phase 3)
  const tlSection = document.getElementById('triggerTimelineSection');
  if (tlSection) tlSection.style.display = 'none'; // reset before render
  renderTriggerTimeline(data);

  // ── Phase 4: Adjusted Returns tab ─────────────────────────────────────
  const adjTab = document.getElementById('tab-adjusted');
  const showAdj = data.tax_enabled || data.inflation_enabled;
  if (adjTab) adjTab.style.display = showAdj ? '' : 'none';
  if (showAdj) renderAdjustedTab(data);

  // ── Phase 5: Monte Carlo tab ─────────────────────────────────────────
  const mcTab = document.getElementById('tab-montecarlo');
  if (mcTab) mcTab.style.display = data.mc_enabled ? '' : 'none';
  if (data.mc_enabled) renderMCTab(data);
}

function metricCard(label, value, cls, tooltip) {
  return `<div class="metric-card">
    <div class="metric-label">${label}</div>
    <div class="metric-value ${cls||''}">${value}</div>
    <div class="metric-sub">${tooltip}</div>
  </div>`;
}

// ── Phase 4: Adjusted Returns tab renderer ───────────────────────────────────
function renderAdjustedTab(data) {
  const taxSection = document.getElementById('adjTaxSection');
  const inflSection = document.getElementById('adjInflationSection');

  if (data.tax_enabled && taxSection) {
    taxSection.style.display = '';
    document.getElementById('adjTaxGrid').innerHTML = `
      ${metricCard('Pre-Tax XIRR', fmtPct(data.xirr), (data.xirr||0)>=0?'positive':'negative', 'Standard XIRR on all cashflows')}
      ${metricCard('Post-Tax XIRR', fmtPct(data.post_tax_xirr), (data.post_tax_xirr||0)>=0?'positive':'negative', 'XIRR after deducting STCG + LTCG on redemptions')}
      ${metricCard('Tax Drag', data.tax_drag != null ? (data.tax_drag > 0 ? '-' : '+') + Math.abs(data.tax_drag).toFixed(2) + ' pp' : '—', (data.tax_drag||0) > 0 ? 'negative' : '', 'Percentage points lost to tax')}
      ${metricCard('STCG Tax Paid', fmt(data.stcg_paid), 'negative', 'Short-term capital gains tax (< 1 year)')}
      ${metricCard('LTCG Tax Paid', fmt(data.ltcg_paid), 'negative', 'Long-term capital gains (≥ 1 year, after ₹1.25L exemption)')}
      ${metricCard('Total Tax Paid', fmt((data.stcg_paid||0) + (data.ltcg_paid||0)), 'negative', 'STCG + LTCG combined')}
    `;
  } else if (taxSection) {
    taxSection.style.display = 'none';
  }

  if (data.inflation_enabled && inflSection) {
    inflSection.style.display = '';
    document.getElementById('adjInflGrid').innerHTML = `
      ${metricCard('Nominal XIRR', fmtPct(data.xirr), (data.xirr||0)>=0?'positive':'negative', 'Standard XIRR before inflation')}
      ${metricCard('Inflation Rate', fmtPct(data.inflation_rate_used), '', 'Annual CPI rate used for adjustment')}
      ${metricCard('Real XIRR', fmtPct(data.real_xirr), (data.real_xirr||0)>=0?'positive':'negative', 'Purchasing-power adjusted return')}
      ${data.real_final_value != null ? metricCard('Real Final Value', fmt(data.real_final_value), 'accent', "Final corpus in today's rupees") : ''}
    `;
  } else if (inflSection) {
    inflSection.style.display = 'none';
  }
}

// ── Phase 5: Monte Carlo fan chart renderer ───────────────────────────────
function renderMCTab(data) {
  if (!data.mc_dates?.length) return;

  const lbl = document.getElementById('mcSimsLabel');
  if (lbl) lbl.textContent = `${data.mc_simulations_run} simulations · ${data.mc_dates.length - 1} months forward`;

  document.getElementById('mcStatsGrid').innerHTML = `
    ${metricCard('Pessimistic (P10)', fmt(data.mc_final_p10), 'negative', '10th percentile — poor scenario')}
    ${metricCard('Median (P50)', fmt(data.mc_final_p50), '', 'Most likely outcome')}
    ${metricCard('Optimistic (P90)', fmt(data.mc_final_p90), 'positive', '90th percentile — strong scenario')}
    ${data.mc_prob_double != null ? metricCard('Prob. of Doubling', data.mc_prob_double.toFixed(1) + '%', (data.mc_prob_double||0)>50?'positive':'', '% sims where final ≥ 2× invested') : ''}
    ${data.mc_prob_loss != null ? metricCard('Prob. of Loss', data.mc_prob_loss.toFixed(1) + '%', (data.mc_prob_loss||0)>20?'negative':'', '% sims ending below invested') : ''}
  `;

  const traces = [
    { x: [...data.mc_dates, ...data.mc_dates.slice().reverse()],
      y: [...data.mc_p10, ...data.mc_p90.slice().reverse()],
      fill: 'toself', fillcolor: 'rgba(99,102,241,0.07)',
      line: { color: 'transparent' }, type: 'scatter', showlegend: false, hoverinfo: 'skip' },
    { x: [...data.mc_dates, ...data.mc_dates.slice().reverse()],
      y: [...data.mc_p25, ...data.mc_p75.slice().reverse()],
      fill: 'toself', fillcolor: 'rgba(99,102,241,0.14)',
      line: { color: 'transparent' }, type: 'scatter', showlegend: false, hoverinfo: 'skip' },
    { x: data.mc_dates, y: data.mc_p50, name: 'Median (P50)',
      type: 'scatter', mode: 'lines', line: { color: '#6366f1', width: 2.5 },
      hovertemplate: '%{x}: ₹%{y:,.0f}<extra>Median</extra>' },
    { x: data.mc_dates, y: data.mc_p10, name: 'Pessimistic (P10)',
      type: 'scatter', mode: 'lines', line: { color: '#f87171', width: 1.2, dash: 'dot' },
      hovertemplate: '%{x}: ₹%{y:,.0f}<extra>P10</extra>' },
    { x: data.mc_dates, y: data.mc_p90, name: 'Optimistic (P90)',
      type: 'scatter', mode: 'lines', line: { color: '#34d399', width: 1.2, dash: 'dot' },
      hovertemplate: '%{x}: ₹%{y:,.0f}<extra>P90</extra>' },
  ];

  Plotly.newPlot('mcFanChart', traces, {
    ...PLOTLY_LAYOUT_BASE,
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, tickprefix: '₹', tickformat: ',.0f' },
    legend: { orientation: 'h', y: -0.15, font: { size: 10 } },
  }, PLOTLY_CONFIG);
}

function fmt(v) {
  if (v == null || isNaN(v)) return '—';
  return '₹' + Math.abs(v).toLocaleString('en-IN', {maximumFractionDigits:0});
}
function fmtPct(v, dec=2) {
  if (v == null || isNaN(v)) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(dec) + '%';
}

// ── Charts (Plotly) ────────────────────────────────────────────────────────
const PLOTLY_LAYOUT_BASE = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { family: 'Inter, sans-serif', color: '#94a3b8', size: 11 },
  margin: { t: 8, r: 12, b: 32, l: 60 },
  xaxis: { gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.1)', tickfont: {size:10} },
  yaxis: { gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.1)', tickfont: {size:10} },
  legend: { bgcolor: 'transparent', font: {size:10} },
  hovermode: 'x unified',
};
const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

// ── State for PE overlay ──────────────────────────────────────────────────
let _peChartData = null;   // last backtest data (has pe_chart_series)

function renderEquityChart(data) {
  _peChartData = data;

  // Show PE overlay toggle if we have PE data
  const hasPE = data.pe_chart_series && data.pe_chart_series.some(v => v != null);
  const toggleLabel = document.getElementById('peOverlayToggleLabel');
  if (toggleLabel) {
    toggleLabel.style.display = hasPE ? 'flex' : 'none';
    const idxSpan = document.getElementById('peOverlayIndex');
    if (idxSpan) idxSpan.textContent = data.pe_index_name || 'NIFTY 50';
  }

  _drawEquityChart(data, document.getElementById('peOverlayToggle')?.checked || false);
}

function togglePEOverlay() {
  if (_peChartData) _drawEquityChart(_peChartData, document.getElementById('peOverlayToggle').checked);
}

function _drawEquityChart(data, showPE) {
  const traces = [{
    x: data.dates, y: data.portfolio_values,
    name: 'Portfolio Value', type: 'scatter', mode: 'lines',
    line: { color: '#6366f1', width: 2 },
    fill: 'tozeroy', fillcolor: 'rgba(99,102,241,0.06)',
    yaxis: 'y',
  }, {
    x: data.dates, y: data.invested_cumulative,
    name: 'Invested', type: 'scatter', mode: 'lines',
    line: { color: '#94a3b8', width: 1, dash: 'dot' },
    yaxis: 'y',
  }];

  if (data.benchmark_values?.length) {
    traces.push({
      x: data.dates, y: data.benchmark_values,
      name: 'Benchmark', type: 'scatter', mode: 'lines',
      line: { color: '#34d399', width: 1.5, dash: 'dash' },
      yaxis: 'y',
    });
  }

  const markers = (data.event_markers || []).map(m => ({
    x: [m.date], y: [0],
    type: 'scatter', mode: 'markers',
    marker: { symbol: 'triangle-up', size: 8, color: '#fbbf24' },
    name: m.label, showlegend: false,
    hovertemplate: `${m.label}<extra></extra>`,
    yaxis: 'y',
  }));

  // PE overlay shapes and line
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, tickprefix: '₹', tickformat: ',.0f' },
    shapes: [],
  };

  if (showPE && data.pe_chart_series?.length && data.dates?.length) {
    // PE band zones as background shapes (on y2)
    // Use percentile-based y-range for PE bands
    const peBands = [
      { min: 0,  max: 15, color: 'rgba(52,211,153,0.06)',  label: 'Cheap (<15)' },
      { min: 15, max: 20, color: 'rgba(96,165,250,0.06)',  label: 'Fair (15–20)' },
      { min: 20, max: 25, color: 'rgba(251,191,36,0.06)',  label: 'High (20–25)' },
      { min: 25, max: 50, color: 'rgba(248,113,113,0.06)', label: 'Expensive (>25)' },
    ];
    peBands.forEach(b => {
      layout.shapes.push({
        type: 'rect',
        xref: 'paper', yref: 'y2',
        x0: 0, x1: 1,
        y0: b.min, y1: b.max,
        fillcolor: b.color,
        line: { width: 0 },
        layer: 'below',
      });
    });

    // PE line on secondary y-axis
    traces.push({
      x: data.dates,
      y: data.pe_chart_series,
      name: (data.pe_index_name || 'NIFTY 50') + ' PE',
      type: 'scatter', mode: 'lines',
      line: { color: 'rgba(244,114,182,0.7)', width: 1.5, dash: 'dot' },
      yaxis: 'y2',
      hovertemplate: 'PE: %{y:.1f}<extra></extra>',
    });

    // PE threshold lines (15, 20, 25)
    [15, 20, 25].forEach(level => {
      layout.shapes.push({
        type: 'line',
        xref: 'paper', yref: 'y2',
        x0: 0, x1: 1,
        y0: level, y1: level,
        line: { color: 'rgba(148,163,184,0.3)', width: 1, dash: 'dot' },
        layer: 'below',
      });
    });

    layout.yaxis2 = {
      title: 'PE Ratio',
      overlaying: 'y',
      side: 'right',
      showgrid: false,
      zeroline: false,
      tickfont: { color: 'rgba(244,114,182,0.7)', size: 9 },
      titlefont: { color: 'rgba(244,114,182,0.7)', size: 10 },
      range: [0, 45],
    };
  }

  Plotly.newPlot('equityChart', [...traces, ...markers], layout, PLOTLY_CONFIG);
}


function renderDrawdownChart(data) {
  Plotly.newPlot('drawdownChart', [{
    x: data.dates, y: data.drawdown_series,
    name: 'Drawdown', type: 'scatter', mode: 'lines',
    line: { color: '#f87171', width: 1.5 },
    fill: 'tozeroy', fillcolor: 'rgba(248,113,113,0.1)',
  }], {
    ...PLOTLY_LAYOUT_BASE,
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, ticksuffix: '%' },
    margin: { ...PLOTLY_LAYOUT_BASE.margin, t: 4 },
  }, PLOTLY_CONFIG);
}

function renderAnnualChart(data) {
  const calRet = data.calendar_returns || {};
  const years = Object.keys(calRet).sort();
  const vals = years.map(y => calRet[y]);
  const colors = vals.map(v => v >= 0 ? 'rgba(52,211,153,0.8)' : 'rgba(248,113,113,0.8)');

  Plotly.newPlot('annualChart', [{
    x: years, y: vals,
    type: 'bar', marker: { color: colors },
    name: 'Annual Return',
    hovertemplate: '%{x}: %{y:.2f}%<extra></extra>',
  }], {
    ...PLOTLY_LAYOUT_BASE,
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, ticksuffix: '%' },
    bargap: 0.3,
  }, PLOTLY_CONFIG);
}

function renderRollingChart(data) {
  const windows = [
    { label: '1Y', key: 'rolling_1y' },
    { label: '3Y', key: 'rolling_3y' },
    { label: '5Y', key: 'rolling_5y' },
    { label: '7Y', key: 'rolling_7y' },
  ].filter(w => data[w.key]?.length);

  if (!windows.length) {
    document.getElementById('rollingChart').innerHTML = '<div style="padding:16px;color:var(--text-muted);font-size:12px">Not enough data for rolling return analysis (need at least 1 year of history).</div>';
    return;
  }

  const traces = windows.map(w => ({
    y: data[w.key],
    name: w.label,
    type: 'box',
    boxpoints: false,
    marker: { color: w.label === '1Y' ? '#6366f1' : w.label === '3Y' ? '#34d399' : w.label === '5Y' ? '#fbbf24' : '#f472b6' },
    line: { color: w.label === '1Y' ? '#6366f1' : w.label === '3Y' ? '#34d399' : w.label === '5Y' ? '#fbbf24' : '#f472b6' },
  }));

  Plotly.newPlot('rollingChart', traces, {
    ...PLOTLY_LAYOUT_BASE,
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, ticksuffix: '%', title: 'CAGR %' },
    xaxis: { ...PLOTLY_LAYOUT_BASE.xaxis, title: 'Rolling Window' },
    showlegend: false,
    margin: { ...PLOTLY_LAYOUT_BASE.margin, t: 12 },
  }, PLOTLY_CONFIG);
}

function renderContributionChart(data) {
  const pa = data.per_asset || [];
  if (!pa.length) return;
  const labels = pa.map(a => a.label);
  const values = pa.map(a => a.contribution_pct || 0);
  const colors = ['#6366f1','#34d399','#fbbf24','#f472b6','#60a5fa','#fb923c'];

  Plotly.newPlot('contributionChart', [{
    type: 'bar',
    x: labels,
    y: values,
    marker: { color: colors.slice(0, labels.length) },
    hovertemplate: '%{x}: %{y:.1f}%<extra></extra>',
  }], {
    ...PLOTLY_LAYOUT_BASE,
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, ticksuffix: '%', title: '% of Portfolio Value' },
    xaxis: { ...PLOTLY_LAYOUT_BASE.xaxis },
    margin: { t: 8, r: 12, b: 80, l: 50 },
  }, PLOTLY_CONFIG);
}

// ── Trigger event timeline (Phase 3) ────────────────────────────────────────
function renderTriggerTimeline(data) {
  const markers = (data.event_markers || []).filter(m => m.type === 'trigger');
  const section = document.getElementById('triggerTimelineSection');
  if (!markers.length || !section) return;

  section.style.display = 'block';

  // Group markers by label
  const groups = {};
  markers.forEach(m => {
    const key = m.label || 'Trigger';
    (groups[key] = groups[key] || []).push(m.date);
  });

  const colors = ['#6366f1', '#34d399', '#fbbf24', '#f472b6', '#60a5fa', '#fb923c'];
  const traces = Object.entries(groups).map(([label, dates], i) => ({
    x: dates,
    y: dates.map(() => label),
    type: 'scatter',
    mode: 'markers',
    marker: { symbol: 'circle', size: 9, color: colors[i % colors.length] },
    name: label,
    hovertemplate: `${label}<br>%{x}<extra></extra>`,
  }));

  Plotly.newPlot('triggerTimeline', traces, {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 8, r: 20, b: 50, l: 180 },
    xaxis: { ...PLOTLY_LAYOUT_BASE.xaxis },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, automargin: true, showgrid: false },
    height: 200,
  }, PLOTLY_CONFIG);
}

function renderHeatmap(data) {
  const mRet = data.monthly_returns || {};
  if (!Object.keys(mRet).length) {
    document.getElementById('heatmapChart').innerHTML = '<div style="padding:20px;color:var(--text-muted);font-size:12px">Not enough data for monthly heatmap.</div>';
    return;
  }

  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const years = [...new Set(Object.keys(mRet).map(k => k.split('-')[0]))].sort();
  const z = years.map(y => months.map((_, mi) => {
    const key = `${y}-${String(mi+1).padStart(2,'0')}`;
    return mRet[key] != null ? mRet[key] : null;
  }));

  Plotly.newPlot('heatmapChart', [{
    x: months, y: years, z,
    type: 'heatmap',
    colorscale: [
      [0, 'rgba(248,113,113,0.9)'],
      [0.5, 'rgba(30,38,64,0.9)'],
      [1, 'rgba(52,211,153,0.9)'],
    ],
    zmid: 0,
    showscale: false,
    hovertemplate: '%{y} %{x}: %{z:.2f}%<extra></extra>',
    text: z.map(row => row.map(v => v != null ? v.toFixed(1)+'%' : '')),
    texttemplate: '%{text}',
    textfont: { size: 9, color: '#f1f5f9' },
  }], {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 8, r: 8, b: 40, l: 46 },
    xaxis: { ...PLOTLY_LAYOUT_BASE.xaxis, side: 'bottom' },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, autorange: 'reversed' },
  }, PLOTLY_CONFIG);
}

// ── Ledger ─────────────────────────────────────────────────────────────────
function renderLedger(transactions) {
  const tbody = document.getElementById('ledgerBody');
  tbody.innerHTML = transactions.map(tx => `
    <tr>
      <td>${tx.date}</td>
      <td>${tx.asset}</td>
      <td><span class="rule-type-badge ${tx.rule_type.toLowerCase()}">${tx.rule_type}</span></td>
      <td style="color:${tx.direction==='BUY'?'var(--emerald-400)':'var(--red-400)'}">${tx.direction}</td>
      <td class="mono">${(tx.units||0).toFixed(4)}</td>
      <td class="mono">${(tx.nav||0).toFixed(4)}</td>
      <td class="mono">${fmt(tx.amount)}</td>
      <td style="font-size:10px;color:var(--text-muted)">${tx.trigger_fired||''}</td>
    </tr>`).join('') || '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:20px">No transactions.</td></tr>';
}

function filterLedger() {
  const q = document.getElementById('ledgerFilter').value.toLowerCase();
  const typeF = document.getElementById('ledgerTypeFilter').value;
  const filtered = allTransactions.filter(tx => {
    const matchText = !q || tx.asset.toLowerCase().includes(q) || tx.rule_type.toLowerCase().includes(q);
    const matchType = !typeF || tx.rule_type === typeF;
    return matchText && matchType;
  });
  renderLedger(filtered);
}

function exportLedgerCSV() {
  const headers = ['Date','Asset','Type','Direction','Units','NAV','Amount','Trigger'];
  const rows = allTransactions.map(tx =>
    [tx.date, tx.asset, tx.rule_type, tx.direction, tx.units, tx.nav, tx.amount, tx.trigger_fired||'']
  );
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'backtest_ledger.csv';
  a.click();
}

// ── Tabs ──────────────────────────────────────────────────────────────────
function switchTab(tabName) {
  document.querySelectorAll('.result-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === tabName));
  document.querySelectorAll('.result-panel').forEach(p =>
    p.classList.toggle('active', p.id === `panel-${tabName}`));
  if (tabName === 'ledger' && allTransactions.length) {
    renderLedger(allTransactions);
  }
  // Resize Plotly charts on tab switch
  if (tabName === 'consistency') {
    setTimeout(() => {
      ['equityChart','drawdownChart','annualChart','heatmapChart'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.data) Plotly.relayout(id, {});
      });
    }, 50);
  }
  if (tabName === 'risk') {
    setTimeout(() => {
      const el = document.getElementById('rollingChart');
      if (el && el.data) Plotly.relayout('rollingChart', {});
    }, 50);
  }
  if (tabName === 'attribution') {
    setTimeout(() => {
      const el = document.getElementById('contributionChart');
      if (el && el.data) Plotly.relayout('contributionChart', {});
    }, 50);
  }
}

// ── Considerations toggle ──────────────────────────────────────────────────
function toggleConsiderations() {
  const body = document.getElementById('considerationsBody');
  const chev = document.getElementById('considerationsChevron');
  body.classList.toggle('open');
  chev.textContent = body.classList.contains('open') ? '▲' : '▼';
}

// ── Trigger Modal ─────────────────────────────────────────────────────────
function openTriggerModal(assetIdx, ruleIdx) {
  editingTrigger = { assetIdx, ruleIdx };
  const existing = assets[assetIdx].rules[ruleIdx].trigger;
  triggerConditions = existing?.conditions
    ? JSON.parse(JSON.stringify(existing.conditions))
    : [{ signal_type: 'drawdown_ath', params: { reference_id: assets[assetIdx].source_id }, operator: 'gte', value: 10 }];

  if (existing?.logic) document.getElementById('triggerLogic').value = existing.logic;
  const mode = existing?.action_mode || 'every_period';
  document.querySelector(`input[name="actionMode"][value="${mode}"]`).checked = true;

  renderConditions();
  document.getElementById('triggerModal').showModal();
}

function closeTriggerModal() {
  document.getElementById('triggerModal').close();
}

function addCondition() {
  if (triggerConditions.length >= 3) return;
  triggerConditions.push({ signal_type: 'drawdown_ath', params: {}, operator: 'gte', value: 10 });
  renderConditions();
}

function removeCondition(idx) {
  triggerConditions.splice(idx, 1);
  renderConditions();
}

function renderConditions() {
  const container = document.getElementById('conditionsList');
  const addBtn = document.getElementById('btnAddCondition');
  const logicRow = document.getElementById('logicRow');

  container.innerHTML = triggerConditions.map((c, i) => `
    <div class="condition-block" id="cond-${i}">
      ${i > 0 ? `<button class="btn-remove-condition" onclick="removeCondition(${i})">✕</button>` : ''}
      <div class="settings-grid" style="margin-bottom:8px">
        <div class="field-group" style="grid-column:1/-1">
          <label>Signal Type</label>
          <select onchange="updateConditionSignal(${i},this.value)">
            ${[
              ['drawdown_ath','Drawdown from ATH'],
              ['pe_ratio','PE Ratio'],
              ['relative_val','Relative Valuation Ratio'],
              ['ma_200','200-DMA (Moving Average)'],
              ['rsi','RSI'],
              ['portfolio_drawdown','Portfolio Drawdown'],
              ['calendar_date','Calendar Date'],
              ['fixed_return','Fixed Return (always on)'],
            ].map(([v,l]) => `<option value="${v}" ${c.signal_type===v?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
      </div>
      ${renderConditionParams(c, i)}
    </div>`).join('');

  addBtn.disabled = triggerConditions.length >= 3;
  logicRow.style.display = triggerConditions.length > 1 ? '' : 'none';
}

function renderConditionParams(c, i) {
  const sig = c.signal_type;
  const op = c.operator || 'gte';
  const val = c.value ?? 10;
  const p = c.params || {};

  const opSelect = `<select onchange="updateCondParam(${i},'operator',this.value)">
    <option value="lt" ${op==='lt'?'selected':''}>< (less than)</option>
    <option value="lte" ${op==='lte'?'selected':''}>≤ (less or equal)</option>
    <option value="gt" ${op==='gt'?'selected':''}>> (greater than)</option>
    <option value="gte" ${op==='gte'?'selected':''}>≥ (greater or equal)</option>
    <option value="eq" ${op==='eq'?'selected':''}}>= (equal)</option>
  </select>`;

  if (sig === 'drawdown_ath' || sig === 'portfolio_drawdown') {
    return `<div class="settings-grid">
      ${sig === 'drawdown_ath' ? `<div class="field-group" style="grid-column:1/-1">
        <label>Reference Asset</label>
        <select onchange="updateCondParamNested(${i},'params','reference_id',this.value)">
          ${assets.map(a => `<option value="${a.source_id}" ${p.reference_id===a.source_id?'selected':''}>${a.label}</option>`).join('')}
        </select>
      </div>` : ''}
      <div class="field-group"><label>Condition</label>${opSelect}</div>
      <div class="field-group"><label>Threshold (%)</label>
        <input type="number" value="${val}" step="1" onchange="updateCondParam(${i},'value',+this.value)" /></div>
    </div>`;
  }

  if (sig === 'pe_ratio') {
    const idxName = p.index_name || 'NIFTY 50';
    return `<div class="settings-grid">
      <div class="field-group" style="grid-column:1/-1">
        <label>Index (PE-tracked)</label>
        <select onchange="updateCondParamNested(${i},'params','index_name',this.value)">
          ${ALL_INDICES.map(n => `<option ${n===idxName?'selected':''}>${n}</option>`).join('')}
        </select>
      </div>
      <div class="field-group"><label>Condition</label>${opSelect}</div>
      <div class="field-group"><label>PE Value</label>
        <input type="number" value="${val}" step="0.5" onchange="updateCondParam(${i},'value',+this.value)" /></div>
    </div>`;
  }

  if (sig === 'relative_val') {
    return `<div class="settings-grid">
      <div class="field-group">
        <label>Asset A</label>
        <select onchange="updateCondParamNested(${i},'params','asset_a',this.value)">
          ${assets.map(a => `<option value="${a.source_id}" ${p.asset_a===a.source_id?'selected':''}>${a.label}</option>`).join('')}
        </select>
      </div>
      <div class="field-group">
        <label>Asset B</label>
        <select onchange="updateCondParamNested(${i},'params','asset_b',this.value)">
          ${assets.map(a => `<option value="${a.source_id}" ${p.asset_b===a.source_id?'selected':''}>${a.label}</option>`).join('')}
        </select>
      </div>
      <div class="field-group"><label>Condition</label>${opSelect}</div>
      <div class="field-group"><label>Ratio Threshold</label>
        <input type="number" value="${val}" step="0.01" onchange="updateCondParam(${i},'value',+this.value)" /></div>
    </div>`;
  }

  if (sig === 'ma_200') {
    return `<div class="settings-grid">
      <div class="field-group" style="grid-column:1/-1">
        <label>Reference Asset</label>
        <select onchange="updateCondParamNested(${i},'params','reference_id',this.value)">
          ${assets.map(a => `<option value="${a.source_id}" ${p.reference_id===a.source_id?'selected':''}>${a.label}</option>`).join('')}
        </select>
      </div>
      <div class="field-group" style="grid-column:1/-1">
        <label>Position</label>
        <select onchange="updateCondParamNested(${i},'params','position',this.value)">
          <option value="above" ${p.position==='above'||!p.position?'selected':''}>Price above 200-DMA (bullish)</option>
          <option value="below" ${p.position==='below'?'selected':''}>Price below 200-DMA (bearish)</option>
        </select>
      </div>
    </div>`;
  }

  if (sig === 'rsi') {
    return `<div class="settings-grid">
      <div class="field-group">
        <label>Reference Asset</label>
        <select onchange="updateCondParamNested(${i},'params','reference_id',this.value)">
          ${assets.map(a => `<option value="${a.source_id}" ${p.reference_id===a.source_id?'selected':''}>${a.label}</option>`).join('')}
        </select>
      </div>
      <div class="field-group">
        <label>Period</label>
        <input type="number" value="${p.period||14}" min="2" max="50" onchange="updateCondParamNested(${i},'params','period',+this.value)" />
      </div>
      <div class="field-group"><label>Condition</label>${opSelect}</div>
      <div class="field-group"><label>RSI Value</label>
        <input type="number" value="${val}" step="1" min="0" max="100" onchange="updateCondParam(${i},'value',+this.value)" /></div>
    </div>`;
  }

  if (sig === 'calendar_date') {
    return `<div class="settings-grid">
      <div class="field-group">
        <label>Target Date</label>
        <input type="date" value="${p.target_date||''}" onchange="updateCondParamNested(${i},'params','target_date',this.value)" />
      </div>
      <div class="field-group">
        <label>Recurrence</label>
        <select onchange="updateCondParamNested(${i},'params','recur_type',this.value)">
          <option value="">One-time</option>
          <option value="annual" ${p.recur_type==='annual'?'selected':''}>Annual (same day each year)</option>
          <option value="monthly" ${p.recur_type==='monthly'?'selected':''}>Monthly (same day each month)</option>
        </select>
      </div>
    </div>`;
  }

  if (sig === 'fixed_return') {
    return `<div style="font-size:11px;color:var(--text-muted);padding:8px 0">
      This trigger always evaluates to <strong>true</strong>. Use it to model a synthetic flat-rate debt leg in Switch rules.
    </div>`;
  }

  return '';
}

function updateConditionSignal(i, sig) {
  triggerConditions[i].signal_type = sig;
  triggerConditions[i].params = {};
  triggerConditions[i].operator = 'gte';
  triggerConditions[i].value = 10;
  renderConditions();
}

function updateCondParam(i, key, val) {
  triggerConditions[i][key] = val;
}

function updateCondParamNested(i, key, subKey, val) {
  if (!triggerConditions[i][key]) triggerConditions[i][key] = {};
  triggerConditions[i][key][subKey] = val;
}

function saveTrigger() {
  const { assetIdx, ruleIdx } = editingTrigger;
  if (assetIdx === null) return;
  const actionMode = document.querySelector('input[name="actionMode"]:checked').value;
  const logic = document.getElementById('triggerLogic').value;
  assets[assetIdx].rules[ruleIdx].trigger = {
    conditions: JSON.parse(JSON.stringify(triggerConditions)),
    logic,
    action_mode: actionMode,
  };
  closeTriggerModal();
  renderAssets();
}

// ── CSRF helper ────────────────────────────────────────────────────────────
function getCsrf() {
  return document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='))?.split('=')[1] || '';
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Default simulation end = today
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('simEnd').value = today;
  // Default start = 5 years ago
  const fiveYearsAgo = new Date();
  fiveYearsAgo.setFullYear(fiveYearsAgo.getFullYear() - 5);
  document.getElementById('simStart').value = fiveYearsAgo.toISOString().split('T')[0];
  rebalanceRule = null;
  updateAddRebalanceVisibility();
  renderAssets();

  // Phase 3: Fetch live Nifty 50 PE and display in sidebar widget
  fetchLivePE();
});

// ── Live PE widget ──────────────────────────────────────────────────
async function fetchLivePE() {
  const widget = document.getElementById('livePEWidget');
  const valEl = document.getElementById('livePEValue');
  const badgeEl = document.getElementById('livePEBadge');
  if (!widget || !valEl || !badgeEl) return;

  try {
    const today = new Date().toISOString().split('T')[0];
    // Fetch last 7 days to get latest available PE
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const fromStr = sevenDaysAgo.toISOString().split('T')[0];
    const url = `/portfolio/backtester/pe-data/?index=NIFTY+50&from=${fromStr}&to=${today}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('fetch failed');
    const data = await resp.json();
    if (data.error || !data.data?.length) throw new Error(data.error || 'no data');

    // Get last non-null PE value
    const lastPE = data.data.filter(d => d.pe != null).slice(-1)[0]?.pe;
    if (lastPE == null) return;

    valEl.textContent = lastPE.toFixed(1);

    // Color-coded zone badge
    let zone, bg, color;
    if (lastPE < 15) {
      zone = 'CHEAP'; bg = 'rgba(52,211,153,0.2)'; color = '#34d399';
    } else if (lastPE < 20) {
      zone = 'FAIR'; bg = 'rgba(96,165,250,0.2)'; color = '#60a5fa';
    } else if (lastPE < 25) {
      zone = 'HIGH'; bg = 'rgba(251,191,36,0.2)'; color = '#fbbf24';
    } else {
      zone = 'EXP.'; bg = 'rgba(248,113,113,0.2)'; color = '#f87171';
    }
    badgeEl.textContent = zone;
    badgeEl.style.background = bg;
    badgeEl.style.color = color;
    widget.style.borderColor = color;
    widget.title = `Nifty 50 PE: ${lastPE.toFixed(1)} (${data.data.slice(-1)[0]?.date || 'latest'})`;
  } catch(e) {
    // Silently ignore — widget stays at —
    console.debug('[PE widget] Could not fetch live PE:', e.message);
  }
}
