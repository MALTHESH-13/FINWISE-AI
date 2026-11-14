// CashPilot - Comprehensive Frontend Application
let currentUser = null;
let currentPersona = 'salaried';
let currentProfileData = null;
let momChartInstance = null;
let momChartType = 'bar'; // 'bar' or 'line'
let narrationViewMode = 'cleaned'; // 'cleaned' or 'raw'
let goalsChatHistory = [];
let copilotChatHistory = [];
let dipAutoMessageSent = false;

// Calendar navigation state
let currentCalYear = 2026;
let currentCalMonth = 11; // 1-indexed (11 = Nov)
let calendarCache = null;

// Category colors for chips and dots (100% light mode)
const CATEGORY_COLORS = {
  'Food': { bg: '#FEF3C7', text: '#92400E' },
  'Groceries': { bg: '#ECFCCB', text: '#3F6212' },
  'Shopping': { bg: '#FCE7F3', text: '#9D174D' },
  'Housing': { bg: '#E0E7FF', text: '#3730A3' },
  'Subscriptions': { bg: '#EDE9FE', text: '#5B21B6' },
  'Utilities': { bg: '#CCFBF1', text: '#115E59' },
  'Phone/Data': { bg: '#E0F2FE', text: '#075985' },
  'Transport': { bg: '#FFEDD5', text: '#9A3412' },
  'Health/Fitness': { bg: '#DCFCE7', text: '#166534' },
  'Insurance': { bg: '#F1F5F9', text: '#334155' },
  'Loan/EMI': { bg: '#FEE2E2', text: '#991B1B' },
  'Entertainment': { bg: '#FAE8FF', text: '#86198F' },
  'Income': { bg: '#D1FAE5', text: '#065F46' },
  'Savings': { bg: '#EDE9FE', text: '#4338CA' },
  'Other': { bg: '#F3F4F6', text: '#374151' }
};

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

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

// Initialize light mode Chart.js defaults
if (window.Chart) {
  Chart.defaults.color = '#374151';
  Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  if (Chart.defaults.plugins && Chart.defaults.plugins.tooltip) {
    Chart.defaults.plugins.tooltip.backgroundColor = '#FFFFFF';
    Chart.defaults.plugins.tooltip.titleColor = '#111827';
    Chart.defaults.plugins.tooltip.bodyColor = '#374151';
    Chart.defaults.plugins.tooltip.borderColor = '#E5E7EB';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.boxPadding = 4;
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

  // Setup calendar controls (month navigation & day side panel)
  setupCalendarControls();

  // Setup dashboard controls (MoM toggle, etc.)
  setupDashboardControls();

  // Setup goals planner & chat
  setupGoalsTab();

  // Setup transactions view toggle
  setupTransactionsTab();

  // Setup limits editor
  setupBudgetTab();

  // Setup deterministic simulator
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
      else if (targetId === 'tab-transactions') window.location.hash = '#/transactions';
      else if (targetId === 'tab-recurring') window.location.hash = '#/recurring';
      else if (targetId === 'tab-budget') window.location.hash = '#/budget';
      else if (targetId === 'tab-simulator') window.location.hash = '#/simulator';

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
  } else if (hash === '#/recurring') {
    switchTab('tab-recurring');
  } else if (hash === '#/budget') {
    switchTab('tab-budget');
  } else if (hash === '#/simulator') {
    switchTab('tab-simulator');
  } else {
    switchTab('tab-dashboard');
  }
}

