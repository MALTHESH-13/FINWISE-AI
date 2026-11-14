// CashPilot - Comprehensive Frontend Application
let currentUser = null;
let currentPersona = 'salaried';
let currentProfileData = null;
let momChartInstance = null;
let forecastChartInstance = null;
let momChartType = 'bar'; // 'bar' or 'line'
let narrationViewMode = 'cleaned'; // 'cleaned' or 'raw'
let goalsChatHistory = [];
let copilotChatHistory = [];
let dipAutoMessageSent = false;

// Format INR currency
function formatINR(val) {
  if (val === undefined || val === null || isNaN(val)) return '₹0';
  const valInt = Math.round(val);
  const neg = valInt < 0 ? '-' : '';
  const s = Math.abs(valInt).toString();
  if (s.length <= 3) return neg + '₹' + s;
  const lastThree = s.substring(s.length - 3);
  let otherNumbers = s.substring(0, s.length - 3);
  const groups = [];
  while (otherNumbers.length > 2) {
    groups.unshift(otherNumbers.substring(otherNumbers.length - 2));
    otherNumbers = otherNumbers.substring(0, otherNumbers.length - 2);
  }
  if (otherNumbers.length > 0) groups.unshift(otherNumbers);
  return neg + '₹' + groups.join(',') + ',' + lastThree;
}

function escapeHtml(str) {
  if (!str) return '';
  return str.toString()
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Global authenticated fetch with 401 redirect
async function authFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (res.status === 401) {
      window.location.href = '/login.html';
      return null;
    }
    return res;
  } catch (err) {
    console.error('Fetch error:', err);
    throw err;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Check auth
  const authRes = await authFetch('/api/auth/me');
  if (!authRes || !authRes.ok) {
    window.location.href = '/login.html';
    return;
  }
  const authData = await authRes.json();
  currentUser = authData.user;
  document.getElementById('user-display-name').textContent = currentUser.name || currentUser.email;
  document.getElementById('user-avatar').textContent = (currentUser.name || currentUser.email).charAt(0).toUpperCase();

  // Setup tabs
  setupNavigationTabs();

  // Setup persona controls & onboarding
  setupPersonaControls();

  // Setup statement upload (drag & drop and file input)
  setupStatementUpload();

  // Setup dashboard controls (MoM toggle, etc.)
  setupDashboardControls();

  // Setup goals planner & chat
  setupGoalsTab();

  // Setup transactions view toggle
  setupTransactionsTab();

  // Setup limits editor
  setupBudgetTab();

  // Setup simulator
  setupSimulatorTab();

  // Setup floating copilot chat
  setupCopilotChat();

  // Setup logout
  document.getElementById('logout-btn').addEventListener('click', async () => {
    await authFetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login.html';
  });

  // Handle URL hash routing e.g. #/goals
  handleHashRoute();
  window.addEventListener('hashchange', handleHashRoute);

  // Initial load
  await loadCurrentPersonaAndData();
});

// Navigation tabs
function setupNavigationTabs() {
  const tabs = document.querySelectorAll('.nav-tab');
  const panes = document.querySelectorAll('.tab-pane');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetId = tab.getAttribute('data-tab');
      tabs.forEach(t => t.classList.remove('active'));
      panes.forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add('active');

      if (targetId === 'tab-goals') window.location.hash = '#/goals';
      else if (targetId === 'tab-dashboard') window.location.hash = '#/dashboard';

      // Refresh charts when switching to tabs
      if (targetId === 'tab-dashboard' && momChartInstance) {
        setTimeout(() => momChartInstance.resize(), 100);
      }
    });
  });
}

function switchTab(tabId) {
  const tabBtn = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
  if (tabBtn) tabBtn.click();
}

function handleHashRoute() {
  const hash = window.location.hash;
  if (hash === '#/goals' || hash === '#goals') {
    switchTab('tab-goals');
  } else if (hash === '#/transactions') {
    switchTab('tab-transactions');
  } else if (hash === '#/simulator') {
    switchTab('tab-simulator');
  }
}

// Persona & Onboarding Setup
function setupPersonaControls() {
  const btnSalaried = document.getElementById('btn-persona-salaried');
  const btnBusiness = document.getElementById('btn-persona-business');
  const btnEditProfile = document.getElementById('btn-edit-profile');

  btnSalaried.addEventListener('click', async () => {
    await switchPersona('salaried');
  });

  btnBusiness.addEventListener('click', async () => {
    await switchPersona('business');
  });

  btnEditProfile.addEventListener('click', () => {
    openProfileModal(currentPersona, currentProfileData ? currentProfileData.profile : null);
  });

  // Landing modal buttons
  document.getElementById('card-choose-salaried').querySelector('button').addEventListener('click', async () => {
    document.getElementById('persona-landing-modal').style.display = 'none';
    await switchPersona('salaried');
  });

  document.getElementById('card-choose-business').querySelector('button').addEventListener('click', async () => {
    document.getElementById('persona-landing-modal').style.display = 'none';
    await switchPersona('business');
  });

  // Setup form
  const safetyRange = document.getElementById('setup-safety-buffer');
  const safetyVal = document.getElementById('safety-buffer-val');
  safetyRange.addEventListener('input', () => {
    safetyVal.textContent = Math.round(parseFloat(safetyRange.value) * 100) + '%';
  });

  // Add revenue row button
  document.getElementById('btn-add-revenue-row').addEventListener('click', () => {
    addRevenueRow('', 0);
  });

  // Form submit
  document.getElementById('profile-setup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await handleProfileSave();
  });
}

