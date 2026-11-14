import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from backend.simulator import simulate_scenario
from backend.explain import explain_simulation, explain_left_to_spend, format_inr
from backend.calendar_service import get_calendar_data
from backend.persona import (
    get_active_persona,
    get_profile_data,
    plan_investment_goal,
    check_business_income_dip,
    load_user_transactions_persona,
    get_mom_comparison,
    get_fixed_commitments,
    get_user_limits
)

def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key.strip()
    key_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".gemini_key")
    if os.path.exists(key_file):
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

def call_gemini_api(prompt: str, context_info: str) -> Optional[str]:
    """
    Call Gemini Generative Language API with user financial context.
    Falls back gracefully if network is unavailable or times out.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        system_instruction = (
            "You are FinWise AI / CashPilot, an intelligent, empathetic financial advisor and cashflow copilot. "
            "You advise users based strictly on their actual bank statement numbers, commitments, and limits. "
            "Always use Indian Rupee (₹) format and Indian numbering (lakhs). Keep answers practical, specific, and concise (under 4-5 sentences). "
            "Do not hallucinate imaginary numbers or mention internal simulation formulas. "
            f"\n\nUser Financial Context:\n{context_info}"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"Context: {context_info}\n\nQuestion: {prompt}"}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 300
            }
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                res_body = json.loads(resp.read().decode("utf-8"))
                candidates = res_body.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "").strip()
                        if text:
                            return text
    except Exception:
        pass
    return None


def parse_amount(text: str) -> Optional[float]:
    t = text.lower()
    lakh_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lakhs|lac|lacs)\b', t)
    if lakh_match:
        return float(lakh_match.group(1)) * 100_000.0

    k_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*k\b', t)
    if k_match:
        return float(k_match.group(1)) * 1_000.0

    inr_match = re.search(r'(?:[₹]|rs\.?|inr)?\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]{3,8}(?:\.[0-9]+)?)', t)
    if inr_match:
        num_str = inr_match.group(1).replace(',', '')
        try:
            val = float(num_str)
            if val > 0:
                return val
        except ValueError:
            pass

    return None

def parse_date(text: str, anchor_date: Optional[datetime] = None) -> str:
    if anchor_date is None:
        anchor_date = datetime(2026, 11, 15)

    t = text.lower()
    if "today" in t:
        return anchor_date.strftime("%Y-%m-%d")
    if "tomorrow" in t:
        return (anchor_date + timedelta(days=1)).strftime("%Y-%m-%d")

    in_days = re.search(r'in\s+([0-9]+)\s+days?', t)
    if in_days:
        return (anchor_date + timedelta(days=int(in_days.group(1)))).strftime("%Y-%m-%d")

    in_weeks = re.search(r'in\s+([0-9]+)\s+weeks?', t)
    if in_weeks:
        return (anchor_date + timedelta(weeks=int(in_weeks.group(1)))).strftime("%Y-%m-%d")

    if "next week" in t:
        return (anchor_date + timedelta(days=7)).strftime("%Y-%m-%d")

    days_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    for day_name, target_weekday in days_map.items():
        if day_name in t:
            cur_weekday = anchor_date.weekday()
            diff = (target_weekday - cur_weekday) % 7
            if diff == 0:
                diff = 7 if "next" in t else 0
            elif "next" in t and diff < 7:
                diff += 7
            return (anchor_date + timedelta(days=diff)).strftime("%Y-%m-%d")

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }
    for m_str, m_num in month_map.items():
        m_match = re.search(rf'([0-9]{{1,2}})(?:st|nd|rd|th)?\s+{m_str}', t)
        if m_match:
            day_num = int(m_match.group(1))
            year = anchor_date.year if m_num >= anchor_date.month else anchor_date.year + 1
            return f"{year}-{m_num:02d}-{day_num:02d}"
        m_match2 = re.search(rf'{m_str}\s+([0-9]{{1,2}})(?:st|nd|rd|th)?', t)
        if m_match2:
            day_num = int(m_match2.group(1))
            year = anchor_date.year if m_num >= anchor_date.month else anchor_date.year + 1
            return f"{year}-{m_num:02d}-{day_num:02d}"

    return (anchor_date + timedelta(days=2)).strftime("%Y-%m-%d")

def parse_months_timeline(text: str) -> Optional[int]:
    t = text.lower()
    m_match = re.search(r'([0-9]+)\s*(?:months?|mths?|mo)\b', t)
    if m_match:
        return int(m_match.group(1))
    y_match = re.search(r'([0-9]+)\s*(?:years?|yrs?)\b', t)
    if y_match:
        return int(y_match.group(1)) * 12
    return None

def parse_goal_intent(text: str) -> Optional[Dict[str, Any]]:
    t = text.lower()
    goal_keywords = ["want a", "want to buy", "save for", "saving for", "target", "invest for", "buying a", "plan for", "goal"]
    has_goal_kw = any(k in t for k in goal_keywords)

    cost = parse_amount(text)
    months = parse_months_timeline(text)

    if has_goal_kw or (cost is not None and months is not None):
        cleaned_text = re.sub(r'([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lakhs|lac|lacs|k)\b', '', t)
        cleaned_text = re.sub(r'(?:[₹]|rs\.?|inr)?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,8})', '', cleaned_text)
        cleaned_text = re.sub(r'in\s+[0-9]+\s*(?:months?|years?|mo|yrs?)', '', cleaned_text)
        cleaned_text = re.sub(r'[0-9]+\s*(?:months?|years?|mo|yrs?)', '', cleaned_text)
        for kw in ["i want a", "i want to buy a", "i want to buy", "save for a", "save for", "saving for a", "saving for", "buy a", "buy", "for"]:
            cleaned_text = cleaned_text.replace(kw, "")
        words = [w.capitalize() for w in cleaned_text.split() if w.isalnum() and len(w) > 2]
        item_name = " ".join(words[:2]) if words else "Target Goal"

        return {
            "is_goal": True,
            "item_name": item_name,
            "cost": cost,
            "months": months
        }
    return None

def get_auto_dip_chat_message(user_id: int) -> Optional[str]:
    dip = check_business_income_dip(user_id)
    if not dip.get("triggered"):
        return None

    shortfall = int(dip["shortfall"])
    projected = int(dip["projected_inflow"])
    baseline = int(dip["baseline"])
    p1_total = int(dip["p1_total"])
    p2_total = int(dip["p2_total"])

    lines = [
        f"⚠️ CashPilot Alert: Income Dip Detected for November.",
        f"Projected revenue is ₹{projected:,}, falling ₹{shortfall:,} short of your Baseline Stable Income (₹{baseline:,}).",
        f"\nPriority Expense Allocation:",
        f"• P1 Essential (Pay First): Housing, Phone/Data, Loan/EMI, Utilities, Insurance.",
        f"  Total P1: ₹{p1_total:,}. " + (f"Projected revenue covers essentials with ₹{int(dip['essentials_diff']):,} buffer." if dip.get("essentials_covered") else f"Essentials are underfunded!"),
        f"• P2 Needed: Groceries & Transport Total: ₹{p2_total:,}.",
        f"• P3 Temporary Cuts to cover the ₹{shortfall:,} gap:"
    ]

    for cut in dip.get("p3_suggested_cuts", []):
        lines.append(f"  - Pause {cut['item']}: saves ₹{int(cut['savings']):,}/month")

    lines.append(f"Total P3 savings = ₹{int(dip.get('total_p3_savings', 0)):,}, protecting your business cashflow.")
    return "\n".join(lines)


def build_financial_context_str(user_id: int, persona: str) -> str:
    """Build a rich text summary of user financial state for advisor grounding."""
    cal_data = get_calendar_data(user_id, persona)
    summary = cal_data.get("summary", {})
    prof = get_profile_data(user_id, persona)
    mom = get_mom_comparison(user_id, persona)
    commitments = get_fixed_commitments(user_id, persona).get("commitments", [])
    limits = get_user_limits(user_id, persona)

    lines = [
        f"Persona: {persona}",
        f"Current Cash Balance: ₹{int(summary.get('balance', 0)):,}",
        f"This Month Inflow: ₹{int(summary.get('income', 0)):,}",
        f"This Month Spent: ₹{int(summary.get('spent', 0)):,}",
        f"Reserved Remaining (Unpaid Bills): ₹{int(summary.get('reserved_remaining', 0)):,}",
        f"Safe Left to Spend: ₹{int(summary.get('left_to_spend', 0)):,}",
        f"Baseline Monthly Income: ₹{int(prof.get('baseline_income', 0)):,}",
        f"Monthly Savings Transfer: ₹{int(prof.get('monthly_savings_amount', 0)):,}",
    ]
    if commitments:
        c_strs = [f"{c['name']} (₹{int(c['amount']):,}, Day {c.get('day_of_month', 'N/A')})" for c in commitments[:5]]
        lines.append(f"Upcoming Commitments: {', '.join(c_strs)}")
    if limits:
        top_limits = [f"{k}: ₹{int(v):,}" for k, v in list(limits.items())[:5]]
        lines.append(f"Budget Limits: {', '.join(top_limits)}")
    if mom.get("overspent"):
        over_strs = [f"{o['category']} (+₹{int(o['over_amount']):,})" for o in mom["overspent"][:3]]
        lines.append(f"Over-budget Categories: {', '.join(over_strs)}")
    return "\n".join(lines)


def handle_chat_message(user_id: int, message: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    t = message.lower().strip()
    persona = get_active_persona(user_id)
    cal_data = get_calendar_data(user_id, persona)
    summary = cal_data.get("summary", {})
    records = load_user_transactions_persona(user_id, persona)
    prof = get_profile_data(user_id, persona)
    limits = get_user_limits(user_id, persona)
    mom = get_mom_comparison(user_id, persona)

    # 1. Goal Advisor Query ("laptop 80k in 8 months", "save for car 5 lakh in 24 months")
    goal_info = parse_goal_intent(message)
    if goal_info and goal_info.get("is_goal"):
        cost = goal_info.get("cost")
        months = goal_info.get("months")
        item_name = goal_info.get("item_name", "Goal")

        if not cost:
            return {
                "reply": f"What is your target budget for {item_name}? For example: '{item_name} for 80k in 8 months'",
                "simulation": None,
                "intent": "goal_clarification_cost"
            }
        if not months:
            return {
                "reply": f"What is your target timeline in months to buy {item_name}? For example: 'in 8 months'",
                "simulation": None,
                "intent": "goal_clarification_months"
            }

        plan = plan_investment_goal(user_id, item_name, cost, months)
        reply = (
            f"🎯 Roadmap for {item_name} (₹{int(cost):,} in {months} months):\n"
            f"• Required Monthly Saving: ₹{int(plan['required_monthly_saving']):,}/mo\n"
            f"• Status: {plan['feasibility_description']}\n"
            f"• Investment Recommendation: {plan['recommended_instrument']} at {plan['assumed_annual_rate']}% p.a. "
            f"(SIP deposit of ₹{int(plan['sip_amount']):,}/mo; {plan['disclaimer']}).\n"
            f"• Check the Investments & Goals tab for your full month-by-month roadmap table."
        )
        return {
            "reply": reply,
            "goal_plan": plan,
            "simulation": None,
            "intent": "goal_plan"
        }

    # 2. Affordability Questions ("can i afford a phone for 40000?", "should i buy a bicycle for 15k?")
    is_affordability = any(k in t for k in ["can i afford", "should i buy", "can i buy", "is it safe to buy", "can i spend"])
    if is_affordability:
        amt = parse_amount(message)
        if amt:
            date_str = parse_date(message)
            scenario = {
                "type": "purchase",
                "amount": amt,
                "date": date_str,
                "interest_rate": 9.0
            }
            sim_result = simulate_scenario(user_id, scenario, persona)
            verdict = sim_result["verdict"]
            lowest = sim_result["lowest_balance"]
            month_end = sim_result["month_end_balance"]
            short_bills = [b["name"] for b in sim_result.get("bills", []) if b["status"] == "Short"]

            if verdict == "Safe":
                reply = (
                    f"✅ Yes, you can comfortably afford this ₹{int(amt):,} purchase on {date_str}. "
                    f"Your lowest running balance will remain at ₹{int(lowest):,} (well above your safety buffer), "
                    f"and month-end cash is projected at ₹{int(month_end):,}. All upcoming bills stay fully covered."
                )
            elif verdict == "Risky":
                reply = (
                    f"⚠️ Caution: Spending ₹{int(amt):,} on {date_str} is tight. "
                    f"Your lowest cash balance would drop to ₹{int(lowest):,}, cutting into your buffer. "
                    f"Month-end balance would be ₹{int(month_end):,}. Consider delaying or finding ₹{int(sim_result.get('buffer', 10000) - lowest):,} in cuts."
                )
            else:
                short_text = f", putting bills at risk: {', '.join(short_bills)}" if short_bills else ""
                reply = (
                    f"❌ Not advisable. A ₹{int(amt):,} purchase on {date_str} would breach your balance into the negative "
                    f"(lowest balance drops to -₹{int(abs(lowest)):,}{short_text}). "
                    f"Prioritize your reserved commitments first."
                )

            return {
                "reply": reply,
                "simulation": {**sim_result, "scenario": scenario},
                "intent": "affordability_check"
            }

    # 3. Direct What-If Simulation Scenarios
    scenario_type = None
    if any(k in t for k in ["prepay", "foreclose", "pay off loan", "prepayment"]):
        scenario_type = "prepay_loan"
    elif any(k in t for k in ["take a loan", "emi of", "new loan", "car emi", "home loan"]):
        scenario_type = "loan_emi"
    elif any(k in t for k in ["salary hike", "income drops", "pay raise", "hike", "bonus", "pay cut"]):
        scenario_type = "income_change"
    elif any(k in t for k in ["cancel netflix", "cancel spotify", "cancel subscription", "cancel", "stop subscription"]):
        scenario_type = "cancel_subscription"
    elif any(k in t for k in ["buy", "purchase", "spend", "bought", "spending", "get a laptop", "get a phone"]):
        scenario_type = "purchase"

    amount = parse_amount(message)
    date_str = parse_date(message)
    interest_rate = 9.0
    rate_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*%', message)
    if rate_match:
        interest_rate = float(rate_match.group(1))

    if scenario_type and (amount or scenario_type == "cancel_subscription"):
        if scenario_type == "cancel_subscription" and not amount:
            amount = 649.0

        scenario = {
            "type": scenario_type,
            "amount": amount,
            "date": date_str,
            "interest_rate": interest_rate
        }
        sim_result = simulate_scenario(user_id, scenario, persona)
        reply = explain_simulation(sim_result, scenario)
        return {
            "reply": reply,
            "simulation": {**sim_result, "scenario": scenario},
            "intent": scenario_type
        }

    # 4. Savings & Expense Cutting Advice
    if any(k in t for k in ["how can i save", "how to save", "reduce expenses", "cut costs", "save more money", "trim budget", "save money", "cut down"]):
        discretionary = ["Food", "Shopping", "Entertainment", "Subscriptions", "Transport"]
        # Calculate current spending in these categories
        cat_spending: Dict[str, float] = {}
        for r in records:
            if r.get("type") == "debit":
                cat = r.get("category", "Other")
                cat_spending[cat] = cat_spending.get(cat, 0.0) + r.get("amount", 0.0)

        discretionary_total = sum(cat_spending.get(c, 0.0) for c in discretionary)
        # Find top 2 discretionary spend categories
        disc_sorted = sorted([(c, cat_spending.get(c, 0.0)) for c in discretionary if cat_spending.get(c, 0.0) > 0], key=lambda x: x[1], reverse=True)

        tips = []
        if disc_sorted:
            top_cat, top_amt = disc_sorted[0]
            cut_amt = round(top_amt * 0.20)
            tips.append(f"1. **Trim {top_cat}**: You've spent ₹{int(top_amt):,} here. Cutting 20% by cooking at home or limiting impulse orders saves **₹{cut_amt:,}/month**.")
        if len(disc_sorted) > 1:
            second_cat, sec_amt = disc_sorted[1]
            cut_amt = round(sec_amt * 0.25)
            tips.append(f"2. **Cap {second_cat}**: Currently at ₹{int(sec_amt):,}. Setting a strict weekly cap saves another **₹{cut_amt:,}/month**.")

        # Subscriptions check
        sub_spend = cat_spending.get("Subscriptions", 0.0)
        if sub_spend > 500:
            tips.append(f"3. **Audit Subscriptions**: Totaling ₹{int(sub_spend):,}/month. Auditing unused OTT or cloud tools can immediately recover **₹{int(sub_spend * 0.5):,}/month**.")
        else:
            tips.append("3. **Automate Savings First**: Schedule your monthly savings transfer on salary day (pay yourself first) before opening the rest for spending.")

        reply = (
            f"💡 **Practical Savings Blueprint based on your actual spend:**\n"
            f"You've spent ₹{int(discretionary_total):,} across flexible categories this month.\n\n"
            + "\n\n".join(tips) +
            f"\n\n👉 Executing these 3 steps could unlock up to **₹{int(discretionary_total * 0.20):,}** in additional monthly savings!"
        )
        return {"reply": reply, "simulation": None, "intent": "savings_advice"}

    # 5. Left to Spend & Run Out of Cash
    if any(q in t for q in ["will i run out of money", "run out of cash", "go broke", "run out", "safe to spend", "how much can i spend", "is it safe to spend", "left to spend"]):
        reply = explain_left_to_spend(summary)
        return {"reply": reply, "simulation": None, "intent": "left_to_spend"}

    # 6. Balance & Financial Status Summary
    if any(q in t for q in ["what is my balance", "current balance", "how much money do i have", "cash status", "financial status", "summary", "how am i doing"]):
        bal = int(summary.get("balance", 0))
        inc = int(summary.get("income", 0))
        spent = int(summary.get("spent", 0))
        res_rem = int(summary.get("reserved_remaining", 0))
        lts = int(summary.get("left_to_spend", 0))
        reply = (
            f"📊 **Financial Snapshot ({persona.capitalize()}):**\n"
            f"• **Current Ledger Balance:** ₹{bal:,}\n"
            f"• **Month Inflow:** ₹{inc:,}\n"
            f"• **Month Spent:** ₹{spent:,}\n"
            f"• **Reserved Bills Remaining:** ₹{res_rem:,}\n"
            f"• **Safe Left to Spend:** ₹{lts:,} (after setting aside buffer and upcoming bills)"
        )
        return {"reply": reply, "simulation": None, "intent": "financial_status"}

    # 7. Top Spending & Breakdown ("where did my money go", "biggest expenses", "top categories")
    if any(q in t for q in ["where did my money go", "where is my money going", "biggest expense", "highest spend", "top spend", "expense breakdown"]):
        cat_spending = {}
        for r in records:
            if r.get("type") == "debit":
                cat = r.get("category", "Other")
                cat_spending[cat] = cat_spending.get(cat, 0.0) + r.get("amount", 0.0)

        sorted_cats = sorted(cat_spending.items(), key=lambda x: x[1], reverse=True)
        top_txs = sorted([r for r in records if r.get("type") == "debit"], key=lambda x: x.get("amount", 0.0), reverse=True)[:3]

        lines = ["📈 **Your Highest Spending Areas This Month:**"]
        for cat, amt in sorted_cats[:4]:
            lines.append(f"• **{cat}:** ₹{int(amt):,}")

        if top_txs:
            lines.append("\n**Top 3 Individual Transactions:**")
            for tx in top_txs:
                lines.append(f"• ₹{int(tx['amount']):,} at {tx.get('cleaned_merchant') or tx.get('description')} ({tx.get('category')}) on {tx.get('date')}")

        reply = "\n".join(lines)
        return {"reply": reply, "simulation": None, "intent": "top_spending"}

    # 8. Category-Specific Queries ("food spend", "how much on groceries", "amazon spend", etc.)
    common_cats = ["food", "groceries", "shopping", "transport", "utilities", "housing", "subscriptions", "loan", "entertainment", "health"]
    matched_cat = next((c for c in common_cats if c in t), None)
    if matched_cat and any(q in t for q in ["how much", "spend", "spent", "total"]):
        cat_proper = matched_cat.capitalize()
        matching_txs = [r for r in records if r.get("type") == "debit" and cat_proper.lower() in r.get("category", "").lower()]
        total_spent = sum(r.get("amount", 0.0) for r in matching_txs)
        limit_val = limits.get(cat_proper, 0.0)
        limit_info = f" (Monthly limit: ₹{int(limit_val):,})" if limit_val > 0 else ""
        status_info = f" — over limit by ₹{int(total_spent - limit_val):,}!" if (limit_val > 0 and total_spent > limit_val) else " — within safe limits."

        reply = (
            f"🛒 **{cat_proper} Spending Analysis:**\n"
            f"You have spent **₹{int(total_spent):,}** across {len(matching_txs)} transactions this month{limit_info}{status_info}"
        )
        return {"reply": reply, "simulation": None, "intent": "category_analysis"}

    # 9. Upcoming Bills & Commitments
    if any(q in t for q in ["which bills are coming", "bills coming", "upcoming bills", "bills due", "when is rent", "when is emi"]):
        comm_info = get_fixed_commitments(user_id, persona)
        obs = comm_info.get("commitments", [])
        if not obs:
            return {"reply": "No recurring bills detected or added yet. You can add them under the Recurring tab.", "simulation": None, "intent": "bills_coming"}
        bill_lines = [f"• **{b['name']}**: ₹{int(b['amount']):,} due on day {b.get('day_of_month', 'N/A')}" for b in obs[:5]]
        reply = "📅 **Upcoming Recurring Commitments:**\n" + "\n".join(bill_lines) + f"\n\nTotal Monthly Fixed Commitments: **₹{int(comm_info.get('total_monthly', 0)):,}**"
        return {"reply": reply, "simulation": None, "intent": "bills_coming"}

    # 10. Emergency Fund & Runway
    if any(q in t for q in ["emergency fund", "runway", "safety buffer", "how many months can i survive", "safety net"]):
        bal = summary.get("balance", 0.0)
        # Essentials = housing, loan, utilities, insurance, phone + groceries
        essentials_cats = ["Housing", "Loan/EMI", "Utilities", "Insurance", "Phone/Data", "Groceries"]
        essential_spend = 0.0
        for r in records:
            if r.get("type") == "debit" and r.get("category") in essentials_cats:
                essential_spend += r.get("amount", 0.0)
        if essential_spend == 0:
            essential_spend = max(20000.0, bal * 0.3)

        runway_months = round(bal / essential_spend, 1) if essential_spend > 0 else 0.0
        target_3mo = round(essential_spend * 3)
        target_6mo = round(essential_spend * 6)

        reply = (
            f"🛡️ **Emergency Runway Analysis:**\n"
            f"• Estimated Essential Monthly Expenses: **₹{int(essential_spend):,}**\n"
            f"• Current Cash Runway: **{runway_months} months** based on current balance of ₹{int(bal):,}.\n"
            f"• 3-Month Target: ₹{target_3mo:,} | 6-Month Target: ₹{target_6mo:,}.\n"
            + ("✅ Your emergency runway is strong and provides ample security." if runway_months >= 3.0 else "⚠️ Aim to build at least 3 months of essential buffer in a liquid fund.")
        )
        return {"reply": reply, "simulation": None, "intent": "emergency_fund"}

    # 11. Investment Advisory Inquiries
    if any(q in t for q in ["how much can i invest", "how much should i invest", "investable surplus", "where to invest", "sip", "investment advice"]):
        baseline = prof.get("baseline_income", 0.0)
        total_curr = sum(mom.get("current_month_spending", []))
        surplus = max(0.0, baseline - total_curr)
        safe_invest = round(surplus * 0.70, 2)
        liquid_buffer = round(surplus - safe_invest, 2)
        reply = (
            f"📈 **Investment & Surplus Recommendation:**\n"
            f"• Baseline Monthly Income: ₹{int(baseline):,} | Recent Monthly Spend: ₹{int(total_curr):,}\n"
            f"• Estimated Monthly Surplus: **₹{int(surplus):,}/mo**\n"
            f"• Recommended 70% Systematic Allocation: **₹{int(safe_invest):,}/mo** into diversified Index / Equity SIPs.\n"
            f"• 30% Liquid Buffer: **₹{int(liquid_buffer):,}/mo** kept in liquid funds/savings for emergency needs."
        )
        return {"reply": reply, "simulation": None, "intent": "advisory_invest"}

    if any(q in t for q in ["am i saving enough", "savings rate", "is my savings good"]):
        baseline = prof.get("baseline_income", 0.0)
        total_curr = sum(mom.get("current_month_spending", []))
        surplus = max(0.0, baseline - total_curr)
        rate = round((surplus / baseline) * 100.0, 1) if baseline > 0 else 0.0
        verdict = "healthy and above the recommended 20% benchmark" if rate >= 20.0 else "below the 20% benchmark; consider trimming discretionary spending"
        reply = (
            f"💰 **Savings Rate Check:**\n"
            f"Your current monthly savings rate is **{rate}%** (₹{int(surplus):,} saved from baseline income of ₹{int(baseline):,}). "
            f"This is {verdict}."
        )
        return {"reply": reply, "simulation": None, "intent": "advisory_savings_rate"}

    # 12. Business Tips
    if any(q in t for q in ["tips to grow my business", "grow my business", "business tips", "increase revenue", "income dip"]):
        if persona != "business":
            return {
                "reply": "Business growth tips and income dip monitors are available in the Small Business persona. You can switch to Small Business in the header switcher anytime.",
                "simulation": None,
                "intent": "business_tips"
            }
        dip = check_business_income_dip(user_id)
        dip_status = f"Income dip is active with a shortfall of ₹{int(dip.get('shortfall', 0)):,}." if dip.get("triggered") else "Cashflow is currently steady with no revenue dip active."
        reply = (
            f"🏢 **Small Business Strategic Action Plan:**\n"
            f"• **Current Status:** {dip_status}\n"
            f"• **1. Invoice Terms:** Offer 2-3% quick-pay discount on 15-day invoices to accelerate receivables and avoid mid-month payment lulls.\n"
            f"• **2. Overhead Shield:** Ensure P1 commitments (Rent, EMIs, Utility Bills) are covered before releasing discretionary vendor payouts.\n"
            f"• **3. Retainer Stability:** Convert one-off clients into recurring monthly retainers to establish an even baseline."
        )
        return {"reply": reply, "simulation": None, "intent": "business_tips"}

    # 13. Gemini AI Advisor / Flexible Fallback for any raw consumer question
    context_str = build_financial_context_str(user_id, persona)
    ai_response = call_gemini_api(message, context_str)
    if ai_response:
        return {
            "reply": ai_response,
            "simulation": None,
            "intent": "ai_advisor"
        }

    # Rich native data-driven response fallback
    bal = int(summary.get("balance", 0))
    lts = int(summary.get("left_to_spend", 0))
    res_rem = int(summary.get("reserved_remaining", 0))
    reply = (
        f"I'm your CashPilot financial copilot. Based on your live ledger:\n"
        f"• **Current Balance:** ₹{bal:,} | **Left to Spend:** ₹{lts:,} | **Reserved Bills:** ₹{res_rem:,}\n\n"
        f"You can ask me questions like:\n"
        f"• *\"How can I save more money this month?\"*\n"
        f"• *\"Can I afford a laptop for 60k next week?\"*\n"
        f"• *\"Where did I spend the most money?\"*\n"
        f"• *\"What bills are coming up?\"*\n"
        f"• *\"Laptop 80k in 8 months\" (for a goal roadmap)*"
    )
    return {
        "reply": reply,
        "simulation": None,
        "intent": "general_guidance"
    }
