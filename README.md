# FINWISE-AI (CashPilot)

Intelligent Cashflow Forecasting, Stress-Testing & Goal Planning Web Application powered by **Google Gemini AI**.

Built with **FastAPI** backend + **Vanilla JavaScript** and **Chart.js** frontend with a responsive dark-mode UI.

---

## Key Features

1. **Google Gemini AI Intelligence (`gemini-3.5-flash-lite` / `gemini-3-flash-preview`)**:
   - **Copilot Chat Assistant**: Grounded in the user's real cashflow, balances, and recurring obligations.
   - **Strategic Financial Audit**: Generates 3 prioritized, automated AI audit insights directly on the dashboard.
   - **What-If Simulations & Goal Coaching**: Enhances Monte Carlo simulation results and SIP roadmaps with personalized Gemini insights.
   - **Graceful Fallback**: Offline/network resilience ensures 100% deterministic rule-based continuity if the API is unreachable.
2. **Dual Persona Modes**:
   - **Salaried**: Fixed monthly salary, optional secondary income, salary credit date, recurring commitments, and goal planning.
   - **Small Business**: Variable revenue cycles, automated **Business Income-Dip Priority Engine**, rolling revenue baseline, and cut recommendations.
3. **Flexible Statement Ingestion**:
   - Drag-and-drop CSV parser accepting standard formats (`Date`, `Description`, `Amount` or `Debit`/`Credit`).
   - Automated narration cleaning and categorization into 14 financial categories.
4. **Forecasting & Monte Carlo Simulation**:
   - Stochastic 30-day balance projections (P10, P50, P90 percentiles) with shortage risk probability.
   - Interactive what-if simulator (purchases, loan EMI, loan prepayment with interest savings, subscription cancellations, income changes).
5. **Investments & Goals Planner (`#/goals`)**:
   - Conversational financial advisor chatbot and visual roadmap generator.
   - Horizon-based vehicle recommendations: `<12m` (RD/Liquid Fund @ 6.5%), `12-36m` (Hybrid SIP @ 9%), `>36m` (Equity Index SIP @ 12%).
   - Future value SIP calculator and monthly milestone schedule.
6. **Business Income-Dip Priority Engine**:
   - Automatically detects current-month revenue dips below baseline.
   - Recommends structured expense reductions: P1 Essential (protect payroll & rent), P2 Needed, P3 Discretionary cuts.

---

## Income Baseline Formulas

- **Salaried Baseline**: `Fixed Salary + Secondary Income`
- **Small Business Baseline**: `Rolling mean of last 3 months revenue × (1 - safety buffer)`
  - Default safety buffer: `15%` (user-adjustable between 0% and 40%).

---

## Google Gemini Configuration

The application includes native integration with the Gemini API using the Python standard library (no extra SDK required):
```bash
# Optional: Set custom API key in environment
export GEMINI_API_KEY="your-gemini-api-key"
```
If not set, it defaults to the configured project key.

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
# Full acceptance test suite (7/7 checks)
python test_new_acceptance.py

# Gemini AI integration tests
python test_gemini_integration.py
```

---

## Limitations & Disclaimer
- Rule-based financial guidance and SIP projections are illustrative calculations and do not constitute certified financial advice.
- All user data is stored locally in SQLite (`data/app.db`) and user-specific directories with PBKDF2-hashed passwords and HMAC session tokens.