function addRevenueRow(monthStr, amountVal) {
  const container = document.getElementById('revenue-history-rows');
  const div = document.createElement('div');
  div.className = 'revenue-row';
  div.innerHTML = `
    <input type="text" class="form-control flex-1 rev-month" placeholder="YYYY-MM (e.g. 2026-10)" value="${escapeHtml(monthStr)}">
    <input type="number" class="form-control flex-1 rev-amount" placeholder="Revenue ₹" min="0" value="${amountVal}">
    <button type="button" class="btn-remove-row" title="Remove">&times;</button>
  `;
  div.querySelector('.btn-remove-row').addEventListener('click', () => div.remove());
  container.appendChild(div);
}

function openProfileModal(persona, existingData) {
  const modal = document.getElementById('profile-setup-modal');
  const title = document.getElementById('setup-modal-title');
  const salariedFields = document.getElementById('setup-salaried-fields');
  const businessFields = document.getElementById('setup-business-fields');

  title.textContent = persona === 'salaried' ? 'Configure Salaried Profile' : 'Configure Small Business Profile';

  if (persona === 'salaried') {
    salariedFields.style.display = 'block';
    businessFields.style.display = 'none';
  } else {
    salariedFields.style.display = 'none';
    businessFields.style.display = 'block';
  }

  // Pre-fill existing data if available
  if (existingData) {
    document.getElementById('setup-name').value = existingData.name || currentUser.name || '';
    document.getElementById('setup-age').value = existingData.age || '';
    if (persona === 'salaried') {
      document.getElementById('setup-salary').value = existingData.salary || '';
      document.getElementById('setup-sec-income').value = existingData.secondary_income_amount || 0;
      document.getElementById('setup-sec-label').value = existingData.secondary_income_label || '';
      document.getElementById('setup-salary-day').value = existingData.salary_day || 1;
    } else {
      document.getElementById('setup-business-type').value = existingData.business_type || '';
      const buf = existingData.safety_buffer !== undefined ? existingData.safety_buffer : 0.15;
      document.getElementById('setup-safety-buffer').value = buf;
      document.getElementById('safety-buffer-val').textContent = Math.round(buf * 100) + '%';

      const revContainer = document.getElementById('revenue-history-rows');
      revContainer.innerHTML = '';
      const revs = existingData.revenue_history || [];
      if (revs.length > 0) {
        revs.forEach(r => addRevenueRow(r.month, r.amount));
      } else {
        addRevenueRow('2026-08', 150000);
        addRevenueRow('2026-09', 160000);
        addRevenueRow('2026-10', 170000);
      }
    }
  } else {
    document.getElementById('setup-name').value = currentUser.name || '';
  }

  modal.style.display = 'flex';
}

async function handleProfileSave() {
  const persona = currentPersona;
  const name = document.getElementById('setup-name').value.trim();
  const age = parseInt(document.getElementById('setup-age').value) || null;

  const payload = { persona, name, age };

  if (persona === 'salaried') {
    payload.salary = parseFloat(document.getElementById('setup-salary').value) || 0.0;
    payload.secondary_income_amount = parseFloat(document.getElementById('setup-sec-income').value) || 0.0;
    payload.secondary_income_label = document.getElementById('setup-sec-label').value.trim();
    payload.salary_day = parseInt(document.getElementById('setup-salary-day').value) || 1;
  } else {
    payload.business_type = document.getElementById('setup-business-type').value.trim();
    payload.safety_buffer = parseFloat(document.getElementById('setup-safety-buffer').value) || 0.15;
    
    const rows = document.querySelectorAll('#revenue-history-rows .revenue-row');
    const revs = [];
    rows.forEach(r => {
      const m = r.querySelector('.rev-month').value.trim();
      const a = parseFloat(r.querySelector('.rev-amount').value) || 0.0;
      if (m && a > 0) revs.push({ month: m, amount: a });
    });
    payload.revenue_history = revs;
  }

  const res = await authFetch('/api/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (res && res.ok) {
    document.getElementById('profile-setup-modal').style.display = 'none';
    await refreshAllDashboardPanels();
  } else {
    alert('Failed to save profile. Please check your inputs.');
  }
}

async function switchPersona(persona) {
  const res = await authFetch('/api/persona', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persona })
  });

  if (res && res.ok) {
    currentPersona = persona;
    updatePersonaHeaderUI(persona);
    dipAutoMessageSent = false;
    await checkProfileAndLoadData();
  }
}

