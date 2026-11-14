import os
import shutil
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.auth import (
    init_db,
    create_user,
    get_user_by_email,
    verify_password,
    set_auth_cookie,
    clear_auth_cookie,
    get_current_user,
    check_rate_limit,
    record_failed_attempt,
    clear_failed_attempts,
    validate_auth_input,
    DATA_DIR
)
from backend.categorizer import clean_description, categorize_transaction
from backend.simulator import (
    load_user_transactions,
    get_forecast,
    simulate_scenario,
    get_user_csv_path
)
from backend.chat import handle_chat_message, get_auto_dip_chat_message
from backend.persona import (
    get_active_persona,
    set_active_persona,
    get_profile_data,
    save_profile_data,
    get_user_limits,
    save_user_limits,
    parse_and_ingest_csv,
    get_fixed_commitments,
    get_mom_comparison,
    check_business_income_dip,
    plan_investment_goal,
    get_anomalies,
    get_backtest_accuracy,
    load_user_transactions_persona
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI(title="CashPilot")

@app.on_event("startup")
def on_startup():
    init_db()

# --- Auth Pydantic Schemas ---
class SignupModel(BaseModel):
    name: str
    email: str
    password: str

class LoginModel(BaseModel):
    email: str
    password: str

class PersonaModel(BaseModel):
    persona: str

class ProfileSaveModel(BaseModel):
    persona: str
    name: str
    age: Optional[Any] = None
    # Salaried fields
    salary: Optional[float] = 0.0
    secondary_income_amount: Optional[float] = 0.0
    secondary_income_label: Optional[str] = ""
    salary_day: Optional[int] = 1
    # Business fields
    business_type: Optional[str] = ""
    safety_buffer: Optional[float] = 0.15
    revenue_history: Optional[List[Dict[str, Any]]] = None

class LimitsModel(BaseModel):
    limits: Dict[str, float]

class GoalPlanModel(BaseModel):
    name: str
    cost: float
    months: int
    current_savings: Optional[float] = 0.0
    annual_return: Optional[float] = None

class SimulateModel(BaseModel):
    type: str
    amount: float
    date: Optional[str] = None
    interest_rate: Optional[float] = 9.0
    name: Optional[str] = None

class ChatModel(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None

# --- Auth Endpoints (unprotected) ---
@app.post("/api/auth/signup")
def signup(data: SignupModel, response: Response):
    validate_auth_input(data.email, data.password, is_signup=True, name=data.name)
    existing = get_user_by_email(data.email.strip().lower())
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = create_user(data.name.strip(), data.email.strip().lower(), data.password)
    set_auth_cookie(response, user["id"])
    return {"status": "ok", "user": user}

@app.post("/api/auth/login")
def login(data: LoginModel, response: Response):
    email_clean = data.email.strip().lower()
    validate_auth_input(email_clean, data.password, is_signup=False)
    check_rate_limit(email_clean)

    user = get_user_by_email(email_clean)
    if not user or not verify_password(data.password, user["password_hash"]):
        record_failed_attempt(email_clean)
        raise HTTPException(status_code=400, detail="Invalid email or password")

    clear_failed_attempts(email_clean)
    set_auth_cookie(response, user["id"])
    return {
        "status": "ok",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]}
    }

@app.post("/api/auth/demo")
def demo_login(response: Response):
    user = get_user_by_email("demo@cashpilot.app")
    if not user:
        raise HTTPException(status_code=500, detail="Demo account not seeded")
    set_auth_cookie(response, user["id"])
    return {
        "status": "ok",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]}
    }

@app.post("/api/auth/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"status": "ok", "message": "Logged out successfully"}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": user}

# --- Persona & Onboarding Routes ---
@app.get("/api/persona")
def get_persona_route(user: dict = Depends(get_current_user)):
    p = get_active_persona(user["id"])
    return {"status": "ok", "active_persona": p, "personas": ["salaried", "business"]}

@app.post("/api/persona")
def set_persona_route(data: PersonaModel, user: dict = Depends(get_current_user)):
    p = set_active_persona(user["id"], data.persona)
    return {"status": "ok", "active_persona": p}

@app.get("/api/profile")
def get_profile_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    info = get_profile_data(user["id"], persona)
    return {"status": "ok", **info}