// Persona selection, switching and onboarding
function setupPersonaControls() {
  const btnSalaried = document.getElementById('btn-persona-salaried');
  const btnBusiness = document.getElementById('btn-persona-business');
  const btnEditProfile = document.getElementById('btn-edit-profile');

  btnSalaried.addEventListener('click', () => switchPersona('salaried'));
  btnBusiness.addEventListener('click', () => switchPersona('business'));

  btnEditProfile.addEventListener('click', () => {
    openProfileModal(currentPersona, currentProfileData ? currentProfileData.profile : null);
  });

  // Landing choice cards
  const cardSalaried = document.getElementById('card-choose-salaried');
  const cardBusiness = document.getElementById('card-choose-business');
  if (cardSalaried) {
    cardSalaried.addEventListener('click', () => {
      document.getElementById('persona-landing-modal').style.display = 'none';
      switchPersona('salaried');
    });
  }
  if (cardBusiness) {
    cardBusiness.addEventListener('click', () => {
      document.getElementById('persona-landing-modal').style.display = 'none';
      switchPersona('business');
    });
  }

  // Profile setup modal form
  const profileForm = document.getElementById('profile-setup-form');
  profileForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    await handleProfileSave();
  });

  // Safety buffer slider feedback
  const bufferSlider = document.getElementById('setup-safety-buffer');
  const bufferVal = document.getElementById('safety-buffer-val');
  if (bufferSlider && bufferVal) {
    bufferSlider.addEventListener('input', () => {
      bufferVal.textContent = Math.round(bufferSlider.value * 100) + '%';
    });
  }

  // Add revenue row button for business
  const btnAddRev = document.getElementById('btn-add-revenue-row');
  if (btnAddRev) {
    btnAddRev.addEventListener('click', () => addRevenueRow('', ''));
  }
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

    // Monthly savings transfer (both personas)
    document.getElementById('setup-savings-amount').value = existingData.monthly_savings_amount || 0;
    document.getElementById('setup-savings-day').value = existingData.monthly_savings_day || 30;
  } else {
    document.getElementById('setup-name').value = currentUser.name || '';
    document.getElementById('setup-savings-amount').value = 0;
    document.getElementById('setup-savings-day').value = 30;
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

  // Monthly savings transfer
  payload.monthly_savings_amount = parseFloat(document.getElementById('setup-savings-amount').value) || 0.0;
  payload.monthly_savings_day = parseInt(document.getElementById('setup-savings-day').value) || 30;

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

  if (persona === 'salaried') {
    btnSalaried.classList.add('active');
    btnBusiness.classList.remove('active');
    subTitle.textContent = 'Salaried Cashflow Calendar & Goals';
  } else {
    btnBusiness.classList.add('active');
    btnSalaried.classList.remove('active');
    subTitle.textContent = 'Small Business Cashflow Calendar & Reserve Engine';
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
      await handleFileUpload(files[0]);
    }
  });

  fileInput.addEventListener('change', async () => {
    if (fileInput.files.length > 0) {
      await handleFileUpload(fileInput.files[0]);
    }
  });
}

async function handleFileUpload(file) {
  if (!file.name.endsWith('.csv')) {
    alert('Please upload a valid CSV bank statement.');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  const res = await authFetch('/api/statement/upload', {
    method: 'POST',
    body: formData
  });

  if (res && res.ok) {
    await refreshAllDashboardPanels();
  } else {
    const err = await res.json();
    alert('Import failed: ' + (err.detail || 'Invalid CSV format'));
  }
}

// Refresh all dashboard components immediately without page reload
async function refreshAllDashboardPanels() {
  await Promise.all([
    loadCalendar(),
    loadCommitments(),
    loadMoMComparison(),
    loadTransactions(),
    loadBudgetLimits(),
    loadAnomaliesTable(),
    checkBusinessDip()
  ]);
}

// ==========================================================================
// SAMSUNG-CALENDAR-STYLE MONTH GRID & KPI STRIP
// ==========================================================================

function setupCalendarControls() {
  document.getElementById('cal-prev-btn').addEventListener('click', () => {
    currentCalMonth--;
    if (currentCalMonth < 1) {
      currentCalMonth = 12;
      currentCalYear--;
    }
    loadCalendar();
  });

  document.getElementById('cal-next-btn').addEventListener('click', () => {
    currentCalMonth++;
    if (currentCalMonth > 12) {
      currentCalMonth = 1;
      currentCalYear++;
    }
    loadCalendar();
  });

  document.getElementById('cal-today-btn').addEventListener('click', () => {
    currentCalYear = 2026;
    currentCalMonth = 11;
    loadCalendar();
  });

  // Close day details side panel
  document.getElementById('btn-close-day-panel').addEventListener('click', closeDayDetailPanel);
  document.getElementById('cal-panel-backdrop').addEventListener('click', closeDayDetailPanel);

  // Submit quick add transaction from panel
  document.getElementById('panel-add-tx-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const date = document.getElementById('new-tx-date').value;
    const description = document.getElementById('new-tx-desc').value.trim();
    const amount = parseFloat(document.getElementById('new-tx-amount').value);
    const type = document.getElementById('new-tx-type').value;

    if (!date || !description || isNaN(amount) || amount <= 0) return;

    const res = await authFetch('/api/transactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, description, amount, type })
    });

    if (res && res.ok) {
      document.getElementById('new-tx-desc').value = '';
      document.getElementById('new-tx-amount').value = '';
      closeDayDetailPanel();
      await refreshAllDashboardPanels();
    } else {
      alert('Failed to add transaction.');
    }
  });
}

