from typing import Dict, Any, Optional

def format_inr(val: float) -> str:
    val_int = int(round(val))
    neg = "-" if val_int < 0 else ""
    s = str(abs(val_int))
    if len(s) <= 3:
        return f"{neg}₹{s}"
    last_three = s[-3:]
    remaining = s[:-3]
    groups = []
    while remaining:
        groups.append(remaining[-2:])
        remaining = remaining[:-2]
    groups.reverse()
    formatted = ",".join(groups) + "," + last_three
    return f"{neg}₹{formatted}"

def explain_simulation(sim: Dict[str, Any], scenario: Dict[str, Any]) -> str:
    """
    Generates deterministic explanation using actual simulator numbers:
    - verdict: Safe / Risky / Not advisable
    - lowest running balance before vs after
    - month-end balance before vs after
    - per-bill status (Covered / Tight / Short)
    - prepay interest-saved output if applicable
    No probabilities.
    """
    verdict = sim.get("verdict", "Safe")
    lowest_before = sim.get("lowest_balance_before", 0.0)
    lowest_after = sim.get("lowest_balance_after", 0.0)
    month_end_before = sim.get("month_end_balance_before", 0.0)
    month_end_after = sim.get("month_end_balance_after", 0.0)

    # Per-bill status
    obligations = sim.get("obligations", [])
    troubled_bills = [o for o in obligations if o.get("status") in ["Tight", "Short"]]
    if troubled_bills:
        t_ob = troubled_bills[0]
        bill_text = f"Upcoming bill '{t_ob['name']}' due on {t_ob['due_date']} ({format_inr(t_ob['amount'])}) shifts to {t_ob['status']}."
    else:
        bill_text = "All scheduled obligations remain Covered."

    prepay_text = ""
    prepay_details = sim.get("prepay_details")
    if prepay_details:
        prepay_text = (
            f" Prepaying {format_inr(prepay_details['cash_dip'])} at {prepay_details['assumed_rate']}% p.a. "
            f"saves an estimated {format_inr(prepay_details['interest_saved'])} in total interest, "
            f"reducing tenure by {prepay_details['tenure_reduced_months']} months."
        )

    sentences = [
        f"Verdict: {verdict}.",
        f"Your lowest running balance shifts from {format_inr(lowest_before)} to {format_inr(lowest_after)}.",
        f"Month-end balance shifts from {format_inr(month_end_before)} to {format_inr(month_end_after)}.",
        f"{bill_text}{prepay_text}"
    ]
    return " ".join(sentences)

def explain_left_to_spend(summary: Dict[str, Any]) -> str:
    """
    Replaces 'will I run out of money' and 'safe to spend' with left to spend this month.
    """
    left = summary.get("left_to_spend", 0.0)
    bal = summary.get("balance", 0.0)
    res = summary.get("reserved_remaining", 0.0)
    buf = summary.get("buffer", 0.0)

    return (
        f"You have {format_inr(left)} left to spend this month. "
        f"Current balance is {format_inr(bal)}, with {format_inr(res)} reserved for upcoming bills "
        f"and a safety buffer of {format_inr(buf)}."
    )
