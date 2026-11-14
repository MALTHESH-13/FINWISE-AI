import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import defaultdict

DEFAULT_LIMITS: Dict[str, float] = {
    "Food": 8000.0,
    "Groceries": 10000.0,
    "Shopping": 6000.0,
    "Housing": 25000.0,
    "Subscriptions": 1500.0,
    "Utilities": 3500.0,
    "Phone/Data": 1200.0,
    "Transport": 4000.0,
    "Health/Fitness": 3000.0,
    "Insurance": 3500.0,
    "Loan/EMI": 15000.0,
    "Entertainment": 3000.0,
    "Other": 4000.0
}

DISCRETIONARY_CATEGORIES = {"Food", "Shopping", "Entertainment", "Subscriptions"}
FIXED_CATEGORIES = {"Housing", "Loan/EMI", "Utilities", "Insurance", "Phone/Data"}

def calculate_actuals_based_limits(records: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Computes limits from actual transactions:
    - per-category limit = average of the last 3 full months of actual spend
    - discretionary categories (Food, Shopping, Entertainment, Subscriptions) x 0.90
    - fixed categories (Housing, Loan/EMI, Utilities, Insurance, Phone/Data) = latest actual
    """
    if not records:
        return dict(DEFAULT_LIMITS)

    # Group debit transactions by month and category
    # monthly_spending: { 'YYYY-MM': { 'Category': total_amount } }
    monthly_spending: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        if r.get("type") == "debit":
            date_str = r.get("date", "")
            if len(date_str) >= 7:
                month_key = date_str[:7]
                cat = r.get("category", "Other")
                monthly_spending[month_key][cat] += float(r.get("amount", 0.0))

    if not monthly_spending:
        return dict(DEFAULT_LIMITS)

    all_months = sorted(monthly_spending.keys())
    # If more than 1 month, exclude current (in-progress) month if possible for the 'full months'
    if len(all_months) > 1:
        past_months = all_months[:-1]
    else:
        past_months = all_months

    last_3_months = past_months[-3:] if len(past_months) >= 3 else past_months
    latest_month = all_months[-1]

    limits: Dict[str, float] = {}

    for cat in DEFAULT_LIMITS.keys():
        if cat in FIXED_CATEGORIES:
            # Fixed categories = latest actual monthly spend
            latest_val = 0.0
            # Look backwards from the latest month to find the latest actual spend
            for m in reversed(all_months):
                if cat in monthly_spending[m] and monthly_spending[m][cat] > 0:
                    latest_val = monthly_spending[m][cat]
                    break
            limits[cat] = round(latest_val if latest_val > 0 else DEFAULT_LIMITS[cat], 2)
        elif cat in DISCRETIONARY_CATEGORIES:
            # Discretionary = average of last 3 full months * 0.90
            vals = [monthly_spending[m].get(cat, 0.0) for m in last_3_months]
            avg_val = (sum(vals) / len(vals)) if vals else DEFAULT_LIMITS[cat]
            if avg_val > 0:
                limits[cat] = round(avg_val * 0.90, 2)
            else:
                limits[cat] = round(DEFAULT_LIMITS[cat] * 0.90, 2)
        else:
            # Other categories = average of last 3 full months
            vals = [monthly_spending[m].get(cat, 0.0) for m in last_3_months]
            avg_val = (sum(vals) / len(vals)) if vals else DEFAULT_LIMITS[cat]
            limits[cat] = round(avg_val if avg_val > 0 else DEFAULT_LIMITS[cat], 2)

    return limits