function closeDayDetailPanel() {
  document.getElementById('cal-side-panel').style.display = 'none';
  document.getElementById('cal-panel-backdrop').style.display = 'none';
}

async function loadCalendar(monthStr) {
  if (!monthStr) {
    monthStr = `${currentCalYear}-${String(currentCalMonth).padStart(2, '0')}`;
  }

  const res = await authFetch(`/api/calendar?month=${monthStr}`);
  if (!res) return;
  const data = await res.json();
  calendarCache = data;

  // Update KPI strip
  const s = data.summary || {};
  document.getElementById('kpi-current-balance').textContent = formatINR(s.balance);
  document.getElementById('kpi-month-income').textContent = formatINR(s.income);
  document.getElementById('kpi-month-spent').textContent = formatINR(s.spent);
  document.getElementById('kpi-reserved-remaining').textContent = formatINR(s.reserved_remaining);
  document.getElementById('kpi-left-to-spend').textContent = formatINR(s.left_to_spend);

  // Update Month Title
  document.getElementById('cal-month-title').textContent = `${MONTH_NAMES[currentCalMonth - 1]} ${currentCalYear}`;

  // Check empty state
  const emptyPrompt = document.getElementById('calendar-empty-prompt');
  const hasAnyRecords = data.days && data.days.some(d => d.spend.length > 0 || d.income.length > 0 || d.reserved.length > 0);
  if (!hasAnyRecords) {
    emptyPrompt.style.display = 'flex';
  } else {
    emptyPrompt.style.display = 'none';
  }

  renderCalendarGrid(data);
}

