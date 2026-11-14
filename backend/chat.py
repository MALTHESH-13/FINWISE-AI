import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from backend.simulator import simulate_scenario, get_forecast
from backend.explain import explain_simulation, explain_general_query
from backend.persona import (
    get_active_persona,
    get_profile_data,
    plan_investment_goal,
    check_business_income_dip,
    load_user_transactions_persona,
    get_mom_comparison
)
from backend.gemini_service import (
    is_gemini_configured,
    generate_gemini_chat_reply,
    call_gemini,
    build_user_financial_context
)

def parse_amount(text: str) -> Optional[float]:
    t = text.lower()
    # Match patterns like "1.5 lakh", "2 lakhs", "1.5lakh", "80k"
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
    """
    BUSINESS INCOME-DIP PRIORITY ENGINE auto-message when triggered.
    """
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
        f"  Total P1: ₹{p1_total:,}. " + (f"Projected revenue covers essentials with ₹{int(dip['essentials_diff']):,} buffer." if dip["essentials_covered"] else f"Essentials are underfunded by ₹{abs(int(dip['essentials_diff'])):,}!"),
        f"• P2 Needed: Groceries & Transport Total: ₹{p2_total:,}.",
        f"• P3 Temporary Cuts to cover the ₹{shortfall:,} gap:"
    ]

    for cut in dip.get("p3_suggested_cuts", []):
        lines.append(f"  - Pause {cut['item']}: saves ₹{int(cut['savings']):,}/month")

    lines.append(f"Total P3 savings = ₹{int(dip.get('total_p3_savings', 0)):,}, protecting your business cashflow.")
    return "\n".join(lines)

