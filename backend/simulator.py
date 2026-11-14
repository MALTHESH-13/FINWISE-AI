import os
import csv
import math
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

def get_user_csv_path(user_id: int, persona: Optional[str] = None) -> str:
    try:
        from backend.persona import get_active_persona
        if not persona:
            persona = get_active_persona(user_id)
    except Exception:
        persona = "salaried"
    persona_path = os.path.join(DATA_DIR, "users", str(user_id), persona, "transactions.csv")
    if os.path.exists(persona_path):
        return persona_path
    legacy_path = os.path.join(DATA_DIR, "users", str(user_id), "transactions.csv")
    if os.path.exists(legacy_path):
        return legacy_path
    os.makedirs(os.path.dirname(persona_path), exist_ok=True)
    return persona_path

def load_user_transactions(user_id: int, persona: Optional[str] = None) -> List[Dict[str, Any]]:
    csv_path = get_user_csv_path(user_id, persona)
    if not os.path.exists(csv_path):
        return []
    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                records.append({
                    "date": row["date"].strip(),
                    "description": row["description"].strip(),
                    "amount": float(row["amount"]),
                    "type": row["type"].strip().lower()
                })
            except Exception:
                continue
    return sorted(records, key=lambda x: x["date"])

def detect_recurring_and_cashflow(records: List[Dict[str, Any]], anchor_date: datetime):
    """
    Detects recurring obligations, recurring income, and daily discretionary spend.
    """
    if not records:
        return {
            "current_balance": 45000.0,
            "recurring_income": [],
            "recurring_obligations": [],
            "daily_discretionary_mean": 300.0,
            "daily_discretionary_std": 150.0
        }

    # Calculate net ledger balance with a healthy base
    credits = sum(r["amount"] for r in records if r["type"] == "credit")
    debits = sum(r["amount"] for r in records if r["type"] == "debit")
    # Base starting balance to ensure realistic working balance
    current_balance = max(25000.0, 50000.0 + (credits - debits) * 0.5)

    # Detect recurring items by grouping descriptions
    debit_groups: Dict[str, List[Dict[str, Any]]] = {}
    credit_groups: Dict[str, List[Dict[str, Any]]] = {}

    for r in records:
        desc_lower = r["description"].lower()
        if r["type"] == "debit":
            # Group by key category or normalized desc
            key = None
            if "rent" in desc_lower or "hostel" in desc_lower:
                key = "Rent / Hostel"
            elif "emi" in desc_lower or "loan" in desc_lower:
                key = "Loan EMI"
            elif "electricity" in desc_lower or "bescom" in desc_lower:
                key = "Electricity / Utility"
            elif "netflix" in desc_lower:
                key = "Netflix"
            elif "spotify" in desc_lower:
                key = "Spotify"
            elif "coworking" in desc_lower or "wework" in desc_lower:
                key = "Office Space"
            elif "adobe" in desc_lower or "figma" in desc_lower:
                key = "Software Subscriptions"
            
            if key:
                debit_groups.setdefault(key, []).append(r)
        else:
            if "salary" in desc_lower or "allowance" in desc_lower or "client" in desc_lower or "gig" in desc_lower:
                credit_groups.setdefault(r["description"][:20], []).append(r)

    # Build obligations for the next 30 days from anchor_date
    obligations = []
    for name, items in debit_groups.items():
        avg_amt = sum(it["amount"] for it in items) / len(items)
        # Find representative day of month
        days = [int(it["date"].split("-")[2]) for it in items]
        rep_day = max(1, min(28, int(sum(days) / len(days))))

        # Calculate next due date relative to anchor_date
        target_year = anchor_date.year
        target_month = anchor_date.month
        try:
            due_dt = datetime(target_year, target_month, rep_day)
            if due_dt < anchor_date:
                if target_month == 12:
                    due_dt = datetime(target_year + 1, 1, rep_day)
                else:
                    due_dt = datetime(target_year, target_month + 1, rep_day)
        except ValueError:
            due_dt = anchor_date + timedelta(days=10)

        # Only include if within 30-day horizon
        if 0 <= (due_dt - anchor_date).days <= 30:
            obligations.append({
                "name": name,
                "due_date": due_dt.strftime("%Y-%m-%d"),
                "amount": round(avg_amt, 2)
            })

    obligations = sorted(obligations, key=lambda x: x["due_date"])

    # Build recurring income for the next 30 days
    incomes = []
    for name, items in credit_groups.items():
        avg_amt = sum(it["amount"] for it in items) / len(items)
        days = [int(it["date"].split("-")[2]) for it in items]
        rep_day = max(1, min(28, int(sum(days) / len(days))))
        target_year = anchor_date.year
        target_month = anchor_date.month
        try:
            inc_dt = datetime(target_year, target_month, rep_day)
            if inc_dt < anchor_date:
                if target_month == 12:
                    inc_dt = datetime(target_year + 1, 1, rep_day)
                else:
                    inc_dt = datetime(target_year, target_month + 1, rep_day)
        except ValueError:
            inc_dt = anchor_date + timedelta(days=15)

        if 0 <= (inc_dt - anchor_date).days <= 30:
            incomes.append({
                "name": name,
                "date": inc_dt.strftime("%Y-%m-%d"),
                "amount": round(avg_amt, 2)
            })

    # Variable spend metrics
    discretionary_debits = [
        r["amount"] for r in records 
        if r["type"] == "debit" and not any(k in r["description"].lower() for k in ["rent", "hostel", "emi", "loan", "bescom", "wework"])
    ]
    if discretionary_debits:
        mean_spend = sum(discretionary_debits) / (len(records) / 3.0 + 10)
        std_spend = mean_spend * 0.4
    else:
        mean_spend = 350.0
        std_spend = 150.0

    return {
        "current_balance": round(current_balance, 2),
        "recurring_income": incomes,
        "recurring_obligations": obligations,
        "daily_discretionary_mean": mean_spend,
        "daily_discretionary_std": std_spend
    }