function renderCalendarGrid(data) {
  const grid = document.getElementById('calendar-grid');
  grid.innerHTML = '';

  const firstDayOfWeek = new Date(currentCalYear, currentCalMonth - 1, 1).getDay(); // 0 = Sun, ..., 6 = Sat
  const daysInCurrentMonth = new Date(currentCalYear, currentCalMonth, 0).getDate();
  const daysInPrevMonth = new Date(currentCalYear, currentCalMonth - 1, 0).getDate();

  // Create dictionary of days
  const daysMap = {};
  if (data.days) {
    data.days.forEach(d => {
      daysMap[d.day] = d;
    });
  }

  // Leading days from previous month
  for (let i = 0; i < firstDayOfWeek; i++) {
    const prevDayNum = daysInPrevMonth - firstDayOfWeek + 1 + i;
    const prevCell = document.createElement('div');
    prevCell.className = 'cal-day-cell other-month';
    prevCell.innerHTML = `
      <div class="cal-day-header">
        <span class="cal-date-number">${prevDayNum}</span>
      </div>
    `;
    grid.appendChild(prevCell);
  }

  // Days of current month (1..daysInCurrentMonth)
  for (let day = 1; day <= daysInCurrentMonth; day++) {
    const dayOfWeek = (firstDayOfWeek + day - 1) % 7;
    const dateStr = `${currentCalYear}-${String(currentCalMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const dayData = daysMap[day] || { spend: [], income: [], reserved: [], totals: { spent: 0, income: 0, reserved: 0 }, has_anomaly: false };

    const isToday = (currentCalYear === 2026 && currentCalMonth === 11 && day === 15);

    const cell = document.createElement('div');
    cell.className = 'cal-day-cell';
    cell.setAttribute('data-date', dateStr);

    let dateNumClasses = 'cal-date-number';
    if (dayOfWeek === 0) dateNumClasses += ' sunday';
    if (dayOfWeek === 6) dateNumClasses += ' saturday';
    if (isToday) dateNumClasses += ' today';

    const anomalyDotHtml = dayData.has_anomaly ? `<span class="cal-anomaly-indicator" title="Unusual transaction detected"></span>` : '';

    // Collect chips:
    // a) Income items
    // b) Spend items
    // c) Reserved items (Paid vs Reserved)
    const allItems = [];
    dayData.income.forEach(item => allItems.push({ kind: 'income', item }));
    dayData.spend.forEach(item => allItems.push({ kind: 'spend', item }));
    dayData.reserved.forEach(item => allItems.push({ kind: 'reserved', item }));

    const maxChips = 3;
    const visibleChips = allItems.slice(0, maxChips);
    const overflowCount = allItems.length - maxChips;

    let chipsHtml = visibleChips.map(c => {
      if (c.kind === 'income') {
        return `<div class="cal-chip income-chip" title="Income: ${escapeHtml(c.item.merchant)}">+₹${Math.round(c.item.amount)} ${escapeHtml(c.item.merchant)}</div>`;
      } else if (c.kind === 'spend') {
        const catCol = CATEGORY_COLORS[c.item.category] || CATEGORY_COLORS['Other'];
        return `<div class="cal-chip spend-chip" style="background:${catCol.bg};color:${catCol.text};" title="${escapeHtml(c.item.category)}: ${escapeHtml(c.item.merchant)}">${escapeHtml(c.item.merchant)} ₹${Math.round(c.item.amount)}</div>`;
      } else if (c.kind === 'reserved') {
        if (c.item.status === 'Paid') {
          return `<div class="cal-chip paid-chip" title="Paid: ${escapeHtml(c.item.name)}">✓ ${escapeHtml(c.item.name)} ₹${Math.round(c.item.amount)}</div>`;
        } else {
          return `<div class="cal-chip reserved-chip" title="Reserved: ${escapeHtml(c.item.name)}">🔒 ${escapeHtml(c.item.name)} ₹${Math.round(c.item.amount)}</div>`;
        }
      }
      return '';
    }).join('');

    if (overflowCount > 0) {
      chipsHtml += `<div class="cal-chip more-chip">+${overflowCount} more</div>`;
    }

    // Dots for 375px mobile view
    let dotsHtml = allItems.slice(0, 6).map(c => {
      if (c.kind === 'income') return `<span class="cal-dot" style="background:#16A34A;" title="Income"></span>`;
      if (c.kind === 'spend') {
        const catCol = CATEGORY_COLORS[c.item.category] || CATEGORY_COLORS['Other'];
        return `<span class="cal-dot" style="background:${catCol.text};" title="${escapeHtml(c.item.category)}"></span>`;
      }
      if (c.kind === 'reserved') {
        return c.item.status === 'Paid'
          ? `<span class="cal-dot" style="background:#3730A3;" title="Paid commitment"></span>`
          : `<span class="cal-dot" style="background:#9CA3AF;" title="Reserved bill"></span>`;
      }
      return '';
    }).join('');

    cell.innerHTML = `
      <div class="cal-day-header">
        <span class="${dateNumClasses}">${day}</span>
        ${anomalyDotHtml}
      </div>
      <div class="cal-chips-list">
        ${chipsHtml}
      </div>
      <div class="cal-dots-container">
        ${dotsHtml}
      </div>
    `;

    cell.addEventListener('click', () => openDayDetailPanel(dateStr, dayData));
    grid.appendChild(cell);
  }

  // Trailing days from next month to complete 6-row (42 cells) or 5-row grid
  const totalRendered = firstDayOfWeek + daysInCurrentMonth;
  const targetTotal = totalRendered > 35 ? 42 : 35;
  const trailingCount = targetTotal - totalRendered;

  for (let t = 1; t <= trailingCount; t++) {
    const nextCell = document.createElement('div');
    nextCell.className = 'cal-day-cell other-month';
    nextCell.innerHTML = `
      <div class="cal-day-header">
        <span class="cal-date-number">${t}</span>
      </div>
    `;
    grid.appendChild(nextCell);
  }
}

function openDayDetailPanel(dateStr, dayData) {
  const panel = document.getElementById('cal-side-panel');
  const backdrop = document.getElementById('cal-panel-backdrop');

  // Format date header nicely
  try {
    const dObj = new Date(dateStr + 'T00:00:00');
    const options = { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric' };
    document.getElementById('panel-date-title').textContent = dObj.toLocaleDateString('en-US', options);
  } catch (e) {
    document.getElementById('panel-date-title').textContent = dateStr;
  }

  document.getElementById('new-tx-date').value = dateStr;

  // Day totals
  document.getElementById('panel-day-spent').textContent = formatINR(dayData.totals.spent);
  document.getElementById('panel-day-income').textContent = formatINR(dayData.totals.income);
  document.getElementById('panel-day-reserved').textContent = formatINR(dayData.totals.reserved);

  // Transactions list
  const txContainer = document.getElementById('panel-transactions-list');
  const allTxs = [...dayData.income, ...dayData.spend];

  if (allTxs.length === 0) {
    txContainer.innerHTML = '<p class="text-sm text-muted">No transactions on this date.</p>';
  } else {
    txContainer.innerHTML = allTxs.map(t => {
      const isCredit = (t.category === 'Income');
      const amtStr = (isCredit ? '+' : '-') + formatINR(t.amount);
      const amtClass = isCredit ? 'text-emerald' : 'text-red';
      const catCol = CATEGORY_COLORS[t.category] || CATEGORY_COLORS['Other'];
      const anomBadge = t.is_anomaly ? `<span class="badge badge-danger">Unusual Spike</span>` : '';

      return `
        <div class="day-tx-card">
          <div class="flex-between">
            <span class="tx-merchant"><strong>${escapeHtml(t.merchant)}</strong></span>
            <span class="tx-amount ${amtClass} font-bold">${amtStr}</span>
          </div>
          <div class="flex-between" style="margin-top: 4px;">
            <span class="badge" style="background:${catCol.bg};color:${catCol.text};">${escapeHtml(t.category)}</span>
            ${anomBadge}
          </div>
        </div>
      `;
    }).join('');
  }

  // Reserved list
  const resContainer = document.getElementById('panel-reserved-list');
  if (dayData.reserved.length === 0) {
    resContainer.innerHTML = '<p class="text-sm text-muted">No scheduled bills or commitments.</p>';
  } else {
    resContainer.innerHTML = dayData.reserved.map(r => {
      const statusBadge = r.status === 'Paid'
        ? `<span class="badge badge-success">✓ Paid</span>`
        : `<span class="badge badge-warning">🔒 Reserved</span>`;

      return `
        <div class="day-tx-card" style="border-left: 3px solid ${r.status === 'Paid' ? '#16A34A' : '#D97706'};">
          <div class="flex-between">
            <span class="tx-merchant"><strong>${escapeHtml(r.name)}</strong></span>
            <span class="tx-amount font-bold">${formatINR(r.amount)}</span>
          </div>
          <div class="flex-between" style="margin-top: 4px;">
            <span class="badge badge-info">${escapeHtml(r.category)}</span>
            ${statusBadge}
          </div>
        </div>
      `;
    }).join('');
  }

  backdrop.style.display = 'block';
  panel.style.display = 'flex';
}

// ==========================================================================
// COMMITMENTS & MOM CHART (100% LIGHT THEME)
// ==========================================================================

async function loadCommitments() {
  const res = await authFetch('/api/commitments');
  if (!res) return;
  const json = await res.json();

  const emptyEl = document.getElementById('commitments-empty');
  const tableEl = document.getElementById('commitments-table');
  const tbody = tableEl.querySelector('tbody');
  const metricTotal = document.getElementById('metric-commitments-total');

  // Also full recurring tab
  const recEmpty = document.getElementById('recurring-empty');
  const recTable = document.getElementById('recurring-full-table');
  const recTbody = recTable ? recTable.querySelector('tbody') : null;

  if (!json.has_data || json.commitments.length === 0) {
    emptyEl.style.display = 'flex';
    tableEl.style.display = 'none';
    if (recEmpty) recEmpty.style.display = 'flex';
    if (recTable) recTable.style.display = 'none';
    if (metricTotal) metricTotal.textContent = '₹0';
    return;
  }

  emptyEl.style.display = 'none';
  tableEl.style.display = 'table';
  if (recEmpty) recEmpty.style.display = 'none';
  if (recTable) recTable.style.display = 'table';

  if (metricTotal) metricTotal.textContent = formatINR(json.monthly_total);

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
  if (recTbody) recTbody.innerHTML = rowsHtml;
}

function setupDashboardControls() {
  const toggle = document.getElementById('mom-chart-type-toggle');
  if (!toggle) return;
  const btns = toggle.querySelectorAll('.btn-pill');
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

  // Color current month bars: red if over limit, primary blue if within limit
  const currentMonthColors = json.categories.map(cat => {
    const isOver = json.overspent.some(o => o.category === cat);
    return isOver ? '#DC2626' : '#2563EB';
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
            backgroundColor: '#94A3B8',
            borderColor: '#64748B',
            borderWidth: 1,
            borderRadius: 4
          },
          {
            label: json.current_month_label,
            data: json.current_month_spending,
            backgroundColor: currentMonthColors,
            borderColor: currentMonthColors,
            borderWidth: 1,
            borderRadius: 4
          },
          {
            label: 'Personalized Budget Limit',
            data: json.limits,
            type: 'line',
            borderColor: '#D97706',
            backgroundColor: '#D97706',
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
            labels: { color: '#374151', font: { family: 'Inter', size: 12 } }
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
            grid: { color: '#E5E7EB' },
            ticks: { color: '#6B7280', font: { family: 'Inter', size: 11 } }
          },
          y: {
            grid: { color: '#E5E7EB' },
            ticks: {
              color: '#6B7280',
              font: { family: 'Inter', size: 11 },
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
            borderColor: '#94A3B8',
            backgroundColor: 'rgba(148, 163, 184, 0.1)',
            tension: 0.3,
            fill: false
          },
          {
            label: json.current_month_label,
            data: json.current_month_spending,
            borderColor: '#2563EB',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            tension: 0.3,
            fill: false
          },
          {
            label: 'Personalized Budget Limit',
            data: json.limits,
            borderColor: '#D97706',
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
          legend: { labels: { color: '#374151' } },
          tooltip: {
            callbacks: {
              label: function(context) {
                return `${context.dataset.label}: ${formatINR(context.raw)}`;
              }
            }
          }
        },
        scales: {
          x: { grid: { color: '#E5E7EB' }, ticks: { color: '#6B7280' } },
          y: {
            grid: { color: '#E5E7EB' },
            ticks: {
              color: '#6B7280',
              callback: function(v) { return formatINR(v); }
            }
          }
        }
      }
    });
  }
}

// ==========================================================================
// TRANSACTIONS & ANOMALIES TAB
// ==========================================================================

function setupTransactionsTab() {
  const toggle = document.getElementById('narration-view-toggle');
  if (!toggle) return;
  const btns = toggle.querySelectorAll('.btn-pill');
  btns.forEach(b => {
    b.addEventListener('click', () => {
      btns.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      narrationViewMode = b.getAttribute('data-view');
      renderTransactionsTable();
    });
  });
}

let cachedTransactionsList = [];

async function loadTransactions() {
  const res = await authFetch('/api/transactions');
  if (!res) return;
  const json = await res.json();
  cachedTransactionsList = json.transactions || [];
  renderTransactionsTable();
}

function renderTransactionsTable() {
  const emptyEl = document.getElementById('transactions-empty');
  const tableEl = document.getElementById('transactions-table');
  const tbody = tableEl.querySelector('tbody');

  if (cachedTransactionsList.length === 0) {
    emptyEl.style.display = 'flex';
    tableEl.style.display = 'none';
    return;
  }

  emptyEl.style.display = 'none';
  tableEl.style.display = 'table';

  tbody.innerHTML = cachedTransactionsList.map(t => {
    const isCredit = (t.type === 'credit');
    const merchantDisplay = (narrationViewMode === 'cleaned')
      ? (t.cleaned_merchant || t.description)
      : t.description;

    const amtStr = (isCredit ? '+' : '-') + formatINR(t.amount);
    const amtClass = isCredit ? 'text-emerald font-bold' : 'text-red font-bold';
    const catCol = CATEGORY_COLORS[t.category] || CATEGORY_COLORS['Other'];

    return `
      <tr>
        <td>${escapeHtml(t.date)}</td>
        <td><strong>${escapeHtml(merchantDisplay)}</strong></td>
        <td><span class="badge" style="background:${catCol.bg};color:${catCol.text};">${escapeHtml(t.category)}</span></td>
        <td class="${amtClass}">${amtStr}</td>
      </tr>
    `;
  }).join('');
}

async function loadAnomaliesTable() {
  const anomRes = await authFetch('/api/anomaly');
  if (anomRes && anomRes.ok) {
    const json = await anomRes.json();
    const anomalies = json.anomalies || [];
    const emptyEl = document.getElementById('anomalies-empty');
    const tableEl = document.getElementById('anomalies-table');
    if (!emptyEl || !tableEl) return;
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

// ==========================================================================
// BUDGET & LIMITS TAB
// ==========================================================================

function setupBudgetTab() {
  const form = document.getElementById('budget-limits-form');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const inputs = document.querySelectorAll('#limits-editor-grid input');
    const limits = {};
    inputs.forEach(inp => {
      const cat = inp.getAttribute('data-cat');
      const val = parseFloat(inp.value) || 0;
      limits[cat] = val;
    });

    const res = await authFetch('/api/limits', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limits })
    });

    if (res && res.ok) {
      await refreshAllDashboardPanels();
      alert('Budget limits updated successfully.');
    }
  });
}

async function loadBudgetLimits() {
  const res = await authFetch('/api/limits');
  if (!res) return;
  const json = await res.json();
  const limits = json.limits || {};

  const grid = document.getElementById('limits-editor-grid');
  if (!grid) return;
  grid.innerHTML = Object.entries(limits).map(([cat, val]) => `
    <div class="limit-item">
      <label>${escapeHtml(cat)}</label>
      <input type="number" class="form-control" data-cat="${escapeHtml(cat)}" value="${val}" min="0">
    </div>
  `).join('');
}

// ==========================================================================
// DETERMINISTIC SIMULATOR TAB
// ==========================================================================

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

  const verdict = sim.verdict || 'Safe';
  document.getElementById('sim-verdict-title').textContent = 'Verdict: ' + verdict;
  document.getElementById('sim-verdict-desc').textContent = `Simulated ${sc.type.replace('_', ' ')} of ${formatINR(sc.amount)} on ${sc.date}.`;

  const banner = document.getElementById('sim-verdict-banner');
  if (verdict === 'Safe') {
    banner.style.borderLeftColor = '#16A34A';
    banner.style.background = '#F0FDF4';
  } else if (verdict === 'Risky') {
    banner.style.borderLeftColor = '#D97706';
    banner.style.background = '#FFFBEB';
  } else {
    banner.style.borderLeftColor = '#DC2626';
    banner.style.background = '#FEF2F2';
  }

  // Prepay Card
  const prepayCard = document.getElementById('prepay-summary-card');
  if (sc.type === 'prepay_loan' && sim.interest_saved !== undefined) {
    prepayCard.style.display = 'block';
    document.getElementById('prepay-cash-dip').textContent = formatINR(sc.amount);
    document.getElementById('prepay-interest-saved').textContent = formatINR(sim.interest_saved);
    document.getElementById('prepay-tenure-reduced').textContent = `${sim.tenure_reduced_months || 0} months reduction`;
    document.getElementById('prepay-assumed-rate').textContent = `${sc.interest_rate || 9}% p.a.`;
  } else {
    prepayCard.style.display = 'none';
  }

  // Min and month-end balances
  document.getElementById('sim-min-before').textContent = formatINR(sim.lowest_balance_before);
  document.getElementById('sim-min-after').textContent = formatINR(sim.lowest_balance_after);
  document.getElementById('sim-end-before').textContent = formatINR(sim.month_end_balance_before);
  document.getElementById('sim-end-after').textContent = formatINR(sim.month_end_balance_after);

  // Bill-Level Obligations Status Table
  const tbody = document.querySelector('#sim-obligations-table tbody');
  tbody.innerHTML = (sim.obligations_status || []).map(ob => {
    function getStatusBadge(status) {
      if (status === 'Covered') return '<span class="badge badge-success">Covered</span>';
      if (status === 'Tight') return '<span class="badge badge-warning">Tight</span>';
      return '<span class="badge badge-danger">Short</span>';
    }

    return `
      <tr>
        <td><strong>${escapeHtml(ob.name)}</strong></td>
        <td>${escapeHtml(ob.date)}</td>
        <td>${formatINR(ob.amount)}</td>
        <td>${getStatusBadge(ob.status_before)}</td>
        <td>${getStatusBadge(ob.status_after)}</td>
      </tr>
    `;
  }).join('');
}

// ==========================================================================
// BUSINESS INCOME-DIP ENGINE
// ==========================================================================

async function checkBusinessDip() {
  if (currentPersona !== 'business') {
    document.getElementById('business-dip-banner').style.display = 'none';
    return;
  }

  const res = await authFetch('/api/dip');
  if (!res) return;
  const json = await res.json();

  const banner = document.getElementById('business-dip-banner');
  if (json.triggered) {
    banner.style.display = 'flex';
    document.getElementById('dip-banner-title').textContent = `Income Dip Detected: Shortfall of ${formatINR(json.shortfall)}`;
    document.getElementById('dip-banner-desc').textContent =
      `Month-to-date inflow is ${formatINR(json.actual_mtd_inflow)}, falling below baseline target. Recommended cuts: Discretionary ₹${Math.round(json.cuts?.P3_discretionary?.reduce((a,c)=>a+c.amount, 0) || 0)} / Needed ₹${Math.round(json.cuts?.P2_needed?.reduce((a,c)=>a+c.amount, 0) || 0)}.`;

    // Trigger auto message in copilot chat once per switch
    if (!dipAutoMessageSent) {
      dipAutoMessageSent = true;
      sendCopilotMessage('Income dip detected. What cuts do you recommend?');
    }
  } else {
    banner.style.display = 'none';
  }
}

// ==========================================================================
// GOALS & INVESTMENTS TAB
// ==========================================================================

function setupGoalsTab() {
  const form = document.getElementById('goal-planner-form');
  const chatForm = document.getElementById('goals-chat-form');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const item = document.getElementById('goal-item-name').value.trim();
    const target_amount = parseFloat(document.getElementById('goal-target-amount').value);
    const horizon_months = parseInt(document.getElementById('goal-horizon-months').value);
    const priority = document.getElementById('goal-priority').value;

    const res = await authFetch('/api/goals/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item, target_amount, horizon_months, priority })
    });

    if (res && res.ok) {
      const json = await res.json();
      displayGoalPlan(json.plan);
    }
  });

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = document.getElementById('goals-chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    sendGoalsChatMessage(msg);
  });
}

function displayGoalPlan(plan) {
  const area = document.getElementById('goal-result-area');
  area.style.display = 'block';

  document.getElementById('plan-monthly-sip').textContent = formatINR(plan.monthly_sip);
  document.getElementById('plan-target-amt').textContent = formatINR(plan.target_amount);
  document.getElementById('plan-vehicle-name').textContent = plan.recommended_vehicle.name;
  document.getElementById('plan-vehicle-rate').textContent = `${plan.recommended_vehicle.expected_return_pct}% p.a. expected`;

  const banner = document.getElementById('plan-feasibility-banner');
  const feas = plan.feasibility;
  if (feas.is_feasible) {
    banner.className = 'goal-feasibility-banner feasible';
    banner.textContent = `Feasible! Your monthly surplus of ${formatINR(feas.monthly_surplus)} covers the required ${formatINR(plan.monthly_sip)}/mo.`;
  } else {
    banner.className = 'goal-feasibility-banner not-feasible';
    banner.textContent = `Shortfall of ${formatINR(feas.shortfall)}/mo. Review suggested budget cuts below.`;
  }

  // Budget cuts table
  const tbody = document.querySelector('#goal-cuts-table tbody');
  if (plan.budget_cuts && plan.budget_cuts.length > 0) {
    tbody.innerHTML = plan.budget_cuts.map(c => `
      <tr>
        <td><strong>${escapeHtml(c.category)}</strong></td>
        <td>${formatINR(c.current_spend)}</td>
        <td class="text-emerald font-bold">-${formatINR(c.recommended_cut)}</td>
        <td>${formatINR(c.target_spend)}</td>
      </tr>
    `).join('');
  } else {
    tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No budget cuts needed! Current cashflow surplus is sufficient.</td></tr>`;
  }

  // Monthly Milestone schedule
  const schedBody = document.querySelector('#goal-schedule-table tbody');
  schedBody.innerHTML = plan.monthly_schedule.map(s => `
    <tr>
      <td>Month ${s.month}</td>
      <td>${formatINR(s.invested_cumulative)}</td>
      <td class="text-emerald font-bold">${formatINR(s.projected_value)}</td>
    </tr>
  `).join('');
}

