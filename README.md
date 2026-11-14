# FINWISE-AI (CashPilot)

Intelligent Cashflow Calendar, Deterministic What-If Stress-Testing & Goal Planning Web Application.

Built with a **FastAPI** backend, **Vanilla JavaScript**, and **Chart.js** frontend with a responsive, modern light-theme UI.

---

## Key Features

1. **Samsung-Calendar-Style Cashflow Dashboard**:
   - 7-column, Sunday-first monthly grid displaying daily income, spending chips categorized by color, and reserved obligations.
   - Distinct lock indicators for scheduled obligations and solid checkmark badges for paid obligations within 3 days.
   - Anomaly indicators for unusual spending spikes.
   - Interactive side panel / bottom sheet with day totals, transaction lists, commitment schedules, and quick transaction logging with immediate real-time dashboard refresh.
   - Responsive design with colored dots on mobile view (375px) and drawer bottom sheet.

2. **KPI Header Strip**:
   - Current ledger balance, month income, month spent, reserved obligations remaining, and left to spend (`balance - reserved_remaining - buffer`).

3. **Deterministic Simulator & What-If Engine**:
   - Day-by-day cashflow simulation for the current month.
   - Evaluates purchases, loan EMIs, loan prepayments with interest savings, subscription cancellations, and income changes.
   - Outputs before-and-after lowest running balance, month-end balance, bill-level statuses (`Covered`, `Tight`, `Short`), and verdict (`Safe`, `Risky`, `Not advisable`).

4. **Dual Persona Modes**:
   - **Salaried**: Monthly salary, salary credit date, optional secondary income, and recurring commitments.
   - **Small Business**: Variable revenue history, rolling revenue baseline with user-adjustable safety buffer, and the **Business Income-Dip Priority Engine** (P1 Essential, P2 Needed, P3 Discretionary cuts).

5. **Actuals-Based Budget Limits & Month-over-Month Comparison**:
   - Limits derived from actual spend history (discretionary $\times 0.90$, fixed at latest actual).
   - Grouped bar / trend line Chart.js visualization with budget alert tags.

6. **Investments & Goals Planner (`#/goals`)**:
   - SIP roadmap calculation, vehicle recommendations by time horizon, and budget reallocation.

---

## Quickstart

### Prerequisites
- Python 3.10+

### Installation
```bash
git clone https://github.com/MALTHESH-13/FINWISE-AI.git
cd FINWISE-AI
pip install -r requirements.txt
```

### Running the Application
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open your browser at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Default demo credentials:
- **Email**: `demo@cashpilot.app`
- **Password**: `demo1234`
*(Or click "Continue with demo account" on the login screen)*

---

## Limitations & Disclaimer
- Financial calculations and SIP simulations are for illustrative and planning purposes only and do not constitute certified financial advice.
- All user data is stored locally in SQLite (`data/app.db`) and user-specific directories with PBKDF2-hashed passwords and HMAC session tokens.