def calculate_prepay_loan_savings(amount: float, annual_rate: float = 9.0, current_emi: Optional[float] = None) -> Dict[str, Any]:
    """
    ADD 4: Prepay loan what-if:
    Reduces remaining principal, recomputes tenure at the same EMI,
    shows cash dip now vs total interest saved.
    Assumed interest rate default 9% p.a.
    """
    if annual_rate <= 0:
        annual_rate = 9.0

    r = (annual_rate / 100.0) / 12.0

    # Default loan parameters if not already known
    if not current_emi or current_emi <= 0:
        current_emi = 15000.0  # standard EMI

    # Estimate original remaining principal assuming standard 36 remaining months
    assumed_tenure = 36
    orig_principal = current_emi * ((1 + r)**assumed_tenure - 1) / (r * (1 + r)**assumed_tenure)

    # Apply prepayment
    prepay_amount = min(amount, orig_principal * 0.95)
    new_principal = max(1000.0, orig_principal - prepay_amount)

    # Recompute tenure at same EMI:
    # (1+r)^N = EMI / (EMI - P * r)
    denom = current_emi - (new_principal * r)
    if denom > 0:
        val = current_emi / denom
        new_tenure = math.ceil(math.log(val) / math.log(1 + r))
    else:
        new_tenure = 1

    total_paid_orig = assumed_tenure * current_emi
    total_paid_new = prepay_amount + (new_tenure * current_emi)
    interest_saved = max(0.0, total_paid_orig - total_paid_new)
    tenure_reduced = max(0, assumed_tenure - new_tenure)

    return {
        "cash_dip": round(amount, 2),
        "interest_saved": round(interest_saved, 2),
        "assumed_rate": annual_rate,
        "current_emi": round(current_emi, 2),
        "old_tenure_months": assumed_tenure,
        "new_tenure_months": new_tenure,
        "tenure_reduced_months": tenure_reduced
    }

