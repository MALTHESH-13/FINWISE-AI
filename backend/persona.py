import os
import json
import csv
import re
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from backend.categorizer import clean_description, categorize_transaction

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_DIR = os.path.join(DATA_DIR, "users")

DEFAULT_LIMITS = {
    "Housing": 35000.0,
    "Loan/EMI": 15000.0,
    "Phone/Data": 2500.0,
    "Utilities": 5000.0,
    "Insurance": 3500.0,
    "Subscriptions": 2000.0,
    "Health/Fitness": 3000.0,
    "Transport": 4000.0,
    "Groceries": 10000.0,
    "Food": 8000.0,
    "Entertainment": 3000.0,
    "Shopping": 5000.0,
    "Other": 4000.0
}

def get_user_dir(user_id: int) -> str:
    path = os.path.join(USERS_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path

def get_active_persona(user_id: int) -> str:
    user_dir = get_user_dir(user_id)
    persona_file = os.path.join(user_dir, "active_persona.json")
    if os.path.exists(persona_file):
        try:
            with open(persona_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("active_persona", "salaried")
        except Exception:
            pass
    return "salaried"

def set_active_persona(user_id: int, persona: str) -> str:
    p = persona.strip().lower()
    if p not in ["salaried", "business"]:
        p = "salaried"
    user_dir = get_user_dir(user_id)
    persona_file = os.path.join(user_dir, "active_persona.json")
    with open(persona_file, "w", encoding="utf-8") as f:
        json.dump({"active_persona": p}, f)
    # Ensure persona directory exists
    os.makedirs(os.path.join(user_dir, p), exist_ok=True)
    return p

def get_persona_dir(user_id: int, persona: Optional[str] = None) -> str:
    if not persona:
        persona = get_active_persona(user_id)
    p_dir = os.path.join(get_user_dir(user_id), persona)
    os.makedirs(p_dir, exist_ok=True)
    return p_dir

def get_profile_path(user_id: int, persona: Optional[str] = None) -> str:
    return os.path.join(get_persona_dir(user_id, persona), "profile.json")

def get_transactions_path(user_id: int, persona: Optional[str] = None) -> str:
    return os.path.join(get_persona_dir(user_id, persona), "transactions.csv")

def get_limits_path(user_id: int, persona: Optional[str] = None) -> str:
    return os.path.join(get_persona_dir(user_id, persona), "limits.json")

def load_user_transactions_persona(user_id: int, persona: Optional[str] = None) -> List[Dict[str, Any]]:
    csv_path = get_transactions_path(user_id, persona)
    if not os.path.exists(csv_path):
        return []
    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                date_str = row.get("date", "").strip()
                desc = row.get("description", "").strip()
                amt = float(row.get("amount", 0.0))
                ttype = row.get("type", "debit").strip().lower()
                cleaned = row.get("cleaned_merchant") or clean_description(desc)
                cat = row.get("category") or categorize_transaction(desc, cleaned, amt, ttype)
                records.append({
                    "date": date_str,
                    "description": desc,
                    "cleaned_merchant": cleaned,
                    "category": cat,
                    "amount": amt,
                    "type": ttype
                })
            except Exception:
                continue
    return sorted(records, key=lambda x: x["date"])

def get_profile_data(user_id: int, persona: Optional[str] = None) -> Dict[str, Any]:
    if not persona:
        persona = get_active_persona(user_id)
    p_path = get_profile_path(user_id, persona)
    
    profile = {}
    is_setup = False
    if os.path.exists(p_path):
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
                is_setup = profile.get("is_setup", False)
        except Exception:
            profile = {}

    # Calculate baseline income and formula details
    calc_details = {}
    baseline = 0.0

    if persona == "salaried":
        salary = float(profile.get("salary", 0.0))
        sec_inc = float(profile.get("secondary_income_amount", 0.0))
        baseline = salary + sec_inc
        calc_details = {
            "formula": "Salary + Secondary Income",
            "inputs": {
                "salary": salary,
                "secondary_income": sec_inc,
                "secondary_label": profile.get("secondary_income_label", "None")
            },
            "value": baseline
        }
    else: # business
        buffer_val = float(profile.get("safety_buffer", 0.15))
        buffer_val = max(0.0, min(0.40, buffer_val))
        rev_history = profile.get("revenue_history", [])
        
        # Auto-fill from statement credits if revenue_history is empty
        if len(rev_history) < 3:
            txs = load_user_transactions_persona(user_id, persona)
            monthly_credits = {}
            for t in txs:
                if t["type"] == "credit" and len(t["date"]) >= 7:
                    m = t["date"][:7]
                    monthly_credits[m] = monthly_credits.get(m, 0.0) + t["amount"]
            if monthly_credits:
                rev_history = [{"month": k, "amount": round(v, 2)} for k, v in sorted(monthly_credits.items())]
                profile["revenue_history"] = rev_history

        # Use last 3-12 months, specifically rolling mean of last 3 months
        if rev_history:
            sorted_rev = sorted(rev_history, key=lambda x: x["month"])
            # take last 3 months if available
            last_3 = sorted_rev[-3:] if len(sorted_rev) >= 3 else sorted_rev
            mean_rev = sum(r["amount"] for r in last_3) / len(last_3)
            baseline = round(mean_rev * (1.0 - buffer_val), 2)
            calc_details = {
                "formula": "Rolling mean of last 3 months revenue × (1 - safety buffer)",
                "inputs": {
                    "months": [f"{r['month']}: ₹{int(r['amount']):,}" for r in last_3],
                    "rolling_mean": round(mean_rev, 2),
                    "safety_buffer_pct": round(buffer_val * 100, 1),
                    "safety_buffer": buffer_val
                },
                "value": baseline
            }
        else:
            baseline = 0.0
            calc_details = {
                "formula": "Rolling mean of last 3 months revenue × (1 - safety buffer)",
                "inputs": {
                    "months": [],
                    "rolling_mean": 0.0,
                    "safety_buffer_pct": round(buffer_val * 100, 1),
                    "safety_buffer": buffer_val
                },
                "value": 0.0
            }

    return {
        "persona": persona,
        "is_setup": is_setup,
        "profile": profile,
        "baseline_income": baseline,
        "calculation_details": calc_details
    }

def save_profile_data(user_id: int, persona: str, data: Dict[str, Any]) -> Dict[str, Any]:
    persona = set_active_persona(user_id, persona)
    p_path = get_profile_path(user_id, persona)
    data["is_setup"] = True
    with open(p_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return get_profile_data(user_id, persona)

def get_user_limits(user_id: int, persona: Optional[str] = None) -> Dict[str, float]:
    from backend.budget import calculate_actuals_based_limits
    records = load_user_transactions_persona(user_id, persona)
    limits = calculate_actuals_based_limits(records)

    l_path = get_limits_path(user_id, persona)
    if os.path.exists(l_path):
        try:
            with open(l_path, "r", encoding="utf-8") as f:
                user_lims = json.load(f)
                limits.update({k: float(v) for k, v in user_lims.items()})
        except Exception:
            pass
    return limits

def save_user_limits(user_id: int, persona: str, new_limits: Dict[str, float]) -> Dict[str, float]:
    l_path = get_limits_path(user_id, persona)
    curr = get_user_limits(user_id, persona)
    curr.update({k: float(v) for k, v in new_limits.items() if float(v) > 0})
    with open(l_path, "w", encoding="utf-8") as f:
        json.dump(curr, f, indent=2)
    return curr

def parse_and_ingest_csv(user_id: int, persona: str, file_contents: bytes) -> Dict[str, Any]:
    """
    Drag-and-drop CSV upload that auto-parses flexible columns:
    date/description/amount or debit/credit. Bad rows skipped with warning.
    Cleans merchant names, categorizes, and saves.
    """
    text = file_contents.decode("utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {"status": "error", "message": "Empty file"}

    reader = csv.reader(lines)
    header = [h.strip().lower() for h in next(reader, [])]

    # Flexible column resolution
    date_col = -1
    desc_col = -1
    amount_col = -1
    debit_col = -1
    credit_col = -1
    type_col = -1

    for idx, col in enumerate(header):
        c = col.lower().replace("_", " ").replace("-", " ")
        if any(k in c for k in ["txn date", "trans date", "date", "value date"]):
            if date_col == -1: date_col = idx
        elif any(k in c for k in ["narration", "description", "particulars", "merchant", "details", "remarks"]):
            if desc_col == -1: desc_col = idx
        elif c in ["amount", "txn amount", "inr"]:
            if amount_col == -1: amount_col = idx
        elif any(k in c for k in ["debit", "withdrawal", "dr"]):
            if debit_col == -1: debit_col = idx
        elif any(k in c for k in ["credit", "deposit", "cr"]):
            if credit_col == -1: credit_col = idx
        elif any(k in c for k in ["type", "cr/dr", "transaction type"]):
            if type_col == -1: type_col = idx

    if date_col == -1 or desc_col == -1 or (amount_col == -1 and debit_col == -1 and credit_col == -1):
        # Fallback to positional: Date(0), Desc(1), Amount(2), Type(3)
        date_col = 0
        desc_col = 1
        amount_col = 2
        type_col = 3 if len(header) > 3 else -1

    parsed_records = []
    warnings = []

    date_patterns = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %B %Y"
    ]

    for line_num, row in enumerate(reader, start=2):
        if not row or not any(row):
            continue
        try:
            # 1. Parse Date
            raw_date = row[date_col].strip() if date_col < len(row) else ""
            parsed_date = None
            for p in date_patterns:
                try:
                    parsed_date = datetime.strptime(raw_date, p).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if not parsed_date:
                warnings.append(f"Row {line_num}: invalid date format '{raw_date}' skipped")
                continue

            # 2. Parse Description
            raw_desc = row[desc_col].strip() if desc_col < len(row) else "Unknown"

            # 3. Parse Amount and Type
            amt = 0.0
            tx_type = "debit"

            if debit_col != -1 or credit_col != -1:
                deb_str = row[debit_col].strip().replace(",", "") if debit_col != -1 and debit_col < len(row) else ""
                cred_str = row[credit_col].strip().replace(",", "") if credit_col != -1 and credit_col < len(row) else ""
                deb_val = float(deb_str) if deb_str and deb_str != "-" else 0.0
                cred_val = float(cred_str) if cred_str and cred_str != "-" else 0.0

                if cred_val > 0:
                    amt = cred_val
                    tx_type = "credit"
                else:
                    amt = deb_val
                    tx_type = "debit"
            else:
                amt_str = row[amount_col].strip().replace(",", "").replace("₹", "").replace("Rs", "") if amount_col < len(row) else "0"
                raw_amt = float(amt_str)
                if raw_amt < 0:
                    amt = abs(raw_amt)
                    tx_type = "debit"
                else:
                    amt = raw_amt
                    if type_col != -1 and type_col < len(row):
                        t_val = row[type_col].strip().lower()
                        tx_type = "credit" if any(k in t_val for k in ["cr", "credit", "dep"]) else "debit"
                    else:
                        tx_type = "credit" if any(k in raw_desc.lower() for k in ["salary", "client", "credit", "inflow", "refund"]) else "debit"

            if amt <= 0:
                continue

            cleaned = clean_description(raw_desc)
            cat = categorize_transaction(raw_desc, cleaned, amt, tx_type)

            parsed_records.append({
                "date": parsed_date,
                "description": raw_desc,
                "cleaned_merchant": cleaned,
                "category": cat,
                "amount": round(amt, 2),
                "type": tx_type
            })

        except Exception as e:
            warnings.append(f"Row {line_num}: parsing error ({str(e)})")
            continue

    if not parsed_records:
        return {"status": "error", "message": "No valid transaction rows found in file", "warnings": warnings}

    parsed_records.sort(key=lambda x: x["date"])

    # Save to user's persona transactions.csv
    dest_path = get_transactions_path(user_id, persona)
    with open(dest_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["date", "description", "cleaned_merchant", "category", "amount", "type"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(parsed_records)

    # For Small Business, if revenue_history in profile is empty, auto-fill from monthly credits
    if persona == "business":
        prof = get_profile_data(user_id, persona)["profile"]
        monthly_credits = {}
        for t in parsed_records:
            if t["type"] == "credit" and len(t["date"]) >= 7:
                m = t["date"][:7]
                monthly_credits[m] = monthly_credits.get(m, 0.0) + t["amount"]
        if monthly_credits:
            prof["revenue_history"] = [{"month": k, "amount": round(v, 2)} for k, v in sorted(monthly_credits.items())]
            save_profile_data(user_id, persona, prof)

    return {
        "status": "ok",
        "count": len(parsed_records),
        "warnings": warnings[:10]  # truncate warnings if many
    }

def get_fixed_commitments(user_id: int, persona: Optional[str] = None) -> Dict[str, Any]:
    """
    Fixed Monthly Commitments: cards/table of detected recurring expenses
    with name, category, amount, next due date, days left, and monthly total.
    """
    records = load_user_transactions_persona(user_id, persona)
    if not records:
        return {"commitments": [], "monthly_total": 0.0, "has_data": False}

    anchor_date = datetime(2026, 11, 14)
    # Target recurring categories
    rec_cats = {"Housing", "Loan/EMI", "Utilities", "Subscriptions", "Phone/Data", "Insurance", "Health/Fitness"}

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        if r["type"] == "debit" and r["category"] in rec_cats:
            key = r["cleaned_merchant"]
            groups.setdefault(key, []).append(r)

    commitments = []
    total_monthly = 0.0

    for name, items in groups.items():
        avg_amt = sum(it["amount"] for it in items) / len(items)
        cat = items[-1]["category"]
        days = [int(it["date"].split("-")[2]) for it in items if len(it["date"].split("-")) == 3]
        rep_day = int(sum(days) / len(days)) if days else 15
        rep_day = max(1, min(28, rep_day))

        # Next due date relative to anchor_date
        y, m = anchor_date.year, anchor_date.month
        try:
            due_dt = datetime(y, m, rep_day)
            if due_dt < anchor_date:
                due_dt = datetime(y + 1, 1, rep_day) if m == 12 else datetime(y, m + 1, rep_day)
        except ValueError:
            due_dt = anchor_date + timedelta(days=10)

        days_left = max(0, (due_dt - anchor_date).days)
        commitments.append({
            "name": name,
            "category": cat,
            "amount": round(avg_amt, 2),
            "next_due_date": due_dt.strftime("%Y-%m-%d"),
            "days_left": days_left
        })
        total_monthly += avg_amt

    commitments.sort(key=lambda x: x["days_left"])
    return {
        "commitments": commitments,
        "monthly_total": round(total_monthly, 2),
        "has_data": len(commitments) > 0
    }

def get_mom_comparison(user_id: int, persona: Optional[str] = None) -> Dict[str, Any]:
    """
    Month-over-Month Category Comparison:
    Chart.js grouped bars (previous month vs current month per category)
    plus a line/marker for each category's personalized limit.
    Over-limit categories colored red with 'Over by ₹X (Y%)' label.
    """
    records = load_user_transactions_persona(user_id, persona)
    if not records:
        return {
            "categories": [],
            "previous_month_label": "Previous Month",
            "current_month_label": "Current Month",
            "previous_month_spending": [],
            "current_month_spending": [],
            "limits": [],
            "overspent": [],
            "has_data": False
        }

    # Find distinct months
    months = sorted(list(set(r["date"][:7] for r in records if len(r["date"]) >= 7)))
    if len(months) >= 2:
        curr_m = months[-1]
        prev_m = months[-2]
    elif len(months) == 1:
        curr_m = months[0]
        prev_m = "2026-10" if curr_m == "2026-11" else "2026-09"
    else:
        curr_m = "2026-11"
        prev_m = "2026-10"

    # Aggregations
    curr_spend: Dict[str, float] = {}
    prev_spend: Dict[str, float] = {}

    standard_cats = [
        "Housing", "Loan/EMI", "Utilities", "Phone/Data", "Subscriptions",
        "Food", "Groceries", "Shopping", "Transport", "Health/Fitness",
        "Insurance", "Entertainment", "Other"
    ]

    for r in records:
        if r["type"] == "debit":
            m = r["date"][:7]
            cat = r["category"]
            if m == curr_m:
                curr_spend[cat] = curr_spend.get(cat, 0.0) + r["amount"]
            elif m == prev_m:
                prev_spend[cat] = prev_spend.get(cat, 0.0) + r["amount"]

    # Active categories with spending in either month
    active_cats = [c for c in standard_cats if curr_spend.get(c, 0) > 0 or prev_spend.get(c, 0) > 0]
    if not active_cats:
        active_cats = standard_cats[:6]

    limits_map = get_user_limits(user_id, persona)

    prev_vals = []
    curr_vals = []
    limit_vals = []
    overspent_list = []

    for cat in active_cats:
        c_val = round(curr_spend.get(cat, 0.0), 2)
        p_val = round(prev_spend.get(cat, 0.0), 2)
        lim = limits_map.get(cat, DEFAULT_LIMITS.get(cat, 5000.0))

        prev_vals.append(p_val)
        curr_vals.append(c_val)
        limit_vals.append(lim)

        if c_val > lim:
            diff = c_val - lim
            pct = round((diff / lim) * 100, 1) if lim > 0 else 100.0
            overspent_list.append({
                "category": cat,
                "current_spent": c_val,
                "limit": lim,
                "over_amount": round(diff, 2),
                "over_pct": pct
            })

    def format_month_label(m_str: str) -> str:
        try:
            return datetime.strptime(m_str, "%Y-%m").strftime("%B %Y")
        except Exception:
            return m_str

    return {
        "categories": active_cats,
        "previous_month_label": format_month_label(prev_m),
        "current_month_label": format_month_label(curr_m),
        "previous_month_spending": prev_vals,
        "current_month_spending": curr_vals,
        "limits": limit_vals,
        "overspent": overspent_list,
        "has_data": len(records) > 0
    }

def check_business_income_dip(user_id: int) -> Dict[str, Any]:
    """
    BUSINESS INCOME-DIP PRIORITY ENGINE (Small Business only, critical):
    Trigger: projected current-month inflow < Baseline Stable Monthly Income,
             or actual inflow pace falls >10% below it.
    Generates ranked expense list:
      P1 Essential (pay first): Housing, Phone/Data, Loan/EMI, Utilities, Insurance.
      P2 Needed: Groceries, Transport/fuel, Health.
      P3 Cut/pause temporarily: Subscriptions, Gym/Fitness, Entertainment, Food delivery, Shopping.
    """
    prof_info = get_profile_data(user_id, "business")
    baseline = prof_info["baseline_income"]

    records = load_user_transactions_persona(user_id, "business")
    if not records or baseline <= 0:
        return {"triggered": False, "reason": "No data or baseline"}

    anchor_date = datetime(2026, 11, 15).date()
    elapsed_days = anchor_date.day
    days_in_month = 30
    curr_m_str = anchor_date.strftime("%Y-%m")

    # Month to date inflow
    mtd_inflows = [r["amount"] for r in records if r["type"] == "credit" and r["date"].startswith(curr_m_str)]
    actual_mtd = sum(mtd_inflows)
    projected_inflow = round(actual_mtd, 2)

    # Prorated baseline
    prorated_baseline = baseline * (elapsed_days / float(days_in_month))
    dip_threshold = prorated_baseline * 0.90

    # Check if closed month's inflow < baseline
    closed_month_dip = False
    monthly_inflows = {}
    for r in records:
        if r["type"] == "credit":
            m_k = r["date"][:7]
            if m_k < curr_m_str:
                monthly_inflows[m_k] = monthly_inflows.get(m_k, 0.0) + r["amount"]
    if any(tot < baseline for tot in monthly_inflows.values()):
        closed_month_dip = True

    triggered = False
    shortfall = 0.0
    if elapsed_days >= 10 and actual_mtd < dip_threshold:
        triggered = True
        shortfall = round(prorated_baseline - actual_mtd, 2)
    elif closed_month_dip:
        triggered = True
        shortfall = round(max(0.0, baseline - actual_mtd), 2)

    if not triggered:
        return {
            "triggered": False,
            "message": "Income on track",
            "baseline": baseline,
            "projected_inflow": projected_inflow
        }

    # Gather category spending in recent month
    mom = get_mom_comparison(user_id, "business")
    recent_spend: Dict[str, float] = {}
    for cat, amt in zip(mom["categories"], mom["current_month_spending"]):
        recent_spend[cat] = amt

    # Commitments
    comm_info = get_fixed_commitments(user_id, "business")
    commitments = comm_info.get("commitments", [])

    # Group into P1, P2, P3
    p1_cats = ["Housing", "Phone/Data", "Loan/EMI", "Utilities", "Insurance"]
    p2_cats = ["Groceries", "Transport", "Health/Fitness"]
    p3_cats = ["Subscriptions", "Food", "Shopping", "Entertainment"]

    p1_items = []
    p1_total = 0.0
    for c in commitments:
        if c["category"] in p1_cats:
            p1_items.append({"name": c["name"], "category": c["category"], "amount": c["amount"]})
            p1_total += c["amount"]
    for cat in p1_cats:
        if not any(i["category"] == cat for i in p1_items) and recent_spend.get(cat, 0) > 0:
            val = recent_spend[cat]
            p1_items.append({"name": f"{cat} Monthly", "category": cat, "amount": val})
            p1_total += val

    p2_items = []
    p2_total = 0.0
    for cat in p2_cats:
        val = recent_spend.get(cat, 0.0)
        if val > 0:
            p2_items.append({"name": cat, "category": cat, "amount": val})
            p2_total += val

    # P3 Candidates for temporary cuts
    p3_candidates = []
    for c in commitments:
        if c["category"] in ["Subscriptions", "Health/Fitness"]:
            p3_candidates.append({
                "item": c["name"],
                "category": c["category"],
                "current_cost": c["amount"],
                "savings": c["amount"]
            })

    # Also add discretionary spending items from recent transactions
    for cat in ["Food", "Shopping", "Entertainment"]:
        val = recent_spend.get(cat, 0.0)
        if val > 0:
            p3_candidates.append({
                "item": f"{cat} Discretionary",
                "category": cat,
                "current_cost": val,
                "savings": val
            })

    # Progressively suggest cuts to cover shortfall
    suggested_cuts = []
    accumulated_savings = 0.0
    for p3 in p3_candidates:
        suggested_cuts.append(p3)
        accumulated_savings += p3["savings"]
        if accumulated_savings >= shortfall:
            break

    essentials_covered = projected_inflow >= p1_total
    essentials_diff = round(projected_inflow - p1_total, 2)

    return {
        "triggered": True,
        "shortfall": shortfall,
        "baseline": baseline,
        "projected_inflow": projected_inflow,
        "actual_mtd_inflow": round(actual_mtd, 2),
        "p1_total": round(p1_total, 2),
        "p2_total": round(p2_total, 2),
        "p1_items": p1_items,
        "p2_items": p2_items,
        "p3_suggested_cuts": suggested_cuts,
        "cuts": {
            "P1_essential": p1_items,
            "P2_needed": p2_items,
            "P3_discretionary": suggested_cuts
        },
        "total_p3_savings": round(accumulated_savings, 2),
        "essentials_covered": essentials_covered,
        "essentials_diff": essentials_diff
    }

def plan_investment_goal(user_id: int, name: str, cost: float, months: int,
                         current_savings: float = 0.0,
                         custom_return: Optional[float] = None) -> Dict[str, Any]:
    """
    POST /api/goals/plan returns roadmap:
    1. Required monthly saving = (cost - current_savings) / months;
       Compare to user average monthly surplus (baseline - avg expenses) -> feasible / stretch / not feasible.
    2. Horizon rule: < 12m -> RD/liquid (6.5%), 12-36m -> debt/hybrid SIP (9%), > 36m -> equity SIP (12%).
       Compute SIP needed with future-value formula.
    3. Budgeting steps: discretionary categories to trim with exact ₹ amounts.
    4. Month-by-month milestone table.
    """
    persona = get_active_persona(user_id)
    prof_info = get_profile_data(user_id, persona)
    baseline = prof_info["baseline_income"]

    # Calculate average monthly expenses
    records = load_user_transactions_persona(user_id, persona)
    months_set = sorted(list(set(r["date"][:7] for r in records if len(r["date"]) >= 7)))
    total_debits = sum(r["amount"] for r in records if r["type"] == "debit")
    num_months = max(1, len(months_set))
    avg_expenses = total_debits / num_months if records else 35000.0
    avg_surplus = max(0.0, baseline - avg_expenses)

    months = max(1, int(months))
    cost = max(100.0, float(cost))
    current_savings = max(0.0, float(current_savings))

    needed_principal = max(0.0, cost - current_savings)
    required_monthly_saving = round(needed_principal / months, 2)

    # Feasibility check
    if avg_surplus >= required_monthly_saving:
        feasibility = "feasible"
        feasibility_desc = f"Feasible. Your average monthly surplus of ₹{int(avg_surplus):,} fully covers the required ₹{int(required_monthly_saving):,}/month."
    elif avg_surplus * 1.35 >= required_monthly_saving:
        feasibility = "stretch"
        feasibility_desc = f"Stretch goal. Your surplus of ₹{int(avg_surplus):,} leaves a ₹{int(required_monthly_saving - avg_surplus):,}/mo gap, achievable with targeted cuts."
    else:
        feasibility = "not feasible"
        feasibility_desc = f"Not feasible without major restructuring. Required ₹{int(required_monthly_saving):,}/mo exceeds current monthly surplus (₹{int(avg_surplus):,})."

    # Horizon rule
    if months < 12:
        instrument = "Recurring Deposit / Liquid Fund"
        annual_rate = custom_return if custom_return is not None else 6.5
    elif months <= 36:
        instrument = "Debt / Hybrid SIP"
        annual_rate = custom_return if custom_return is not None else 9.0
    else:
        instrument = "Equity Index SIP"
        annual_rate = custom_return if custom_return is not None else 12.0

    r = (annual_rate / 100.0) / 12.0
    # Future value of current savings: FV_curr = current_savings * (1 + r)^months
    fv_curr = current_savings * ((1.0 + r) ** months)
    target_needed = max(0.0, cost - fv_curr)

    # P * [((1+r)^months - 1) / r] * (1+r) = target_needed
    if r > 0 and months > 0:
        factor = (((1.0 + r) ** months - 1.0) / r) * (1.0 + r)
        sip_amount = round(target_needed / factor, 2)
    else:
        sip_amount = required_monthly_saving

    # Budgeting steps from user's actual spending
    mom = get_mom_comparison(user_id, persona)
    trim_steps = []
    gap = max(0.0, required_monthly_saving - avg_surplus)
    discretionary_order = ["Shopping", "Entertainment", "Food", "Subscriptions"]

    curr_cats = dict(zip(mom["categories"], mom["current_month_spending"]))
    for d_cat in discretionary_order:
        spent = curr_cats.get(d_cat, 0.0)
        if spent > 1500:
            suggested_cut = round(min(spent * 0.45, max(1000.0, gap)), 2)
            trim_steps.append({
                "category": d_cat,
                "current_spent": spent,
                "suggested_cut": suggested_cut,
                "new_target": round(spent - suggested_cut, 2),
                "action": f"Trim {d_cat} from ₹{int(spent):,} to ₹{int(spent - suggested_cut):,}, saving ₹{int(suggested_cut):,}/mo."
            })
            gap -= suggested_cut
            if gap <= 0:
                break

    # Alternate timeline if they cannot cut
    if avg_surplus > 500:
        alt_months = math.ceil(needed_principal / avg_surplus)
    else:
        alt_months = months * 2

    # Milestone table
    milestones = []
    balance = current_savings
    for m in range(1, months + 1):
        interest = round(balance * r, 2)
        balance += sip_amount + interest
        milestones.append({
            "month": m,
            "monthly_deposit": sip_amount,
            "projected_returns": interest,
            "target_balance": round(balance, 2)
        })

    return {
        "goal_name": name,
        "target_cost": cost,
        "timeline_months": months,
        "current_savings": current_savings,
        "required_monthly_saving": required_monthly_saving,
        "average_monthly_surplus": round(avg_surplus, 2),
        "feasibility": feasibility,
        "feasibility_description": feasibility_desc,
        "recommended_instrument": instrument,
        "assumed_annual_rate": annual_rate,
        "sip_amount": sip_amount,
        "disclaimer": "Illustrative, not financial advice",
        "budgeting_steps": trim_steps,
        "alternative_timeline_months": alt_months,
        "milestones": milestones
    }

def get_anomalies(user_id: int, persona: Optional[str] = None) -> List[Dict[str, Any]]:
    records = load_user_transactions_persona(user_id, persona)
    if not records:
        return []
    debits = [r["amount"] for r in records if r["type"] == "debit"]
    if len(debits) < 5:
        return []
    mean_d = sum(debits) / len(debits)
    variance = sum((d - mean_d) ** 2 for d in debits) / len(debits)
    std_d = math.sqrt(variance)
    threshold = mean_d + (2.2 * std_d)

    anomalies = []
    for r in records:
        if r["type"] == "debit" and r["amount"] > threshold:
            anomalies.append({
                "date": r["date"],
                "merchant": r["cleaned_merchant"],
                "category": r["category"],
                "amount": r["amount"],
                "threshold": round(threshold, 2),
                "severity": "High" if r["amount"] > (mean_d + 3.0 * std_d) else "Medium"
            })
    return sorted(anomalies, key=lambda x: x["amount"], reverse=True)
