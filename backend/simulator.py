import os
import csv
import math
import calendar
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

from backend.config import BASE_DIR, DATA_DIR, get_data_dir

def get_user_csv_path(user_id: int, persona: Optional[str] = None) -> str:
    try:
        from backend.persona import get_active_persona
        if not persona:
            persona = get_active_persona(user_id)
    except Exception:
        persona = "salaried"
    data_dir = get_data_dir()
    persona_path = os.path.join(data_dir, "users", str(user_id), persona, "transactions.csv")
    if os.path.exists(persona_path):
        return persona_path
    legacy_path = os.path.join(data_dir, "users", str(user_id), "transactions.csv")
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

def calculate_prepay_loan_savings(amount: float, annual_rate: float = 9.0, current_emi: Optional[float] = None) -> Dict[str, Any]:
    """
    Prepay loan what-if:
    Reduces remaining principal, recomputes tenure at the same EMI,
    shows cash dip now vs total interest saved.
    Assumed interest rate default 9% p.a.
    """
    if annual_rate <= 0:
        annual_rate = 9.0

    r = (annual_rate / 100.0) / 12.0

    if not current_emi or current_emi <= 0:
        current_emi = 15000.0

    assumed_tenure = 36
    orig_principal = current_emi * ((1 + r)**assumed_tenure - 1) / (r * (1 + r)**assumed_tenure)

    prepay_amount = min(amount, orig_principal * 0.95)
    new_principal = max(1000.0, orig_principal - prepay_amount)

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