function updatePersonaHeaderUI(persona) {
  const btnSalaried = document.getElementById('btn-persona-salaried');
  const btnBusiness = document.getElementById('btn-persona-business');
  const subTitle = document.getElementById('header-persona-subtitle');
  const chipBiz = document.getElementById('chip-biz-tips');

  if (persona === 'salaried') {
    btnSalaried.classList.add('active');
    btnBusiness.classList.remove('active');
    subTitle.textContent = 'Salaried Cashflow & Investments';
    if (chipBiz) chipBiz.style.display = 'none';
  } else {
    btnBusiness.classList.add('active');
    btnSalaried.classList.remove('active');
    subTitle.textContent = 'Small Business Cashflow & Reserve Engine';
    if (chipBiz) chipBiz.style.display = 'inline-block';
  }
}

async function loadCurrentPersonaAndData() {
  const res = await authFetch('/api/persona');
  if (!res) return;
  const data = await res.json();
  currentPersona = data.active_persona || 'salaried';
  updatePersonaHeaderUI(currentPersona);
  await checkProfileAndLoadData();
}

async function checkProfileAndLoadData() {
  const res = await authFetch('/api/profile');
  if (!res) return;
  const data = await res.json();
  currentProfileData = data;

  if (!data.is_setup) {
    // Open profile modal blocking until saved
    openProfileModal(currentPersona, data.profile);
    return;
  }

  await refreshAllDashboardPanels();
}

// Statement Ingestion (Drag-and-Drop and File Input)
function setupStatementUpload() {
  const dropzone = document.getElementById('dashboard-dropzone');
  const fileInput = document.getElementById('csv-file-input');

  ['dragenter', 'dragover'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', async (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      await uploadStatementFile(files[0]);
    }
  });

  fileInput.addEventListener('change', async () => {
    if (fileInput.files.length > 0) {
      await uploadStatementFile(fileInput.files[0]);
      fileInput.value = '';
    }
  });
}

async function uploadStatementFile(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    alert('Please upload a CSV bank statement.');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  const res = await authFetch('/api/upload', {
    method: 'POST',
    body: formData
  });

  if (res && res.ok) {
    const data = await res.json();
    let msg = `Successfully imported ${data.count} transactions!`;
    if (data.warnings && data.warnings.length > 0) {
      msg += ` (${data.warnings.length} rows skipped with warnings)`;
    }
    console.log(msg);
    // Refresh all panels immediately without reload
    await refreshAllDashboardPanels();
  } else {
    const err = await res.json();
    alert('Import failed: ' + (err.detail || 'Invalid CSV format'));
  }
}

// Refresh all dashboard components immediately without page reload
async function refreshAllDashboardPanels() {
  await Promise.all([
    loadProfileBaselineCard(),
    loadCommitments(),
    loadMoMComparison(),
    loadForecastChart(),
    loadTransactions(),
    loadBudgetLimits(),
    loadAccuracyAndAnomalies(),
    checkBusinessDip()
  ]);
}

// Baseline Stable Monthly Income Card
async function loadProfileBaselineCard() {
  const res = await authFetch('/api/profile');
  if (!res) return;
  const data = await res.json();
  currentProfileData = data;

  const titleEl = document.getElementById('baseline-income-title');
  const valEl = document.getElementById('metric-baseline-income');
  const tooltipDesc = document.getElementById('tooltip-formula-desc');

  if (data.persona === 'salaried') {
    titleEl.textContent = 'Salaried Baseline Income';
    valEl.textContent = formatINR(data.baseline_income);
    tooltipDesc.innerHTML = `
      <strong>Formula:</strong> Salary + Secondary Income<br>
      <strong>Salary:</strong> ${formatINR(data.calculation_details?.inputs?.salary || 0)}<br>
      <strong>Secondary:</strong> ${formatINR(data.calculation_details?.inputs?.secondary_income || 0)} (${escapeHtml(data.calculation_details?.inputs?.secondary_label || 'None')})<br>
      <strong>Total:</strong> ${formatINR(data.baseline_income)}
    `;
  } else {
    titleEl.textContent = 'Stable Monthly Income Baseline';
    valEl.textContent = formatINR(data.baseline_income);
    const inp = data.calculation_details?.inputs || {};
    tooltipDesc.innerHTML = `
      <strong>Formula:</strong> Rolling mean of last 3 months revenue × (1 - safety buffer)<br>
      <strong>Months Considered:</strong> ${inp.months ? inp.months.join(', ') : 'None'}<br>
      <strong>Rolling Mean:</strong> ${formatINR(inp.rolling_mean || 0)}<br>
      <strong>Safety Buffer:</strong> ${inp.safety_buffer_pct || 15}%<br>
      <strong>Baseline Result:</strong> ${formatINR(data.baseline_income)}
    `;
  }
}