@app.post("/api/profile")
def save_profile_route(data: ProfileSaveModel, user: dict = Depends(get_current_user)):
    persona = data.persona.strip().lower()
    profile_dict = {
        "name": data.name,
        "age": data.age,
        "salary": data.salary,
        "secondary_income_amount": data.secondary_income_amount,
        "secondary_income_label": data.secondary_income_label,
        "salary_day": data.salary_day,
        "business_type": data.business_type,
        "safety_buffer": data.safety_buffer,
        "revenue_history": data.revenue_history or []
    }
    updated = save_profile_data(user["id"], persona, profile_dict)
    return {"status": "ok", **updated}

@app.post("/api/upload")
async def upload_csv_route(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    persona = get_active_persona(user["id"])
    contents = await file.read()
    result = parse_and_ingest_csv(user["id"], persona, contents)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Error parsing CSV"))
    return result

# --- Commitments, MoM, Limits ---
@app.get("/api/commitments")
def get_commitments_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    res = get_fixed_commitments(user["id"], persona)
    return {"status": "ok", **res}

@app.get("/api/mom")
def get_mom_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    res = get_mom_comparison(user["id"], persona)
    return {"status": "ok", **res}

@app.get("/api/limits")
def get_limits_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    limits = get_user_limits(user["id"], persona)
    return {"status": "ok", "limits": limits}

@app.post("/api/limits")
def set_limits_route(data: LimitsModel, user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    updated = save_user_limits(user["id"], persona, data.limits)
    return {"status": "ok", "limits": updated}

# --- Goals & Priority Engine ---
@app.post("/api/goals/plan")
def plan_goal_route(data: GoalPlanModel, user: dict = Depends(get_current_user)):
    plan = plan_investment_goal(
        user_id=user["id"],
        name=data.name,
        cost=data.cost,
        months=data.months,
        current_savings=data.current_savings or 0.0,
        custom_return=data.annual_return
    )
    return {"status": "ok", "plan": plan}

@app.get("/api/dip-check")
def dip_check_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    if persona != "business":
        return {"status": "ok", "triggered": False, "message": "Not applicable for Salaried"}
    res = check_business_income_dip(user["id"])
    auto_msg = get_auto_dip_chat_message(user["id"])
    return {"status": "ok", **res, "auto_chat_message": auto_msg}

@app.get("/api/anomaly")
def anomaly_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    anomalies = get_anomalies(user["id"], persona)
    return {"status": "ok", "anomalies": anomalies}

@app.get("/api/backtest")
def backtest_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    bt = get_backtest_accuracy(user["id"], persona)
    return {"status": "ok", "backtest": bt}

# --- Transactions, Forecast, Simulator, Chat ---
@app.get("/api/transactions")
def get_transactions(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    records = load_user_transactions_persona(user["id"], persona)
    output = []
    for r in records:
        output.append({
            "date": r["date"],
            "raw_description": r["description"],
            "cleaned_merchant": r["cleaned_merchant"],
            "category": r["category"],
            "amount": r["amount"],
            "type": r["type"]
        })
    return {"status": "ok", "transactions": output, "has_data": len(output) > 0}

@app.get("/api/forecast")
def forecast_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    records = load_user_transactions_persona(user["id"], persona)
    if not records:
        return {"status": "empty", "message": "No transactions loaded"}
    res = get_forecast(user["id"], persona)
    return {"status": "ok", "data": res}

@app.post("/api/simulate")
def simulate_route(data: SimulateModel, user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    records = load_user_transactions_persona(user["id"], persona)
    if not records:
        raise HTTPException(status_code=400, detail="Please upload a statement to simulate scenarios")
    scenario = {
        "type": data.type,
        "amount": data.amount,
        "date": data.date,
        "interest_rate": data.interest_rate or 9.0,
        "name": data.name
    }
    result = simulate_scenario(user["id"], scenario, persona)
    return {"status": "ok", "simulation": result}

@app.post("/api/chat")
def chat_route(data: ChatModel, user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    records = load_user_transactions_persona(user["id"], persona)
    if not records and "laptop" not in data.message.lower() and "plan" not in data.message.lower():
        return {
            "reply": "Please complete your profile setup and upload a statement to run personalized simulations and forecasting.",
            "simulation": None,
            "intent": "empty_state"
        }
    res = handle_chat_message(user["id"], data.message, data.history)
    return res

# --- Static Frontend Serving ---
@app.get("/login.html")
def serve_login():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

@app.get("/")
def serve_root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