def simulate_scenario(user_id: int, scenario: Dict[str, Any], persona: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic simulator + bill-level check + what-if:
    Builds a day-by-day running balance for the rest of the current month.
    = current balance, minus reserved items on their due dates,
      plus expected salary (Salaried only, if salary day is still ahead and not yet credited).
    Applies what-if and returns before vs after:
    lowest running balance, month-end balance, per-bill status (Covered / Tight / Short),
    and verdict: Safe (lowest >= buffer), Risky (0 <= lowest < buffer), Not advisable (lowest < 0).
    """
    from backend.persona import (
        get_active_persona,
        get_profile_data,
        get_fixed_commitments
    )

    if not persona:
        persona = get_active_persona(user_id)

    records = load_user_transactions(user_id, persona)

    # Current reference date: Nov 15, 2026 for sample statements or today's date
    anchor_date = date(2026, 11, 15)
    year = anchor_date.year
    month = anchor_date.month
    num_days = calendar.monthrange(year, month)[1]
    curr_month_prefix = f"{year}-{month:02d}"

    # Profile settings
    prof_info = get_profile_data(user_id, persona)
    profile = prof_info.get("profile", {})
    baseline_income = prof_info.get("baseline_income", 0.0)

    # Calculate current ledger balance
    credits = sum(r["amount"] for r in records if r["type"] == "credit")
    debits = sum(r["amount"] for r in records if r["type"] == "debit")

    starting_balance = float(profile.get("starting_balance", 0.0) or 0.0)
    statement_balance = float(profile.get("statement_balance", 0.0) or 0.0)

    if statement_balance > 0:
        current_balance = statement_balance
    elif starting_balance > 0:
        current_balance = starting_balance + credits - debits
    elif credits > 0:
        current_balance = credits - debits
    elif debits > 0 and baseline_income > 0:
        debit_months = len(set(r["date"][:7] for r in records if len(r["date"]) >= 7)) or 1
        effective_credits = max(baseline_income * debit_months, debits + 10000.0)
        current_balance = effective_credits - debits
    else:
        current_balance = credits - debits

    # Buffer: from scenario parameter, or profile safety buffer, or default 10,000
    scenario_buffer = scenario.get("buffer")
    if scenario_buffer is not None and float(scenario_buffer) >= 0:
        buffer_val = float(scenario_buffer)
    else:
        buffer_val = float(profile.get("safety_buffer", 0.15) * baseline_income) if baseline_income > 0 else 10000.0
        if buffer_val <= 0:
            buffer_val = 10000.0

    # Expected salary check (Salaried only)
    salary_to_add = 0.0
    salary_credit_day = None
    if persona == "salaried":
        salary_amt = float(profile.get("salary", 0.0) or baseline_income)
        sal_day = int(profile.get("salary_day", 1))
        sal_day = max(1, min(num_days, sal_day))

        # Check if salary was already credited this month on or before anchor date
        salary_already_received = any(
            r["type"] == "credit" and
            r["date"].startswith(curr_month_prefix) and
            ("salary" in r["description"].lower() or r["amount"] >= salary_amt * 0.8)
            for r in records
        )

        if not salary_already_received and sal_day >= anchor_date.day:
            salary_to_add = salary_amt
            salary_credit_day = sal_day

    # Recurring commitments & reserved items
    commitments_data = get_fixed_commitments(user_id, persona)
    commitments_list = commitments_data.get("commitments", [])

    savings_amount = float(profile.get("monthly_savings_amount", 0.0) or 0.0)
    savings_day = int(profile.get("monthly_savings_day", num_days) or num_days)
    savings_day = max(1, min(num_days, savings_day))

    reserved_items = []
    for c in commitments_list:
        rep_day = int(c.get("day_of_month", 5))
        rep_day = max(1, min(num_days, rep_day))
        due_str = f"{year}-{month:02d}-{rep_day:02d}"

        # Only consider bills due from anchor_date onwards
        if rep_day >= anchor_date.day:
            # Check if already paid
            is_paid = any(
                r["type"] == "debit" and
                r["date"].startswith(curr_month_prefix) and
                abs(r["amount"] - c["amount"]) <= max(200.0, c["amount"] * 0.25)
                for r in records
            )
            if not is_paid:
                reserved_items.append({
                    "name": c["name"],
                    "category": c["category"],
                    "amount": float(c["amount"]),
                    "due_day": rep_day,
                    "due_date": due_str
                })

    if savings_amount > 0 and savings_day >= anchor_date.day:
        reserved_items.append({
            "name": "Monthly Savings Transfer",
            "category": "Savings",
            "amount": savings_amount,
            "due_day": savings_day,
            "due_date": f"{year}-{month:02d}-{savings_day:02d}"
        })

    # What-if scenario parameters
    stype = scenario.get("type", "purchase")
    samount = float(scenario.get("amount", 0.0))
    sdate_str = scenario.get("date", anchor_date.strftime("%Y-%m-%d"))
    try:
        scenario_dt = datetime.strptime(sdate_str, "%Y-%m-%d").date()
        sday = scenario_dt.day if (scenario_dt.year == year and scenario_dt.month == month) else anchor_date.day
    except Exception:
        sday = anchor_date.day

    cancel_sub_name = scenario.get("name", "").lower() if stype == "cancel_subscription" else None

    # Day-by-day simulation from anchor_date.day to num_days
    sim_days = list(range(anchor_date.day, num_days + 1))
    date_labels = [f"{year}-{month:02d}-{d:02d}" for d in sim_days]

    bal_before = current_balance
    bal_after = current_balance

    daily_before = []
    daily_after = []

    # Bill tracking on due date
    bill_status_before = {}
    bill_status_after = {}

    for d in sim_days:
        cur_date_str = f"{year}-{month:02d}-{d:02d}"

        # Inflows (Salary if due today)
        inflow_day = salary_to_add if (d == salary_credit_day) else 0.0
        bal_before += inflow_day
        bal_after += inflow_day

        # Income change scenario
        if stype == "income_change" and d == sday:
            bal_after += samount

        # Outflows from reserved bills due today
        bills_due_today = [b for b in reserved_items if b["due_day"] == d]
        for b in bills_due_today:
            # Before status
            rem_before = bal_before - b["amount"]
            if rem_before >= buffer_val:
                bill_status_before[b["due_date"]] = "Covered"
            elif rem_before >= 0:
                bill_status_before[b["due_date"]] = "Tight"
            else:
                bill_status_before[b["due_date"]] = "Short"
            bal_before -= b["amount"]

            # After status (account for cancel_subscription)
            if cancel_sub_name and cancel_sub_name in b["name"].lower():
                # cancelled subscription is NOT deducted in 'after'
                rem_after = bal_after
            else:
                rem_after = bal_after - b["amount"]
                bal_after -= b["amount"]

            if rem_after >= buffer_val:
                bill_status_after[b["due_date"]] = "Covered"
            elif rem_after >= 0:
                bill_status_after[b["due_date"]] = "Tight"
            else:
                bill_status_after[b["due_date"]] = "Short"

        # Outflows from one-time what-if (purchase, loan_emi, prepay_loan)
        if d == sday:
            if stype in ["purchase", "loan_emi", "prepay_loan"]:
                bal_after -= samount

        daily_before.append(round(bal_before, 2))
        daily_after.append(round(bal_after, 2))

    lowest_before = min(daily_before) if daily_before else current_balance
    lowest_after = min(daily_after) if daily_after else current_balance
    month_end_before = daily_before[-1] if daily_before else current_balance
    month_end_after = daily_after[-1] if daily_after else current_balance

    # Per-bill status results
    obligations_result = []
    for b in reserved_items:
        s_b = bill_status_before.get(b["due_date"], "Covered")
        s_a = bill_status_after.get(b["due_date"], "Covered")
        obligations_result.append({
            "name": b["name"],
            "due_date": b["due_date"],
            "amount": b["amount"],
            "status_before": s_b,
            "status_after": s_a,
            "status": s_a
        })

    # Verdict: Safe (lowest >= buffer), Risky (0 <= lowest < buffer), Not advisable (lowest < 0)
    if lowest_after >= buffer_val:
        verdict = "Safe"
    elif 0 <= lowest_after < buffer_val:
        verdict = "Risky"
    else:
        verdict = "Not advisable"

    # Prepay loan calculations if applicable
    prepay_details = None
    if stype == "prepay_loan":
        rate = float(scenario.get("interest_rate", 9.0))
        emi_amt = 15000.0
        for ob in commitments_list:
            if "emi" in ob["name"].lower() or "loan" in ob["name"].lower():
                emi_amt = float(ob["amount"])
                break
        prepay_details = calculate_prepay_loan_savings(
            amount=samount,
            annual_rate=rate,
            current_emi=emi_amt
        )

    return {
        "verdict": verdict,
        "lowest_balance_before": round(lowest_before, 2),
        "lowest_balance_after": round(lowest_after, 2),
        "month_end_balance_before": round(month_end_before, 2),
        "month_end_balance_after": round(month_end_after, 2),
        "obligations": obligations_result,
        "obligations_status": obligations_result,
        "buffer": round(buffer_val, 2),
        "prepay_details": prepay_details,
        "dates": date_labels,
        "daily_balance_before": daily_before,
        "daily_balance_after": daily_after
    }