// Commitments
async function loadCommitments() {
  const res = await authFetch('/api/commitments');
  if (!res) return;
  const json = await res.json();

  const emptyEl = document.getElementById('commitments-empty');
  const tableEl = document.getElementById('commitments-table');
  const tbody = tableEl.querySelector('tbody');
  const badgeTotal = document.getElementById('commitments-badge-total');
  const metricTotal = document.getElementById('metric-commitments-total');
  const metricCount = document.getElementById('metric-commitments-count');

  // Also full recurring tab
  const recEmpty = document.getElementById('recurring-empty');
  const recTable = document.getElementById('recurring-full-table');
  const recTbody = recTable.querySelector('tbody');

  if (!json.has_data || json.commitments.length === 0) {
    emptyEl.style.display = 'flex';
    tableEl.style.display = 'none';
    recEmpty.style.display = 'flex';
    recTable.style.display = 'none';
    badgeTotal.textContent = 'Total: ₹0/mo';
    metricTotal.textContent = '₹0';
    metricCount.textContent = '0 recurring obligations';
    return;
  }

  emptyEl.style.display = 'none';
  tableEl.style.display = 'table';
  recEmpty.style.display = 'none';
  recTable.style.display = 'table';

  badgeTotal.textContent = `Total: ${formatINR(json.monthly_total)}/mo`;
  metricTotal.textContent = formatINR(json.monthly_total);
  metricCount.textContent = `${json.commitments.length} detected commitments`;

  const rowsHtml = json.commitments.map(c => `
    <tr>
      <td><strong>${escapeHtml(c.name)}</strong></td>
      <td><span class="badge badge-info">${escapeHtml(c.category)}</span></td>
      <td>${formatINR(c.amount)}</td>
      <td>${escapeHtml(c.next_due_date)}</td>
      <td><strong>${c.days_left} days</strong></td>
    </tr>
  `).join('');

  tbody.innerHTML = rowsHtml;
  recTbody.innerHTML = rowsHtml;
}

// Month-over-Month Category Comparison with Chart.js
function setupDashboardControls() {
  const toggle = document.getElementById('mom-chart-type-toggle');
  const btns = toggle.querySelectorAll('.segment-btn');
  btns.forEach(b => {
    b.addEventListener('click', () => {
      btns.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      momChartType = b.getAttribute('data-chart-type');
      loadMoMComparison();
    });
  });
}

async function loadMoMComparison() {
  const res = await authFetch('/api/mom');
  if (!res) return;
  const json = await res.json();

  const emptyEl = document.getElementById('mom-chart-empty');
  const canvas = document.getElementById('mom-chart-canvas');
  const overspentBox = document.getElementById('mom-overspent-container');
  const overspentTags = document.getElementById('mom-overspent-tags');

  if (!json.has_data || json.categories.length === 0) {
    emptyEl.style.display = 'flex';
    canvas.style.display = 'none';
    overspentBox.style.display = 'none';
    if (momChartInstance) { momChartInstance.destroy(); momChartInstance = null; }
    return;
  }

  emptyEl.style.display = 'none';
  canvas.style.display = 'block';

  // Render overspent alerts
  if (json.overspent && json.overspent.length > 0) {
    overspentBox.style.display = 'flex';
    overspentTags.innerHTML = json.overspent.map(o => `
      <span class="overspent-tag">
        ⚠️ ${escapeHtml(o.category)}: Over by ${formatINR(o.over_amount)} (${o.over_pct}%)
      </span>
    `).join('');
  } else {
    overspentBox.style.display = 'none';
  }

  // Destroy previous Chart instance
  if (momChartInstance) momChartInstance.destroy();

  // Color current month bars: red if over limit, cyan if within limit
  const currentMonthColors = json.categories.map((cat, idx) => {
    const isOver = json.overspent.some(o => o.category === cat);
    return isOver ? 'rgba(239, 68, 68, 0.85)' : 'rgba(56, 189, 248, 0.85)';
  });

  const ctx = canvas.getContext('2d');
  
  if (momChartType === 'bar') {
    momChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: json.categories,
        datasets: [
          {
            label: json.previous_month_label,
            data: json.previous_month_spending,
            backgroundColor: 'rgba(100, 116, 139, 0.65)',
            borderColor: '#64748b',
            borderWidth: 1,
            borderRadius: 4
          },
          {
            label: json.current_month_label,
            data: json.current_month_spending,
            backgroundColor: currentMonthColors,
            borderColor: currentMonthColors.map(c => c.replace('0.85', '1')),
            borderWidth: 1,
            borderRadius: 4
          },
          {
            label: 'Personalized Budget Limit',
            data: json.limits,
            type: 'line',
            borderColor: '#f59e0b',
            backgroundColor: '#f59e0b',
            borderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            borderDash: [5, 5],
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#9ca3af', font: { family: 'Inter', size: 11 } }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                return `${context.dataset.label}: ${formatINR(context.raw)}`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { color: '#1f2937' },
            ticks: { color: '#9ca3af', font: { family: 'Inter', size: 10 } }
          },
          y: {
            grid: { color: '#1f2937' },
            ticks: {
              color: '#9ca3af',
              font: { family: 'Inter', size: 10 },
              callback: function(value) { return formatINR(value); }
            }
          }
        }
      }
    });
  } else {
    // Line chart view
    momChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: json.categories,
        datasets: [
          {
            label: json.previous_month_label,
            data: json.previous_month_spending,
            borderColor: '#64748b',
            backgroundColor: 'rgba(100, 116, 139, 0.1)',
            tension: 0.3,
            fill: false
          },
          {
            label: json.current_month_label,
            data: json.current_month_spending,
            borderColor: '#38bdf8',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            tension: 0.3,
            fill: false
          },
          {
            label: 'Personalized Budget Limit',
            data: json.limits,
            borderColor: '#f59e0b',
            borderDash: [5, 5],
            tension: 0,
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#9ca3af' } },
          tooltip: {
            callbacks: {
              label: function(context) {
                return `${context.dataset.label}: ${formatINR(context.raw)}`;
              }
            }
          }
        },
        scales: {
          x: { grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' } },
          y: {
            grid: { color: '#1f2937' },
            ticks: {
              color: '#9ca3af',
              callback: function(v) { return formatINR(v); }
            }
          }
        }
      }
    });
  }
}