async function sendGoalsChatMessage(text) {
  appendChatMessage('goals', 'user', text);
  goalsChatHistory.push({ role: 'user', content: text });

  try {
    const res = await authFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: goalsChatHistory })
    });
    if (!res) return;
    const data = await res.json();
    goalsChatHistory.push({ role: 'assistant', content: data.reply });
    appendChatMessage('goals', 'bot', data.reply);
  } catch (err) {
    appendChatMessage('goals', 'bot', 'Unable to reach assistant.');
  }
}

// ==========================================================================
// FLOATING COPILOT CHAT
// ==========================================================================

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
  if (indicator) indicator.style.display = 'flex';

  try {
    const res = await authFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: copilotChatHistory })
    });
    if (indicator) indicator.style.display = 'none';
    if (!res) return;
    const data = await res.json();
    copilotChatHistory.push({ role: 'assistant', content: data.reply });
    appendChatMessage('copilot', 'bot', data.reply);
  } catch (err) {
    if (indicator) indicator.style.display = 'none';
    appendChatMessage('copilot', 'bot', 'Unable to reach Copilot.');
  }
}

function appendChatMessage(target, sender, text) {
  const containerId = target === 'goals' ? 'goals-chat-messages' : 'chat-messages';
  const container = document.getElementById(containerId);
  if (!container) return;

  const div = document.createElement('div');
  div.className = `chat-msg ${sender}-msg`;
  let formatted = escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
  div.innerHTML = `<div class="msg-bubble">${formatted}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}
