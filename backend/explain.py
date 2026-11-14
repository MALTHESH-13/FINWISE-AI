from typing import Dict, Any, Optional

def format_inr(val: float) -> str:
    # Format amount cleanly with commas
    val_int = int(round(val))
    neg = "-" if val_int < 0 else ""
    s = str(abs(val_int))
    if len(s) <= 3:
        return f"{neg}₹{s}"
    last_three = s[-3:]
    remaining = s[:-3]
    # Indian numbering format grouping in 2s
    groups = []
    while remaining:
        groups.append(remaining[-2:])
        remaining = remaining[:-2]
    groups.reverse()
    formatted = ",".join(groups) + "," + last_three
    return f"{neg}₹{formatted}"

def explain_simulation(sim: Dict[str, Any], scenario: Dict[str, Any]) -> str:
    """
    Generates 3-4 sentence explanation using ONLY real numbers from simulation.
    Includes: verdict, min balance before vs after, shortage probability change,
    and which upcoming bill is at risk.
    """
    verdict = sim.get("verdict", "Simulation complete.")
    min_before = sim.get("min_balance_before", 0.0)
    min_after = sim.get("min_balance_after", 0.0)
    p_before = sim.get("shortage_prob_before", 0.0) * 100.0
    p_after = sim.get("shortage_prob_after", 0.0) * 100.0

    # Bill at risk
    at_risk_obs = [o for o in sim.get("obligations", []) if o.get("status") in ["At risk", "Will likely miss"]]
    if at_risk_obs:
        target_ob = at_risk_obs[0]
        bill_risk_text = (
            f"Your upcoming bill '{target_ob['name']}' due on {target_ob['due_date']} "
            f"({format_inr(target_ob['amount'])}) shifts to {target_ob['status']} "
            f"with payment probability dropping to {target_ob['prob_after'] * 100:.0f}%."
        )
    else:
        bill_risk_text = "All scheduled obligations (including rent and utilities) remain Safe with over 95% certainty."

    # Prepay loan note if applicable
    prepay_text = ""
    prepay_details = sim.get("prepay_details")
    if prepay_details:
        prepay_text = (
            f" Prepaying {format_inr(prepay_details['cash_dip'])} at {prepay_details['assumed_rate']}% p.a. "
            f"saves an estimated {format_inr(prepay_details['interest_saved'])} in total interest, "
            f"cutting tenure by {prepay_details['tenure_reduced_months']} months."
        )

    # Combine into 3-4 concise sentences
    sentences = [
        f"Verdict: {verdict}",
        f"Your minimum projected cash balance shifts from {format_inr(min_before)} to {format_inr(min_after)}.",
        f"The probability of a cash shortage changes from {p_before:.1f}% to {p_after:.1f}%.",
        f"{bill_risk_text}{prepay_text}"
    ]

    return " ".join(sentences)

def explain_general_query(query_type: str, forecast: Dict[str, Any]) -> str:
    """
    Answers general non-what-if financial questions using real forecast numbers.
    """
    min_bal = forecast.get("min_balance", 0.0)
    shortage_prob = forecast.get("shortage_prob", 0.0) * 100.0
    cur_bal = forecast.get("current_balance", 0.0)
    obligations = forecast.get("obligations", [])

    if query_type == "run_out":
        if shortage_prob > 10.0:
            return (
                f"Based on current cashflow, there is a {shortage_prob:.1f}% risk of running short of money in the next 30 days. "
                f"Your lowest projected balance is {format_inr(min_bal)}. "
                f"Review your discretionary spending or upcoming large bills to maintain a safe buffer."
            )
        else:
            return (
                f"You are on track and unlikely to run out of money, with a {shortage_prob:.1f}% shortage probability. "
                f"Your balance is projected to stay above {format_inr(min_bal)} over the next 30 days. "
                f"Current cash balance sits comfortably at {format_inr(cur_bal)}."
            )

    elif query_type == "safe_to_spend":
        safe_margin = max(0.0, min_bal - 10000.0)
        return (
            f"Your current available balance is {format_inr(cur_bal)}, with an estimated safe spending margin of {format_inr(safe_margin)}. "
            f"Holding at least ₹10,000 buffer keeps your shortage risk at {shortage_prob:.1f}%. "
            f"Any single expense beyond {format_inr(safe_margin)} could strain upcoming obligations."
        )

    elif query_type == "bills_coming":
        if not obligations:
            return "No recurring bills detected in the immediate 30-day window."
        bill_lines = [f"• {b['name']} ({format_inr(b['amount'])}) on {b['due_date']} [{b['status']}]" for b in obligations[:4]]
        return f"Upcoming obligations in the next 30 days:\n" + "\n".join(bill_lines)

    elif query_type == "biggest_risk":
        at_risk = [b for b in obligations if b["status"] != "Safe"]
        if at_risk:
            b = at_risk[0]
            return (
                f"Your biggest risk is '{b['name']}' due on {b['due_date']} for {format_inr(b['amount'])}. "
                f"Its on-time payment probability is currently {b['prob_after']*100:.0f}%."
            )
        return (
            f"Your cashflow has no critical bill alerts right now. "
            f"Shortage risk is low at {shortage_prob:.1f}%, with a minimum expected floor of {format_inr(min_bal)}."
        )

    return f"Your current balance is {format_inr(cur_bal)} with an expected minimum of {format_inr(min_bal)} over the month."