// 30-Day Forecast Trajectory Chart
async function loadForecastChart() {
  const res = await authFetch('/api/forecast');
  if (!res) return;
  const json = await res.json();

  const emptyEl = document.getElementById('forecast-empty');
  const canvas = document.getElementById('forecast-chart-canvas');
  const minBalEl = document.getElementById('metric-min-balance');
  const shortageEl = document.getElementById('metric-shortage-prob');

  if (json.status === 'empty' || !json.data) {
    emptyEl.style.display = 'flex';
    canvas.style.display = 'none';
    minBalEl.textContent = '₹0';
    shortageEl.textContent = '0.0%';
    if (forecastChartInstance) { forecastChartInstance.destroy(); forecastChartInstance = null; }
    return;
  }

  emptyEl.style.display = 'none';
  canvas.style.display = 'block';

  const d = json.data;
  minBalEl.textContent = formatINR(d.min_balance);
  shortageEl.textContent = (d.shortage_prob * 100).toFixed(1) + '%';
  shortageEl.className = 'metric-value ' + (d.shortage_prob > 0.2 ? 'text-red' : (d.shortage_prob > 0.05 ? 'text-amber' : 'text-emerald'));

  if (forecastChartInstance) forecastChartInstance.destroy();

  const ctx = canvas.getContext('2d');
  forecastChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.dates.map(dt => dt.substring(5)),
      datasets: [
        {
          label: 'P90 (Optimistic)',
          data: d.p90,
          borderColor: 'rgba(56, 189, 248, 0.3)',
          borderWidth: 1,
          pointRadius: 0,
          fill: '+1',
          backgroundColor: 'rgba(56, 189, 248, 0.08)'
        },
        {
          label: 'P50 (Median Trajectory)',
          data: d.p50,
          borderColor: '#38bdf8',
          borderWidth: 2.5,
          pointRadius: 0,
          fill: false
        },
        {
          label: 'P10 (Conservative Floor)',
          data: d.p10,
          borderColor: 'rgba(239, 68, 68, 0.4)',
          borderWidth: 1,
          pointRadius: 0,
          fill: '-1',
          backgroundColor: 'rgba(56, 189, 248, 0.08)'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#9ca3af', font: { family: 'Inter', size: 10 } } },
        tooltip: {
          callbacks: {
            label: function(ctx) { return `${ctx.dataset.label}: ${formatINR(ctx.raw)}`; }
          }
        }
      },
      scales: {
        x: { grid: { color: '#1f2937' }, ticks: { color: '#9ca3af', maxTicksLimit: 10 } },
        y: {
          grid: { color: '#1f2937' },
          ticks: { color: '#9ca3af', callback: function(v) { return formatINR(v); } }
        }
      }
    }
  });
}

// Business Income-Dip Priority Engine
async function checkBusinessDip() {
  const banner = document.getElementById('business-dip-banner');
  if (currentPersona !== 'business') {
    banner.style.display = 'none';
    return;
  }

  const res = await authFetch('/api/dip-check');
  if (!res) return;
  const json = await res.json();

  if (json.triggered) {
    banner.style.display = 'flex';
    document.getElementById('dip-banner-title').textContent = `⚠️ Income Dip Detected: Projected Revenue ₹${Math.round(json.projected_inflow).toLocaleString()} falls short by ₹${Math.round(json.shortfall).toLocaleString()}`;
    document.getElementById('dip-banner-desc').textContent = `Baseline stable income is ${formatINR(json.baseline)}. P1 Essentials: ${formatINR(json.p1_total)} (${json.essentials_covered ? 'Covered' : 'Underfunded'}). Suggested P3 cuts to save ${formatINR(json.total_p3_savings)}.`;

    // Auto-post chatbot message in goals chat without user asking
    if (!dipAutoMessageSent && json.auto_chat_message) {
      appendChatMessage('goals', 'bot', json.auto_chat_message);
      appendChatMessage('copilot', 'bot', json.auto_chat_message);
      dipAutoMessageSent = true;
    }

    document.getElementById('btn-view-dip-details').onclick = () => {
      switchTab('tab-goals');
    };
  } else {
    banner.style.display = 'none';
  }
}

