import os
import calendar
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from backend.categorizer import clean_description
from backend.persona import (
    load_user_transactions_persona,
    get_fixed_commitments,
    get_profile_data,
    get_anomalies
)

def get_calendar_data(user_id: int, persona: str, month_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Builds Samsung-Calendar-style month grid data and summary KPIs.
    GET /api/calendar?month=YYYY-MM ->
    {
      days: [{date, spend[], income[], reserved[{name,category,amount,kind,status}], totals}],
      summary: {income, spent, reserved_remaining, left_to_spend, balance, buffer}
    }
    """
    # Load all user transactions for active persona
    all_records = load_user_transactions_persona(user_id, persona)
    record_months = sorted(list(set(r["date"][:7] for r in all_records if len(r.get("date", "")) >= 7)))

    # Default to latest month with records if available, otherwise current month (2026-11)
    if not month_str:
        if record_months:
            month_str = record_months[-1]
        else:
            month_str = "2026-11"

    try:
        parts = month_str.split("-")
        year = int(parts[0])
        month = int(parts[1])
    except Exception:
        year = 2026
        month = 11
        month_str = "2026-11"

    num_days = calendar.monthrange(year, month)[1]

    # Filter transactions for requested month
    month_records = [r for r in all_records if r["date"].startswith(month_str)]

    # Get anomalies for active persona
    anomalies = get_anomalies(user_id, persona)
    anomaly_dates = {a["date"] for a in anomalies}
    anomaly_descriptions = {(a["date"], a["merchant"], a["amount"]) for a in anomalies}

    # Fixed recurring commitments
    commitments_data = get_fixed_commitments(user_id, persona)
    commitments_list = commitments_data.get("commitments", [])

    # Profile data for savings transfer and safety buffer
    profile_info = get_profile_data(user_id, persona)
    profile = profile_info.get("profile", {})
    savings_amount = float(profile.get("monthly_savings_amount", 0.0) or 0.0)
    savings_day = int(profile.get("monthly_savings_day", num_days) or num_days)
    savings_day = max(1, min(num_days, savings_day))

    buffer_val = float(profile.get("safety_buffer", 0.15) * profile_info.get("baseline_income", 60000.0))
    if buffer_val <= 0:
        buffer_val = 10000.0

    # Build reserved items for the month
    # Each item: {name, category, amount, day, kind}
    month_reserved_items = []
    for c in commitments_list:
        rep_day = int(c.get("day_of_month", 5))
        rep_day = max(1, min(num_days, rep_day))
        month_reserved_items.append({
            "name": c["name"],
            "category": c["category"],
            "amount": float(c["amount"]),
            "day": rep_day,
            "kind": "recurring"
        })

    if savings_amount > 0:
        month_reserved_items.append({
            "name": "Monthly Savings Transfer",
            "category": "Savings",
            "amount": savings_amount,
            "day": savings_day,
            "kind": "savings"
        })

    # Determine status (Paid vs Reserved) for each reserved item
    # "If a matching transaction exists on/after the due date within 3 days, show it as 'Paid' instead of Reserved."
    reserved_by_day = defaultdict(list)
    for res_item in month_reserved_items:
        r_day = res_item["day"]
        r_amt = res_item["amount"]
        r_cat = res_item["category"].lower()
        r_name = res_item["name"].lower()

        # Check transactions from day r_day to r_day + 3
        is_paid = False
        for offset in range(0, 4):
            check_d = r_day + offset
            if check_d <= num_days:
                check_date_str = f"{year}-{month:02d}-{check_d:02d}"
                for tr in month_records:
                    if tr["date"] == check_date_str and tr["type"] == "debit":
                        t_amt = tr["amount"]
                        t_desc = tr["description"].lower()
                        t_cat = tr["category"].lower()
                        # Match by amount closeness (within 25%) and category or description keyword
                        if abs(t_amt - r_amt) <= max(200.0, r_amt * 0.25):
                            if (t_cat == r_cat or 
                                any(w in t_desc for w in r_name.split() if len(w) > 3) or 
                                r_cat in t_desc):
                                is_paid = True
                                break
            if is_paid:
                break

        res_entry = {
            "name": res_item["name"],
            "category": res_item["category"],
            "amount": round(res_item["amount"], 2),
            "kind": res_item["kind"],
            "status": "Paid" if is_paid else "Reserved"
        }
        reserved_by_day[r_day].append(res_entry)

    # Build day-by-day array
    days_data = []
    month_income_total = 0.0
    month_spent_total = 0.0
    reserved_remaining_total = 0.0

    today_date = date.today()
    if today_date.year == 2026 and today_date.month == 11:
        current_day_marker = today_date.day
    else:
        current_day_marker = 15  # Default current marker for sample data

    for d in range(1, num_days + 1):
        d_str = f"{year}-{month:02d}-{d:02d}"

        # Get day transactions
        d_txs = [r for r in month_records if r["date"] == d_str]
        spend_items = []
        income_items = []

        day_spent = 0.0
        day_income = 0.0

        for r in d_txs:
            merchant = r.get("cleaned_merchant") or clean_description(r["description"])
            is_anom = (d_str in anomaly_dates) and (r["amount"] > 10000.0 or any(a["merchant"].lower() in merchant.lower() for a in anomalies if a["date"] == d_str))
            
            if r["type"] == "debit":
                spend_items.append({
                    "merchant": merchant,
                    "category": r["category"],
                    "amount": round(r["amount"], 2),
                    "raw": r["description"],
                    "is_anomaly": is_anom
                })
                day_spent += r["amount"]
            else:
                income_items.append({
                    "merchant": merchant,
                    "category": "Income",
                    "amount": round(r["amount"], 2),
                    "raw": r["description"]
                })
                day_income += r["amount"]

        day_reserved = reserved_by_day.get(d, [])
        day_reserved_unpaid = sum(ri["amount"] for ri in day_reserved if ri["status"] == "Reserved")

        # In current month, reserved remaining is the sum of items not yet paid
        if month_str < "2026-11":
            day_remaining = 0.0
        elif month_str == "2026-11":
            day_remaining = day_reserved_unpaid if d >= current_day_marker else 0.0
        else:
            day_remaining = day_reserved_unpaid

        reserved_remaining_total += day_remaining

        month_income_total += day_income
        month_spent_total += day_spent

        days_data.append({
            "date": d_str,
            "day": d,
            "spend": spend_items,
            "income": income_items,
            "reserved": day_reserved,
            "totals": {
                "spent": round(day_spent, 2),
                "income": round(day_income, 2),
                "reserved": round(day_reserved_unpaid, 2)
            },
            "has_anomaly": any(s["is_anomaly"] for s in spend_items)
        })

    # Overall ledger balance
    total_credits = sum(r["amount"] for r in all_records if r["type"] == "credit")
    total_debits = sum(r["amount"] for r in all_records if r["type"] == "debit")

    baseline_income = float(profile_info.get("baseline_income", 0.0) or 0.0)
    starting_balance = float(profile.get("starting_balance", 0.0) or 0.0)
    statement_balance = float(profile.get("statement_balance", 0.0) or 0.0)

    # Determine accurate ledger balance:
    # 1. If statement has a known closing balance from bank statement, use it
    # 2. If user set an initial/starting bank balance, use starting_balance + credits - debits
    # 3. If CSV has credits, use total_credits - total_debits
    # 4. If CSV only has debits (e.g. expenses-only statement) and 0 credits, baseline monthly income covers debits
    if statement_balance > 0:
        current_balance = statement_balance
    elif starting_balance > 0:
        current_balance = starting_balance + total_credits - total_debits
    elif total_credits > 0:
        current_balance = total_credits - total_debits
    elif total_debits > 0 and baseline_income > 0:
        debit_months = len(set(r["date"][:7] for r in all_records if len(r["date"]) >= 7)) or 1
        effective_credits = max(baseline_income * debit_months, total_debits + buffer_val)
        current_balance = effective_credits - total_debits
    else:
        current_balance = total_credits - total_debits

    # If active month has debits but 0 credits in CSV and total_credits == 0, show baseline income for the month
    if month_income_total == 0 and month_spent_total > 0 and baseline_income > 0 and total_credits == 0:
        month_income_total = baseline_income

    left_to_spend = current_balance - reserved_remaining_total - buffer_val

    return {
        "month": month_str,
        "available_months": record_months,
        "days": days_data,
        "summary": {
            "income": round(month_income_total, 2),
            "spent": round(month_spent_total, 2),
            "reserved_remaining": round(reserved_remaining_total, 2),
            "left_to_spend": round(left_to_spend, 2),
            "balance": round(current_balance, 2),
            "buffer": round(buffer_val, 2)
        }
    }