def run_monte_carlo(current_balance: float, incomes: List[Dict], obligations: List[Dict],
                     daily_mean: float, daily_std: float, anchor_date: datetime,
                     extra_scenario: Optional[Dict[str, Any]] = None,
                     iterations: int = 400):
    """
    Runs Monte Carlo simulation for 30 days.
    """
    horizon_days = 30
    date_list = [(anchor_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(horizon_days + 1)]

    # Pre-map daily deterministic flows
    inflows_by_date = {}
    for inc in incomes:
        inflows_by_date[inc["date"]] = inflows_by_date.get(inc["date"], 0.0) + inc["amount"]

    outflows_by_date = {}
    for ob in obligations:
        outflows_by_date[ob["due_date"]] = outflows_by_date.get(ob["due_date"], 0.0) + ob["amount"]

    # Extra scenario modifications
    scenario_one_time_debit = 0.0
    scenario_debit_date = None
    recurring_income_delta = 0.0
    cancel_sub_name = None

    if extra_scenario:
        stype = extra_scenario.get("type")
        samount = float(extra_scenario.get("amount", 0.0))
        sdate = extra_scenario.get("date", date_list[1])

        if stype in ["purchase", "prepay_loan"]:
            scenario_one_time_debit = samount
            scenario_debit_date = sdate
        elif stype == "loan_emi":
            # Adds monthly EMI
            scenario_one_time_debit = samount
            scenario_debit_date = sdate
        elif stype == "income_change":
            recurring_income_delta = samount
        elif stype == "cancel_subscription":
            cancel_sub_name = extra_scenario.get("name", "").lower()

    # Track trajectories and obligation checks across runs
    daily_balances_all = [[] for _ in range(horizon_days + 1)]
    min_balances = []
    shortage_count = 0

    # Obligation hits tracker: {due_date: [success_bool, ...]}
    obligation_checks: Dict[str, List[bool]] = {ob["due_date"]: [] for ob in obligations}

    random.seed(42)  # For deterministic reproduction

    for _ in range(iterations):
        balance = current_balance
        min_bal = balance
        had_shortage = False

        for day_idx in range(horizon_days + 1):
            cur_date = date_list[day_idx]

            # Inflow
            day_in = inflows_by_date.get(cur_date, 0.0) + recurring_income_delta
            # Outflow
            day_out = outflows_by_date.get(cur_date, 0.0)

            # Check if this date has a cancelled subscription
            if cancel_sub_name:
                for ob in obligations:
                    if ob["due_date"] == cur_date and cancel_sub_name in ob["name"].lower():
                        day_out = max(0.0, day_out - ob["amount"])

            # Check scenario one-time debit
            if scenario_debit_date == cur_date:
                day_out += scenario_one_time_debit

            # Discretionary spending
            if day_idx > 0:
                spend = max(0.0, random.gauss(daily_mean, daily_std))
                balance -= spend

            balance += (day_in - day_out)
            daily_balances_all[day_idx].append(balance)

            if balance < min_bal:
                min_bal = balance
            if balance < 0:
                had_shortage = True

            # Record if balance satisfied upcoming obligation
            if cur_date in obligation_checks:
                req_amt = outflows_by_date.get(cur_date, 0.0)
                obligation_checks[cur_date].append(balance >= req_amt)

        min_balances.append(min_bal)
        if had_shortage:
            shortage_count += 1

    # Percentiles
    p10_traj = []
    p50_traj = []
    p90_traj = []
    for day_idx in range(horizon_days + 1):
        vals = sorted(daily_balances_all[day_idx])
        p10_traj.append(vals[int(iterations * 0.10)])
        p50_traj.append(vals[int(iterations * 0.50)])
        p90_traj.append(vals[int(iterations * 0.90)])

    sorted_mins = sorted(min_balances)
    med_min_bal = sorted_mins[int(iterations * 0.50)]
    shortage_prob = round(shortage_count / float(iterations), 3)

    # Obligation probabilities
    ob_probs = {}
    for dt, checks in obligation_checks.items():
        if checks:
            ob_probs[dt] = round(sum(1 for c in checks if c) / float(len(checks)), 3)
        else:
            ob_probs[dt] = 1.0

    return {
        "dates": date_list,
        "p10": p10_traj,
        "p50": p50_traj,
        "p90": p90_traj,
        "min_balance": round(med_min_bal, 2),
        "shortage_prob": shortage_prob,
        "obligation_probs": ob_probs
    }

def get_forecast(user_id: int, persona: Optional[str] = None) -> Dict[str, Any]:
    records = load_user_transactions(user_id, persona)
    anchor_date = datetime(2026, 11, 15)
    model = detect_recurring_and_cashflow(records, anchor_date)

    baseline = run_monte_carlo(
        current_balance=model["current_balance"],
        incomes=model["recurring_income"],
        obligations=model["recurring_obligations"],
        daily_mean=model["daily_discretionary_mean"],
        daily_std=model["daily_discretionary_std"],
        anchor_date=anchor_date
    )

    # Map obligations
    ob_list = []
    for ob in model["recurring_obligations"]:
        prob = baseline["obligation_probs"].get(ob["due_date"], 1.0)
        status = "Safe" if prob >= 0.95 else ("At risk" if prob >= 0.70 else "Will likely miss")
        ob_list.append({
            "name": ob["name"],
            "due_date": ob["due_date"],
            "amount": ob["amount"],
            "prob_before": prob,
            "prob_after": prob,
            "status": status
        })

    return {
        "current_balance": model["current_balance"],
        "min_balance": baseline["min_balance"],
        "shortage_prob": baseline["shortage_prob"],
        "dates": baseline["dates"],
        "p10": baseline["p10"],
        "p50": baseline["p50"],
        "p90": baseline["p90"],
        "obligations": ob_list
    }

def simulate_scenario(user_id: int, scenario: Dict[str, Any], persona: Optional[str] = None) -> Dict[str, Any]:
    """
    Runs before vs after simulation.
    """
    records = load_user_transactions(user_id, persona)
    anchor_date = datetime(2026, 11, 15)
    model = detect_recurring_and_cashflow(records, anchor_date)

    # Baseline (Before)
    baseline = run_monte_carlo(
        current_balance=model["current_balance"],
        incomes=model["recurring_income"],
        obligations=model["recurring_obligations"],
        daily_mean=model["daily_discretionary_mean"],
        daily_std=model["daily_discretionary_std"],
        anchor_date=anchor_date
    )

    # After scenario
    simulated = run_monte_carlo(
        current_balance=model["current_balance"],
        incomes=model["recurring_income"],
        obligations=model["recurring_obligations"],
        daily_mean=model["daily_discretionary_mean"],
        daily_std=model["daily_discretionary_std"],
        anchor_date=anchor_date,
        extra_scenario=scenario
    )

    # ADD 3: Bill-level check
    obligations_result = []
    first_at_risk_bill = None

    for ob in model["recurring_obligations"]:
        p_before = baseline["obligation_probs"].get(ob["due_date"], 1.0)
        p_after = simulated["obligation_probs"].get(ob["due_date"], 1.0)

        if p_after >= 0.95:
            st = "Safe"
        elif p_after >= 0.60:
            st = "At risk"
            if not first_at_risk_bill:
                first_at_risk_bill = ob["name"]
        else:
            st = "Will likely miss"
            if not first_at_risk_bill:
                first_at_risk_bill = ob["name"]

        obligations_result.append({
            "name": ob["name"],
            "due_date": ob["due_date"],
            "amount": ob["amount"],
            "prob_before": p_before,
            "prob_after": p_after,
            "status": st
        })

    # Prepay loan specific details
    prepay_details = None
    if scenario.get("type") == "prepay_loan":
        rate = float(scenario.get("interest_rate", 9.0))
        # Find EMI obligation if exists
        emi_amt = 15000.0
        for ob in model["recurring_obligations"]:
            if "emi" in ob["name"].lower() or "loan" in ob["name"].lower():
                emi_amt = ob["amount"]
                break
        prepay_details = calculate_prepay_loan_savings(
            amount=float(scenario.get("amount", 0.0)),
            annual_rate=rate,
            current_emi=emi_amt
        )

    # Formulate verdict
    min_diff = simulated["min_balance"] - baseline["min_balance"]
    shortage_diff = simulated["shortage_prob"] - baseline["shortage_prob"]

    if simulated["shortage_prob"] <= 0.05 and not first_at_risk_bill:
        verdict = "Safe to proceed. Your cashflow remains resilient."
    elif simulated["shortage_prob"] > 0.25 or any(o["status"] == "Will likely miss" for o in obligations_result):
        verdict = "High risk of cash shortfall. You are likely to face trouble covering essential bills."
    else:
        verdict = "Caution recommended. Cash buffer will be significantly tight."

    return {
        "verdict": verdict,
        "min_balance_before": baseline["min_balance"],
        "min_balance_after": simulated["min_balance"],
        "min_balance_diff": round(min_diff, 2),
        "shortage_prob_before": baseline["shortage_prob"],
        "shortage_prob_after": simulated["shortage_prob"],
        "shortage_prob_diff": round(shortage_diff, 3),
        "obligations": obligations_result,
        "first_at_risk_bill": first_at_risk_bill,
        "prepay_details": prepay_details,
        "dates": baseline["dates"],
        "baseline_p50": baseline["p50"],
        "simulated_p50": simulated["p50"]
    }