// Goals Tab & Advisor Chat
function setupGoalsTab() {
  const form = document.getElementById('goal-planner-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('goal-item-name').value.trim();
    const cost = parseFloat(document.getElementById('goal-target-cost').value);
    const months = parseInt(document.getElementById('goal-timeline-months').value);
    const current_savings = parseFloat(document.getElementById('goal-current-savings').value) || 0.0;
    const custom_return_val = document.getElementById('goal-custom-return').value;
    const annual_return = custom_return_val ? parseFloat(custom_return_val) : null;

    const res = await authFetch('/api/goals/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, cost, months, current_savings, annual_return })
    });

    if (res && res.ok) {
      const data = await res.json();
      displayGoalRoadmap(data.plan);
    }
  });

  // Chat in goals tab
  const chatForm = document.getElementById('goals-chat-form');
  const chatInput = document.getElementById('goals-chat-input');
  const chips = document.querySelectorAll('#goals-chat-chips .chip-btn');

  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.getAttribute('data-query');
      chatInput.value = q;
      sendAdvisorChatMessage(q);
    });
  });

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const msg = chatInput.value.trim();
    if (!msg) return;
    sendAdvisorChatMessage(msg);
    chatInput.value = '';
  });
}

function displayGoalRoadmap(plan) {
  const output = document.getElementById('goal-roadmap-output');
  output.style.display = 'block';

  document.getElementById('goal-feasibility-title').textContent = `Feasibility: ${plan.feasibility.toUpperCase()}`;
  document.getElementById('goal-feasibility-desc').textContent = plan.feasibility_description;
  const box = document.getElementById('goal-feasibility-box');
  if (plan.feasibility === 'feasible') box.style.borderLeftColor = '#10b981';
  else if (plan.feasibility === 'stretch') box.style.borderLeftColor = '#f59e0b';
  else box.style.borderLeftColor = '#ef4444';

  document.getElementById('goal-stat-monthly').textContent = `${formatINR(plan.required_monthly_saving)}/mo`;
  document.getElementById('goal-stat-vehicle').textContent = plan.recommended_instrument;
  document.getElementById('goal-stat-sip').textContent = `${formatINR(plan.sip_amount)}/mo (${plan.assumed_annual_rate}% p.a.)`;

  // Budget cuts
  const cutsList = document.getElementById('goal-budget-cuts-list');
  if (plan.budgeting_steps && plan.budgeting_steps.length > 0) {
    cutsList.innerHTML = plan.budgeting_steps.map(s => `
      <div class="cut-item">
        <strong>${escapeHtml(s.action)}</strong>
      </div>
    `).join('');
  } else {
    cutsList.innerHTML = '<div class="text-sm text-muted">No category trimming required; surplus fully covers the monthly deposit.</div>';
  }

  // Milestones
  const mTable = document.querySelector('#goal-milestones-table tbody');
  mTable.innerHTML = (plan.milestones || []).map(m => `
    <tr>
      <td>Month ${m.month}</td>
      <td>${formatINR(m.monthly_deposit)}</td>
      <td class="text-emerald">+${formatINR(m.projected_returns)}</td>
      <td><strong>${formatINR(m.target_balance)}</strong></td>
    </tr>
  `).join('');
}

async function sendAdvisorChatMessage(text) {
  appendChatMessage('goals', 'user', text);
  goalsChatHistory.push({ role: 'user', content: text });

  const indicator = document.getElementById('goals-typing-indicator');
  indicator.style.display = 'flex';

  try {
    const res = await authFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: goalsChatHistory })
    });
    indicator.style.display = 'none';
    if (!res) return;
    const data = await res.json();
    goalsChatHistory.push({ role: 'assistant', content: data.reply });
    appendChatMessage('goals', 'bot', data.reply);

    // If goal plan returned, also update roadmap form UI
    if (data.goal_plan) {
      displayGoalRoadmap(data.goal_plan);
    }
  } catch (err) {
    indicator.style.display = 'none';
    appendChatMessage('goals', 'bot', 'Unable to connect to advisor.');
  }
}

// Transactions View
function setupTransactionsTab() {
  const control = document.getElementById('narration-view-control');
  const btns = control.querySelectorAll('.segment-btn');
  btns.forEach(b => {
    b.addEventListener('click', () => {
      btns.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      narrationViewMode = b.getAttribute('data-view');
      loadTransactions();
    });
  });
}

