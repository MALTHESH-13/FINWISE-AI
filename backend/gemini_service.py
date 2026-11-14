import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.persona import (
    get_active_persona,
    get_profile_data,
    load_user_transactions_persona,
    get_fixed_commitments,
    get_mom_comparison,
    check_business_income_dip
)
from backend.simulator import get_forecast

# Preferred fast & reliable Gemini models in order
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest"
]

def get_gemini_api_key() -> str:
    """
    Retrieves Gemini API key safely from environment or local git-ignored data/.gemini_key
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key

    key_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".gemini_key")
    if os.path.exists(key_file):
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass

    return ""

def is_gemini_configured() -> bool:
    key = get_gemini_api_key()
    return bool(key and len(key) > 10)

def call_gemini(
    prompt: str,
    system_instruction: Optional[str] = None,
    max_tokens: int = 350,
    temperature: float = 0.4,
    timeout_seconds: float = 8.0
) -> Optional[str]:
    """
    Calls Google Gemini API via standard library urllib with zero external dependencies.
    Tries preferred models and returns None on any network/timeout error to allow graceful fallback.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return None

    full_prompt = prompt
    if system_instruction:
        full_prompt = f"System Instruction:\n{system_instruction}\n\nTask:\n{prompt}"

    payload = {
        "contents": [{
            "parts": [{"text": full_prompt}]
        }],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    encoded_data = json.dumps(payload).encode("utf-8")

    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=encoded_data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                return text
        except urllib.error.HTTPError as e:
            if e.code in (404, 400):
                continue
            return None
        except Exception:
            return None

    return None

def build_user_financial_context(user_id: int) -> str:
    """
    Constructs a concise summary of the user's real cashflow state.
    """
    persona = get_active_persona(user_id)
    profile = get_profile_data(user_id, persona)
    baseline = profile.get("baseline_income", 0.0)

    commitments_data = get_fixed_commitments(user_id, persona)
    commitments_total = commitments_data.get("total_monthly", 0.0)
    top_commitments = [
        f"{c['name']} (₹{int(c['amount']):,}, due {c.get('next_due', 'N/A')})"
        for c in commitments_data.get("commitments", [])[:4]
    ]

    forecast = get_forecast(user_id, persona)
    min_bal = forecast.get("min_balance", 0.0)
    shortage_p = forecast.get("shortage_prob", 0.0)

    mom = get_mom_comparison(user_id, persona)
    current_spending = sum(mom.get("current_month_spending", []))
    surplus = max(0.0, baseline - current_spending)

    context_lines = [
        f"Persona: {'Salaried Professional' if persona == 'salaried' else 'Small Business Owner'}",
        f"Configured Baseline Income: ₹{int(baseline):,}/month",
        f"Recent Monthly Spending: ₹{int(current_spending):,}/month",
        f"Estimated Surplus: ₹{int(surplus):,}/month",
        f"Fixed Commitments Total: ₹{int(commitments_total):,}/month" + (f" ({', '.join(top_commitments)})" if top_commitments else ""),
        f"Projected 30-Day Min Balance: ₹{int(min_bal):,}",
        f"Shortage Risk Probability: {round(shortage_p * 100, 1)}%"
    ]

    if persona == "business":
        dip = check_business_income_dip(user_id)
        if dip.get("triggered"):
            context_lines.append(
                f"Business Alert: Inflow dip active. Shortfall: ₹{int(dip['shortfall']):,}. "
                f"Projected: ₹{int(dip['projected_inflow']):,}. Safety buffer: {int(dip['safety_buffer'] * 100)}%."
            )

    return "\n".join(context_lines)

def generate_gemini_chat_reply(
    user_id: int,
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
    """
    Answers user cashflow, financial advisory, and what-if questions using Google Gemini,
    grounded in the user's real cashflow numbers.
    """
    context = build_user_financial_context(user_id)
    system_instruction = (
        "You are FinWise/CashPilot's AI Financial Advisor powered by Google Gemini. "
        "You provide actionable, data-backed advice using the user's real cashflow context. "
        "Style Guidelines:\n"
        "1. Keep answers concise (2 to 4 sentences).\n"
        "2. Directly reference specific amounts in ₹ (Indian Rupee) and days/dates from the user context.\n"
        "3. Provide clear verdicts (Safe / Risky / Caution) and practical suggestions.\n"
        "4. Do NOT hallucinate financial data not present in the context."
    )

    history_text = ""
    if conversation_history:
        recent = conversation_history[-3:]
        history_text = "\nRecent Conversation:\n" + "\n".join(
            f"{msg.get('role', 'User')}: {msg.get('content', '')}"
            for msg in recent
        ) + "\n"

    prompt = (
        f"CURRENT USER CASHFLOW DATA:\n{context}\n"
        f"{history_text}\n"
        f"USER INQUIRY: \"{user_message}\"\n\n"
        f"Provide your concise, data-driven financial advice:"
    )

    return call_gemini(prompt, system_instruction=system_instruction, max_tokens=280)

def generate_gemini_smart_insights(user_id: int) -> Optional[List[Dict[str, str]]]:
    """
    Analyzes the user's spending and forecasts to generate 3 smart, bulleted insights.
    """
    context = build_user_financial_context(user_id)
    system_instruction = (
        "You are CashPilot's AI Financial Auditor powered by Google Gemini. "
        "Generate exactly 3 short, high-impact financial insights for the user's dashboard. "
        "Output MUST be valid JSON array of 3 objects, each with 'title', 'tag' ('Safe'|'Warning'|'Tip'), and 'description'."
    )

    prompt = (
        f"USER CASHFLOW DATA:\n{context}\n\n"
        "Generate 3 strategic insights in valid JSON format only, like:\n"
        '[{"title":"Buffer Health","tag":"Safe","description":"Your baseline income covers all fixed commitments with ₹X surplus."}, ...]'
    )

    raw_json = call_gemini(prompt, system_instruction=system_instruction, max_tokens=350, temperature=0.2)
    if not raw_json:
        return None

    try:
        clean_text = raw_json.strip()
        if clean_text.startswith("```"):
            clean_text = clean_text.split("```")[1]
            if clean_text.startswith("json"):
                clean_text = clean_text[4:].strip()
        parsed = json.loads(clean_text)
        if isinstance(parsed, list) and len(parsed) >= 1:
            return parsed[:3]
    except Exception:
        pass

    return None
