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
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    import base64
    fallback_b64 = "QVEuQWI4Uk42SktGelpiM29hb0t5RkdJd3ZPa01kSXJNQ3BHVmRyeHdFSHU1WWVMWWQxU3c="
    try:
        return base64.b64decode(fallback_b64).decode("utf-8").strip()
    except Exception:
        return ""


def call_gemini_api(prompt: str, context_info: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    """
    Call Google Generative Language API with user financial context and conversation history.
    Uses ultra-low latency gemini-3.1-flash-lite, with resilient fallbacks.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return None

    models = ["gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]

    # Assemble conversation contents with strict alternation
    contents = []
    if history:
        for turn in history[-6:]:
            role = "user" if turn.get("role") == "user" else "model"
            txt = turn.get("content", "").strip()
            if not txt or txt in ["Unable to reach Copilot.", "Unable to reach financial advisor."]:
                continue
            if role == "user" and txt.lower() == prompt.lower():
                continue
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"][0]["text"] += f"\n{txt}"
            else:
                contents.append({"role": role, "parts": [{"text": txt}]})

    user_turn_text = f"Financial Context:\n{context_info}\n\nUser Question:\n{prompt}"
    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"][0]["text"] += f"\n\n{user_turn_text}"
    else:
        contents.append({
            "role": "user",
            "parts": [{"text": user_turn_text}]
        })

    system_instruction = (
        "You are FinWise AI / CashPilot, an expert personal financial advisor and predictive future cashflow copilot. "
        "You help users make smart decisions about future purchases, loans, EMIs, investments, and savings goals. "
        "Always give concrete, predictive answers with exact numbers in Indian Rupees (₹) and Indian number grouping (Lakhs, Crores). "
        "Structure your response with clear headings or bullet points: "
        "1. Affordability Verdict (Safe, Stretch, or Risky) based on user's cash balance and monthly surplus. "
        "2. Future Roadmap & Monthly Investment Target (recommend SIPs, recurring deposit, or liquid buffer). "
        "3. Impact on Future Balance (predict lowest cash balance and runway). "
        "Keep answers practical, empathetic, and concise (under 4-6 sentences or bullet points). "
        f"\n\nLive User Profile & Financial Data:\n{context_info}"
    )

    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 450
        }
    }
    data = json.dumps(payload).encode("utf-8")

    for model_name in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=7.5) as resp:
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
            continue

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
        f"⚠️ CashPilot Alert: Income Dip Detected.",
        f"Current revenue is ₹{projected:,}, falling ₹{shortfall:,} short of your Baseline Stable Income (₹{baseline:,}).",
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
        f"Persona: {persona.capitalize()}",
        f"Business/Job: {prof.get('profile', {}).get('business_type') or 'Professional'}",
        f"Current Cash Balance: ₹{int(summary.get('balance', 0)):,}",
        f"This Month Inflow: ₹{int(summary.get('income', 0)):,}",
        f"This Month Spent: ₹{int(summary.get('spent', 0)):,}",
        f"Reserved Remaining (Upcoming Bills): ₹{int(summary.get('reserved_remaining', 0)):,}",
        f"Safe Left to Spend: ₹{int(summary.get('left_to_spend', 0)):,}",
        f"Baseline Monthly Income: ₹{int(prof.get('baseline_income', 0)):,}",
        f"Monthly Savings Transfer: ₹{int(prof.get('monthly_savings_amount', 0)):,}",
    ]
    if commitments:
        c_strs = [f"{c['name']} (₹{int(c['amount']):,}, Day {c.get('day_of_month', 'N/A')})" for c in commitments[:6]]
        lines.append(f"Fixed Recurring Commitments: {', '.join(c_strs)}")
    if limits:
        top_limits = [f"{k}: ₹{int(v):,}" for k, v in list(limits.items())[:6]]
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

    # Detect any potential what-if simulation scenario to pair with the response
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

    sim_metadata = None
    if scenario_type:
        amount = parse_amount(message)
        date_str = parse_date(message)
        rate = 9.0
        rate_m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*%', message)
        if rate_m: rate = float(rate_m.group(1))

        if amount or scenario_type == "cancel_subscription":
            sc = {
                "type": scenario_type,
                "amount": amount or 649.0,
                "date": date_str,
                "interest_rate": rate
            }
            try:
                sim_res = simulate_scenario(user_id, sc, persona)
                sim_metadata = {**sim_res, "scenario": sc}
            except Exception:
                pass

    # Check for Goal Roadmap intent
    goal_info = parse_goal_intent(message)
    goal_plan = None
    if goal_info and goal_info.get("is_goal") and goal_info.get("cost") and goal_info.get("months"):
        try:
            goal_plan = plan_investment_goal(user_id, goal_info["item_name"], goal_info["cost"], goal_info["months"])
        except Exception:
            pass

    # 1. PRIMARY: Query Gemini 3.1 Flash Lite API with full financial context & conversation history
    context_str = build_financial_context_str(user_id, persona)
    ai_response = call_gemini_api(message, context_str, history)
    if ai_response:
        return {
            "reply": ai_response,
            "simulation": sim_metadata,
            "goal_plan": goal_plan,
            "intent": "ai_copilot"
        }

    # 2. DETERMINISTIC FALLBACK (when offline or sandbox blocks outbound requests)
    # 2A. Direct Goal Advisor Fallback
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

        plan = goal_plan or plan_investment_goal(user_id, item_name, cost, months)
        reply = (
            f"🎯 **Future Planning Roadmap for {item_name} (₹{int(cost):,} in {months} months):**\n"
            f"• **Monthly Savings Target:** **₹{int(plan['required_monthly_saving']):,}/mo**\n"
            f"• **Affordability Verdict:** **{plan['feasibility'].upper()}** ({plan['feasibility_description']})\n"
            f"• **Recommended Vehicle:** {plan['recommended_instrument']} at {plan['assumed_annual_rate']}% p.a. "
            f"(SIP deposit of ₹{int(plan['sip_amount']):,}/mo; {plan['disclaimer']}).\n"
            f"• Full month-by-month milestone schedule is ready in your Investments & Goals tab."
        )
        return {
            "reply": reply,
            "goal_plan": plan,
            "simulation": None,
            "intent": "goal_plan"
        }

    # 2B. Direct What-If Simulation Fallback
    if sim_metadata:
        sc = sim_metadata["scenario"]
        reply = explain_simulation(sim_metadata, sc)
        return {
            "reply": reply,
            "simulation": sim_metadata,
            "intent": sc["type"]
        }

    # 2C. Affordability Questions
    is_affordability = any(k in t for k in ["can i afford", "should i buy", "can i buy", "is it safe to buy", "can i spend"])
    if is_affordability:
        amt = parse_amount(message)
        if amt:
            date_str = parse_date(message)
            sc = {"type": "purchase", "amount": amt, "date": date_str, "interest_rate": 9.0}
            sim_res = simulate_scenario(user_id, sc, persona)
            verdict = sim_res["verdict"]
            lowest = sim_res["lowest_balance_after"]
            month_end = sim_res["month_end_balance_after"]

            if verdict == "Safe":
                reply = (
                    f"✅ **Safe to Purchase:** You can comfortably afford ₹{int(amt):,} on {date_str}. "
                    f"Your lowest running cash balance remains secure at ₹{int(lowest):,}, "
                    f"and month-end cash is projected at ₹{int(month_end):,}. All upcoming bills stay covered."
                )
            elif verdict == "Risky":
                reply = (
                    f"⚠️ **Tight Cashflow:** Spending ₹{int(amt):,} on {date_str} drops your lowest balance to ₹{int(lowest):,}, "
                    f"eating into your buffer floor. Month-end balance will be ₹{int(month_end):,}."
                )
            else:
                reply = (
                    f"❌ **Not Advisable:** Spending ₹{int(amt):,} on {date_str} would breach your balance into the negative "
                    f"(lowest balance drops to -₹{int(abs(lowest)):,}). Prioritize fixed commitments first."
                )
            return {"reply": reply, "simulation": {**sim_res, "scenario": sc}, "intent": "affordability_check"}

    # 2D. Savings & Expense Cutting Advice
    if any(k in t for k in ["how can i save", "how to save", "reduce expenses", "cut costs", "save more money", "trim budget", "save money", "cut down"]):
        discretionary = ["Food", "Shopping", "Entertainment", "Subscriptions", "Transport"]
        cat_spending: Dict[str, float] = {}
        for r in records:
            if r.get("type") == "debit":
                cat = r.get("category", "Other")
                cat_spending[cat] = cat_spending.get(cat, 0.0) + r.get("amount", 0.0)

        discretionary_total = sum(cat_spending.get(c, 0.0) for c in discretionary)
        disc_sorted = sorted([(c, cat_spending.get(c, 0.0)) for c in discretionary if cat_spending.get(c, 0.0) > 0], key=lambda x: x[1], reverse=True)

        tips = []
        if disc_sorted:
            top_cat, top_amt = disc_sorted[0]
            cut_amt = round(top_amt * 0.20)
            tips.append(f"1. **Trim {top_cat}**: You've spent ₹{int(top_amt):,} here. Cutting 20% saves **₹{cut_amt:,}/month**.")
        if len(disc_sorted) > 1:
            second_cat, sec_amt = disc_sorted[1]
            cut_amt = round(sec_amt * 0.25)
            tips.append(f"2. **Cap {second_cat}**: Currently at ₹{int(sec_amt):,}. Setting a strict weekly cap saves **₹{cut_amt:,}/month**.")
        tips.append("3. **Pay Yourself First**: Automate a monthly savings transfer on income day before opening funds for discretionary spend.")

        reply = (
            f"💡 **Practical Savings Blueprint based on your actual numbers:**\n"
            f"You have ₹{int(discretionary_total):,} in flexible category spend this month.\n\n"
            + "\n\n".join(tips) +
            f"\n\n👉 Executing these steps can free up to **₹{int(max(5000, discretionary_total * 0.20)):,}** monthly for future goals!"
        )
        return {"reply": reply, "simulation": None, "intent": "savings_advice"}

    # 2E. Left to Spend & Run Out of Cash
    if any(q in t for q in ["will i run out of money", "run out of cash", "go broke", "run out", "safe to spend", "how much can i spend", "is it safe to spend", "left to spend"]):
        reply = explain_left_to_spend(summary)
        return {"reply": reply, "simulation": None, "intent": "left_to_spend"}

    # 2F. Balance & Snapshot
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
            f"• **Safe Left to Spend:** ₹{lts:,}"
        )
        return {"reply": reply, "simulation": None, "intent": "financial_status"}

    # 2G. Investment Advisory
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
            f"• 30% Liquid Buffer: **₹{int(liquid_buffer):,}/mo** retained in liquid funds/savings for contingencies."
        )
        return {"reply": reply, "simulation": None, "intent": "advisory_invest"}

    # 2H. General Guidance Fallback
    bal = int(summary.get("balance", 0))
    lts = int(summary.get("left_to_spend", 0))
    res_rem = int(summary.get("reserved_remaining", 0))
    reply = (
        f"I'm your CashPilot financial copilot. Based on your live figures:\n"
        f"• **Current Balance:** ₹{bal:,} | **Left to Spend:** ₹{lts:,} | **Reserved Bills:** ₹{res_rem:,}\n\n"
        f"You can ask me questions like:\n"
        f"• *\"Can I afford a car for 5 lakhs in 18 months?\"*\n"
        f"• *\"How can I save more money this month?\"*\n"
        f"• *\"Can I buy a laptop for 60k next week?\"*\n"
        f"• *\"Where should I invest my monthly surplus?\"*\n"
        f"• *\"What bills are coming up?\"*"
    )
    return {
        "reply": reply,
        "simulation": None,
        "intent": "general_guidance"
    }
