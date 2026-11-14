# FINWISE-AI (CashPilot)

Intelligent Cashflow Forecasting, Stress-Testing & Goal Planning Web Application.

Built with **FastAPI** backend + **Vanilla JavaScript** and **Chart.js** frontend with a responsive dark-mode UI.

---

## Key Features

1. **Dual Persona Modes**:
   - **Salaried**: Fixed monthly salary, optional secondary income, salary credit date, recurring commitments, and goal planning.
   - **Small Business**: Variable revenue cycles, automated **Business Income-Dip Priority Engine**, rolling revenue baseline, and cut recommendations.
2. **Flexible Statement Ingestion**:
   - Drag-and-drop CSV parser accepting standard formats (`Date`, `Description`, `Amount` or `Debit`/`Credit`).
   - Automated narration cleaning and categorization into 14 financial categories.
3. **Forecasting & Monte Carlo Simulation**:
   - Stochastic 30-day balance projections (P10, P50, P90 percentiles) with shortage risk probability.
   - Interactive what-if simulator (purchases, loan EMI, loan prepayment with interest savings, subscription cancellations, income changes).
4. **Investments & Goals Planner (`#/goals`)**:
   - Rule-based financial advisor chatbot and visual roadmap generator.
   - Horizon-based vehicle recommendations: `<12m` (RD/Liquid Fund @ 6.5%), `12-36m` (Hybrid SIP @ 9%), `>36m` (Equity Index SIP @ 12%).
   - Future value SIP calculator and monthly milestone schedule.
5. **Business Income-Dip Priority Engine**:
   - Automatically detects current-month revenue dips below baseline.
   - Recommends structured expense reductions: P1 Essential (protect payroll & rent), P2 Needed, P3 Discretionary cuts.

---

## Income Baseline Formulas

- **Salaried Baseline**: `Fixed Salary + Secondary Income`
- **Small Business Baseline**: `Rolling mean of last 3 months revenue × (1 - safety buffer)`
  - Default safety buffer: `15%` (user-adjustable between 0% and 40%).

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

### Running Tests
```bash
python test_new_acceptance.py
```

---

## Limitations & Disclaimer
- Rule-based financial guidance and SIP projections are illustrative calculations and do not constitute certified financial advice.
- All data is stored locally in SQLite (`data/app.db`) and user-specific directories with PBKDF2-hashed passwords and HMAC session tokens. No external API keys or third-party cloud trackers are used.