async function loadTransactions() {
  const res = await authFetch('/api/transactions');
  if (!res) return;
  const json = await res.json();

  const emptyEl = document.getElementById('transactions-empty');
  const tableEl = document.getElementById('transactions-table');
  const tbody = document.getElementById('transactions-tbody');
  const thDesc = document.getElementById('th-merchant-desc');

  if (!json.has_data || json.transactions.length === 0) {
    emptyEl.style.display = 'flex';
    tableEl.style.display = 'none';
    return;
  }

  emptyEl.style.display = 'none';
  tableEl.style.display = 'table';

  thDesc.textContent = narrationViewMode === 'cleaned' ? 'Cleaned Merchant → Category' : 'Raw Narration';

  tbody.innerHTML = json.transactions.map(tx => {
    const isCredit = tx.type === 'credit';
    const amtClass = isCredit ? 'text-emerald' : 'text-main';
    const typeBadge = isCredit ? '<span class="badge badge-success">Credit</span>' : '<span class="badge" style="background:#334155;">Debit</span>';

    const descCell = narrationViewMode === 'cleaned' ? `
      <div>
        <div style="font-weight:600; color:#f8fafc;">${escapeHtml(tx.cleaned_merchant)}</div>
        <div style="font-size:0.75rem; color:#94a3b8;">${escapeHtml(tx.category)}</div>
      </div>
    ` : `<span style="font-family:monospace; font-size:0.78rem;">${escapeHtml(tx.raw_description)}</span>`;

    return `
      <tr>
        <td style="white-space:nowrap;">${escapeHtml(tx.date)}</td>
        <td>${descCell}</td>
        <td>${typeBadge}</td>
        <td class="text-right ${amtClass}" style="font-weight:600;">${isCredit ? '+' : '-'}${formatINR(tx.amount)}</td>
      </tr>
    `;
  }).join('');
}

// Budget & Limits Tab
function setupBudgetTab() {
  document.getElementById('btn-save-limits').addEventListener('click', async () => {
    const inputs = document.querySelectorAll('#limits-editor-grid input');
    const newLimits = {};
    inputs.forEach(inp => {
      const cat = inp.getAttribute('data-cat');
      const val = parseFloat(inp.value) || 0;
      newLimits[cat] = val;
    });

    const res = await authFetch('/api/limits', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limits: newLimits })
    });

    if (res && res.ok) {
      alert('Budget limits saved successfully!');
      await loadMoMComparison();
    }
  });
}

async function loadBudgetLimits() {
  const res = await authFetch('/api/limits');
  if (!res) return;
  const json = await res.json();
  const limits = json.limits || {};

  const grid = document.getElementById('limits-editor-grid');
  grid.innerHTML = Object.entries(limits).map(([cat, val]) => `
    <div class="limit-item">
      <label>${escapeHtml(cat)}</label>
      <input type="number" class="form-control" data-cat="${escapeHtml(cat)}" value="${val}" min="0">
    </div>
  `).join('');
}

// Accuracy & Anomalies
async function loadAccuracyAndAnomalies() {
  const btRes = await authFetch('/api/backtest');
  if (btRes && btRes.ok) {
    const json = await btRes.json();
    const bt = json.backtest;
    document.getElementById('acc-accuracy-rate').textContent = bt.accuracy_rate + '%';
    document.getElementById('acc-mape').textContent = bt.mape + '%';
    document.getElementById('acc-interval').textContent = bt.in_confidence_interval_pct + '%';
  }

  const anomRes = await authFetch('/api/anomaly');
  if (anomRes && anomRes.ok) {
    const json = await anomRes.json();
    const anomalies = json.anomalies || [];
    const emptyEl = document.getElementById('anomalies-empty');
    const tableEl = document.getElementById('anomalies-table');
    const tbody = tableEl.querySelector('tbody');

    if (anomalies.length === 0) {
      emptyEl.style.display = 'flex';
      tableEl.style.display = 'none';
      return;
    }

    emptyEl.style.display = 'none';
    tableEl.style.display = 'table';
    tbody.innerHTML = anomalies.map(a => `
      <tr>
        <td>${escapeHtml(a.date)}</td>
        <td><strong>${escapeHtml(a.merchant)}</strong></td>
        <td><span class="badge badge-info">${escapeHtml(a.category)}</span></td>
        <td class="text-red font-bold">${formatINR(a.amount)}</td>
        <td>${formatINR(a.threshold)}</td>
        <td><span class="badge ${a.severity === 'High' ? 'badge-danger' : 'badge-warning'}">${a.severity}</span></td>
      </tr>
    `).join('');
  }
}

// Simulator Tab
function setupSimulatorTab() {
  const simType = document.getElementById('sim-type');
  const rateGroup = document.getElementById('interest-rate-group');
  const form = document.getElementById('simulator-form');

  simType.addEventListener('change', () => {
    rateGroup.style.display = simType.value === 'prepay_loan' ? 'block' : 'none';
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const type = simType.value;
    const amount = parseFloat(document.getElementById('sim-amount').value);
    const date = document.getElementById('sim-date').value;
    const interest_rate = parseFloat(document.getElementById('sim-interest-rate').value) || 9.0;

    const res = await authFetch('/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, amount, date, interest_rate })
    });

    if (res && res.ok) {
      const json = await res.json();
      displaySimulatorResult(json.simulation, { type, amount, date, interest_rate });
    } else {
      const err = await res.json();
      alert(err.detail || 'Simulation failed.');
    }
  });
}