def handle_chat_message(user_id: int, message: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    t = message.lower().strip()
    persona = get_active_persona(user_id)

    # 1. Goal Advisor Query
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

        # Plan the goal
        plan = plan_investment_goal(user_id, item_name, cost, months)
        reply = (
            f"Roadmap for {item_name} (₹{int(cost):,} in {months} months): "
            f"Requires saving ₹{int(plan['required_monthly_saving']):,}/month. "
            f"Status: {plan['feasibility_description']} "
            f"Horizon Rule recommends {plan['recommended_instrument']} at {plan['assumed_annual_rate']}% p.a. "
            f"(SIP deposit of ₹{int(plan['sip_amount']):,}/mo; {plan['disclaimer']}). "
            f"A complete month-by-month milestone table is generated in your Investments & Goals tab."
        )

        # Optional Gemini enhancement
        if is_gemini_configured():
            try:
                gemini_tip = call_gemini(
                    f"User goal: {item_name} for ₹{int(cost):,} in {months} months. "
                    f"Required monthly saving: ₹{int(plan['required_monthly_saving']):,}. "
                    f"Feasibility: {plan['feasibility']}. "
                    f"Give 1 actionable tip on how to achieve this without lifestyle pain in 2 sentences.",
                    max_tokens=150,
                    timeout_seconds=4.0
                )
                if gemini_tip:
                    reply += f"\n\n✨ Gemini AI Tip: {gemini_tip}"
            except Exception:
                pass

        return {
            "reply": reply,
            "goal_plan": plan,
            "simulation": None,
            "intent": "goal_plan",
            "ai_powered": is_gemini_configured()
        }

    # 2. What-If Scenarios
    scenario_type = None
    if any(k in t for k in ["prepay", "foreclose", "pay off loan", "prepayment"]):
        scenario_type = "prepay_loan"
    elif any(k in t for k in ["take a loan", "emi of", "new loan"]):
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

    if scenario_type:
        if not amount and scenario_type not in ["cancel_subscription"]:
            example = (
                "If I buy a laptop for 60k on Monday, can I pay rent?" if scenario_type == "purchase"
                else "What if I prepay 50k on my loan next week?"
            )
            return {
                "reply": f"Could you specify the amount you want to {scenario_type.replace('_', ' ')}? For example: \"{example}\"",
                "simulation": None,
                "intent": scenario_type
            }

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

        # Optional Gemini enhancement
        if is_gemini_configured():
            try:
                min_before = int(sim_result.get("min_balance_before", 0))
                min_after = int(sim_result.get("min_balance_after", 0))
                prob_before = round(sim_result.get("prob_before", 0) * 100, 1)
                prob_after = round(sim_result.get("prob_after", 0) * 100, 1)
                gemini_insight = call_gemini(
                    f"What-if scenario: {scenario_type} of ₹{int(amount):,} on {date_str}. "
                    f"Min balance shifts from ₹{min_before:,} to ₹{min_after:,}. "
                    f"Shortage risk changes from {prob_before}% to {prob_after}%. "
                    f"Summarize the practical takeaway for the user in 2 sentences.",
                    max_tokens=150,
                    timeout_seconds=4.0
                )
                if gemini_insight:
                    reply += f"\n\n✨ Gemini AI Takeaway: {gemini_insight}"
            except Exception:
                pass

        return {
            "reply": reply,
            "simulation": {
                **sim_result,
                "scenario": scenario
            },
            "intent": scenario_type,
            "ai_powered": is_gemini_configured()
        }

    # 3. Check with Google Gemini for Advisory or Free-Text Inquiries
    if is_gemini_configured():
        try:
            gemini_advice = generate_gemini_chat_reply(user_id, message, history)
            if gemini_advice and len(gemini_advice.strip()) > 15:
                return {
                    "reply": gemini_advice,
                    "simulation": None,
                    "intent": "gemini_advisory",
                    "ai_powered": True
                }
        except Exception:
            pass

    # 4. Fallback Rule-Based Financial Advisory
    if any(q in t for q in ["how much can i invest", "how much should i invest", "investable surplus"]):
        prof = get_profile_data(user_id, persona)
        baseline = prof["baseline_income"]
        mom = get_mom_comparison(user_id, persona)
        total_curr = sum(mom.get("current_month_spending", []))
        surplus = max(0.0, baseline - total_curr)
        safe_invest = round(surplus * 0.70, 2)
        return {
            "reply": (
                f"Based on your baseline monthly income of ₹{int(baseline):,} and recent monthly spending of ₹{int(total_curr):,}, "
                f"your estimated investable surplus is ₹{int(surplus):,}/month. "
                f"We recommend allocating 70% (₹{int(safe_invest):,}/mo) into recommended SIPs and retaining 30% (₹{int(surplus - safe_invest):,}/mo) as an emergency liquid buffer."
            ),
            "simulation": None,
            "intent": "advisory_invest",
            "ai_powered": False
        }

    if any(q in t for q in ["am i saving enough", "savings rate", "is my savings good"]):
        prof = get_profile_data(user_id, persona)
        baseline = prof["baseline_income"]
        mom = get_mom_comparison(user_id, persona)
        total_curr = sum(mom.get("current_month_spending", []))
        surplus = max(0.0, baseline - total_curr)
        rate = round((surplus / baseline) * 100.0, 1) if baseline > 0 else 0.0
        verdict = "healthy and above the recommended 20% benchmark" if rate >= 20.0 else "below the 20% benchmark; consider trimming discretionary categories"
        return {
            "reply": (
                f"Your current monthly savings rate is {rate}% (₹{int(surplus):,} saved from a baseline income of ₹{int(baseline):,}). "
                f"This is {verdict}."
            ),
            "simulation": None,
            "intent": "advisory_savings_rate",
            "ai_powered": False
        }

    if any(q in t for q in ["tips to grow my business", "grow my business", "business tips", "increase revenue"]):
        if persona != "business":
            return {
                "reply": "Business growth tips are available in the Small Business persona. You can switch to Small Business in the header switcher anytime.",
                "simulation": None,
                "intent": "business_tips",
                "ai_powered": False
            }
        return {
            "reply": (
                "Here are 3 data-driven recommendations for your business: "
                "1. Revenue Pattern: Your historical records show October was your peak revenue month (₹1,70,000), driven by large client retainers. "
                "2. Cashflow Smoothing: November current inflow is ₹35,000; offer 5% early-payment discounts on invoices to avoid 45-day payment lulls. "
                "3. Overhead Protection: Keep your 15% safety buffer active to guarantee covering P1 essentials (Office Rent and Loan EMIs) during low-inflow cycles."
            ),
            "simulation": None,
            "intent": "business_tips",
            "ai_powered": False
        }

    if any(q in t for q in ["will i run out of money", "run out of cash", "go broke", "run out"]):
        forecast = get_forecast(user_id, persona)
        reply = explain_general_query("run_out", forecast)
        return {"reply": reply, "simulation": None, "intent": "run_out", "ai_powered": False}

    if any(q in t for q in ["safe to spend", "how much can i spend", "is it safe to spend"]):
        forecast = get_forecast(user_id, persona)
        reply = explain_general_query("safe_to_spend", forecast)
        return {"reply": reply, "simulation": None, "intent": "safe_to_spend", "ai_powered": False}

    if any(q in t for q in ["biggest risk", "what's my biggest risk", "whats my biggest risk"]):
        forecast = get_forecast(user_id, persona)
        reply = explain_general_query("biggest_risk", forecast)
        return {"reply": reply, "simulation": None, "intent": "biggest_risk", "ai_powered": False}

    if any(q in t for q in ["which bills are coming", "bills coming", "upcoming bills", "bills due"]):
        forecast = get_forecast(user_id, persona)
        reply = explain_general_query("bills_coming", forecast)
        return {"reply": reply, "simulation": None, "intent": "bills_coming", "ai_powered": False}

    return {
        "reply": (
            "I can help you evaluate what-if scenarios, plan financial goals, or review cashflow risks. "
            "Try: \"laptop 80k in 8 months\", \"If I buy a laptop for 60k on Monday, can I pay rent?\", "
            "or \"tips to grow my business\"."
        ),
        "simulation": None,
        "intent": "clarification_needed",
        "ai_powered": False
    }