function displaySimulatorResult(sim, sc) {
  const resultsArea = document.getElementById('sim-results-area');
  resultsArea.style.display = 'block';

  document.getElementById('sim-verdict-title').textContent = 'Verdict: ' + sim.verdict;
  document.getElementById('sim-verdict-desc').textContent = `Simulated ${sc.type.replace('_', ' ')} of ${formatINR(sc.amount)} on ${sc.date}.`;

  const banner = document.getElementById('sim-verdict-banner');
  if (sim.shortage_prob_after <= 0.05 && !sim.first_at_risk_bill) banner.style.borderLeftColor = '#10b981';
  else if (sim.shortage_prob_after > 0.20 || sim.first_at_risk_bill) banner.style.borderLeftColor = '#ef4444';
  else banner.style.borderLeftColor = '#f59e0b';

  // Prepay Card
  const prepayCard = document.getElementById('prepay-summary-card');
  if (sim.prepay_details) {
    prepayCard.style.display = 'block';
    const pp = sim.prepay_details;
    document.getElementById('prepay-cash-dip').textContent = formatINR(pp.cash_dip);
    document.getElementById('prepay-interest-saved').textContent = formatINR(pp.interest_saved);
    document.getElementById('prepay-tenure-reduced').textContent = `${pp.tenure_reduced_months} months reduction`;
    document.getElementById('prepay-assumed-rate').textContent = `${pp.assumed_rate}% p.a.`;
  } else {
    prepayCard.style.display = 'none';
  }

  // Min balances
  document.getElementById('sim-min-before').textContent = formatINR(sim.min_balance_before);
  document.getElementById('sim-min-after').textContent = formatINR(sim.min_balance_after);
  document.getElementById('sim-prob-before').textContent = (sim.shortage_prob_before * 100).toFixed(1) + '%';
  document.getElementById('sim-prob-after').textContent = (sim.shortage_prob_after * 100).toFixed(1) + '%';

  // Obligations
  const tbody = document.querySelector('#sim-obligations-table tbody');
  tbody.innerHTML = (sim.obligations || []).map(ob => {
    let badgeClass = 'badge-success';
    if (ob.status === 'At risk') badgeClass = 'badge-warning';
    else if (ob.status === 'Will likely miss') badgeClass = 'badge-danger';
    return `
      <tr>
        <td><strong>${escapeHtml(ob.name)}</strong></td>
        <td>${escapeHtml(ob.due_date)}</td>
        <td>${formatINR(ob.amount)}</td>
        <td>${(ob.prob_before * 100).toFixed(0)}%</td>
        <td><strong>${(ob.prob_after * 100).toFixed(0)}%</strong></td>
        <td><span class="badge ${badgeClass}">${escapeHtml(ob.status)}</span></td>
      </tr>
    `;
  }).join('');
}

// Floating Copilot Chat
function setupCopilotChat() {
  const triggerBtn = document.getElementById('chat-trigger-btn');
  const chatWindow = document.getElementById('chat-window');
  const closeBtn = document.getElementById('chat-close-btn');
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const openIcon = triggerBtn.querySelector('.chat-icon-open');
  const closeIcon = triggerBtn.querySelector('.chat-icon-close');
  const chips = document.querySelectorAll('#chat-chips .chip-btn');

  function toggle(show) {
    const isVis = show !== undefined ? show : (chatWindow.style.display !== 'none');
    if (isVis) {
      chatWindow.style.display = 'none';
      openIcon.style.display = 'block';
      closeIcon.style.display = 'none';
    } else {
      chatWindow.style.display = 'flex';
      openIcon.style.display = 'none';
      closeIcon.style.display = 'block';
      input.focus();
    }
  }

  triggerBtn.addEventListener('click', () => toggle());
  closeBtn.addEventListener('click', () => toggle(true));

  chips.forEach(c => {
    c.addEventListener('click', () => {
      const q = c.getAttribute('data-query');
      input.value = q;
      sendCopilotMessage(q);
    });
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;
    sendCopilotMessage(msg);
    input.value = '';
  });
}

async function sendCopilotMessage(text) {
  appendChatMessage('copilot', 'user', text);
  copilotChatHistory.push({ role: 'user', content: text });

  const indicator = document.getElementById('typing-indicator');
  indicator.style.display = 'flex';

  try {
    const res = await authFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: copilotChatHistory })
    });
    indicator.style.display = 'none';
    if (!res) return;
    const data = await res.json();
    copilotChatHistory.push({ role: 'assistant', content: data.reply });
    appendChatMessage('copilot', 'bot', data.reply);
  } catch (err) {
    indicator.style.display = 'none';
    appendChatMessage('copilot', 'bot', 'Unable to reach Copilot.');
  }
}

function appendChatMessage(target, sender, text) {
  const containerId = target === 'goals' ? 'goals-chat-messages' : 'chat-messages';
  const container = document.getElementById(containerId);
  if (!container) return;

  const div = document.createElement('div');
  div.className = `chat-msg ${sender}-msg`;
  div.innerHTML = `<div class="msg-bubble">${escapeHtml(text).replace(/\n/g, '<br>')}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}
