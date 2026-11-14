import os
import csv
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
    save_custom_commitment,
    delete_custom_commitment,
    get_mom_comparison,
    check_business_income_dip,
    plan_investment_goal,
    get_anomalies,
    load_user_transactions_persona,
    get_transactions_path
)

from backend.config import BASE_DIR, FRONTEND_DIR, DATA_DIR, get_data_dir

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
    # Savings transfer
    monthly_savings_amount: Optional[float] = 0.0
    monthly_savings_day: Optional[int] = None
    # Starting/Current Bank Balance
    starting_balance: Optional[float] = 0.0

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
    buffer: Optional[float] = None

class ChatModel(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None

class TransactionAddModel(BaseModel):
    date: str
    description: str
    amount: float
    type: str = "debit"

class CommitmentAddModel(BaseModel):
    name: str
    category: Optional[str] = "Other"
    amount: float
    day_of_month: Optional[int] = 5

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
    return {"status": "ok", "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}

@app.post("/api/auth/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"status": "ok", "message": "Logged out successfully"}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": user}

@app.post("/api/auth/demo")
def login_demo(response: Response):
    user = get_user_by_email("demo@cashpilot.app")
    if not user:
        user = create_user("Demo User", "demo@cashpilot.app", "demo1234")
    set_auth_cookie(response, user["id"])
    return {"status": "ok", "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}

# --- Persona & Onboarding Endpoints ---
@app.get("/api/persona")
def get_persona_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    return {
        "status": "ok",
        "active_persona": persona,
        "personas": ["salaried", "business"]
    }

@app.post("/api/persona")
def set_persona_route(data: PersonaModel, user: dict = Depends(get_current_user)):
    if data.persona not in ["salaried", "business"]:
        raise HTTPException(status_code=400, detail="Invalid persona type")
    chosen = set_active_persona(user["id"], data.persona)
    return {"status": "ok", "active_persona": chosen}

@app.get("/api/profile")
def get_profile_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    info = get_profile_data(user["id"], persona)
    return {"status": "ok", **info}

@app.post("/api/profile")
def save_profile_route(data: ProfileSaveModel, user: dict = Depends(get_current_user)):
    saved = save_profile_data(user["id"], data.persona, data.dict())
    return {"status": "ok", **saved}

# --- Statement Upload Endpoint ---
@app.post("/api/upload")
@app.post("/api/statement/upload")
async def upload_statement(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    contents = await file.read()
    res = parse_and_ingest_csv(user["id"], persona, contents)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to parse CSV statement"))
    return {"status": "ok", **res}

# --- Statement Delete / Reset Endpoint ---
@app.delete("/api/statement")
@app.delete("/api/upload")
def delete_statement_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    csv_path = get_transactions_path(user["id"], persona)
    if os.path.exists(csv_path):
        os.remove(csv_path)
    return {"status": "ok", "message": "Statement deleted successfully"}

# --- Calendar Endpoint ---
@app.get("/api/calendar")
def get_calendar_route(month: Optional[str] = None, user: dict = Depends(get_current_user)):
    from backend.calendar_service import get_calendar_data
    persona = get_active_persona(user["id"])
    data = get_calendar_data(user["id"], persona, month)
    return {"status": "ok", **data}

# --- Summary & Alerts Endpoint ---
@app.get("/api/summary")
def get_summary_route(user: dict = Depends(get_current_user)):
    from backend.calendar_service import get_calendar_data
    persona = get_active_persona(user["id"])
    cal = get_calendar_data(user["id"], persona)
    summary = cal["summary"]

    mom = get_mom_comparison(user["id"], persona)
    anomalies = get_anomalies(user["id"], persona)
    dip = check_business_income_dip(user["id"]) if persona == "business" else {"triggered": False}
    commitments = get_fixed_commitments(user["id"], persona)

    alerts = []
    for o in mom.get("overspent", []):
        alerts.append({
            "type": "overspent",
            "category": o["category"],
            "message": f"{o['category']} is over budget by ₹{int(o['over_amount']):,} ({o['over_pct']}%)"
        })
    for a in anomalies[:3]:
        alerts.append({
            "type": "anomaly",
            "message": f"Unusual spend of ₹{int(a['amount']):,} at {a['merchant']} on {a['date']}"
        })
    if dip.get("triggered"):
        alerts.append({
            "type": "income_dip",
            "message": f"Business revenue dip active! Shortfall is ₹{int(dip['shortfall']):,}."
        })

    anchor_day = 15
    for c in commitments.get("commitments", []):
        due_d = int(c.get("day_of_month", 0))
        if anchor_day <= due_d <= anchor_day + 7:
            alerts.append({
                "type": "bill_due",
                "message": f"Bill '{c['name']}' (₹{int(c['amount']):,}) due in {due_d - anchor_day} days"
            })

    return {
        "status": "ok",
        "summary": summary,
        "alerts": alerts
    }

# --- Commitments, MoM, Limits ---
@app.get("/api/commitments")
def get_commitments_route(user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    res = get_fixed_commitments(user["id"], persona)
    return {"status": "ok", **res}

@app.post("/api/commitments")
def add_commitment_route(data: CommitmentAddModel, user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    saved = save_custom_commitment(user["id"], persona, {
        "name": data.name,
        "category": data.category or "Other",
        "amount": data.amount,
        "day_of_month": data.day_of_month or 5
    })
    return {"status": "ok", "commitment": saved}

@app.delete("/api/commitments/{name}")
def delete_commitment_route(name: str, user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    success = delete_custom_commitment(user["id"], persona, name)
    return {"status": "ok", "success": success}

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

@app.get("/api/dip")
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

# --- Transactions (GET & POST) ---
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

@app.post("/api/transactions")
def add_transaction_route(data: TransactionAddModel, user: dict = Depends(get_current_user)):
    persona = get_active_persona(user["id"])
    csv_path = get_transactions_path(user["id"], persona)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    file_exists = os.path.exists(csv_path)

    amt = abs(float(data.amount))
    t_type = data.type.strip().lower()
    if t_type not in ["debit", "credit"]:
        t_type = "debit"

    cleaned = clean_description(data.description)
    cat = categorize_transaction(data.description.strip(), cleaned, amt, t_type)

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists or os.path.getsize(csv_path) == 0:
            writer.writerow(["date", "description", "cleaned_merchant", "category", "amount", "type"])
        writer.writerow([data.date.strip(), data.description.strip(), cleaned, cat, str(amt), t_type])

    return {
        "status": "ok",
        "transaction": {
            "date": data.date.strip(),
            "description": data.description.strip(),
            "cleaned_merchant": cleaned,
            "category": cat,
            "amount": amt,
            "type": t_type
        }
    }

# --- Simulator & Chat ---
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
        "name": data.name,
        "buffer": data.buffer
    }
    result = simulate_scenario(user["id"], scenario, persona)
    return {"status": "ok", "simulation": result}

@app.post("/api/chat")
def chat_route(data: ChatModel, user: dict = Depends(get_current_user)):
    res = handle_chat_message(user["id"], data.message, data.history)
    return res

# --- Static Frontend Serving ---
@app.get("/login.html")
def serve_login():
    path = os.path.join(FRONTEND_DIR, "login.html")
    if os.path.exists(path):
        return FileResponse(path)
    cwd_path = os.path.join(os.getcwd(), "frontend", "login.html")
    if os.path.exists(cwd_path):
        return FileResponse(cwd_path)
    return JSONResponse({"status": "error", "message": "login.html not found"}, status_code=404)

@app.get("/")
def serve_root():
    path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    cwd_path = os.path.join(os.getcwd(), "frontend", "index.html")
    if os.path.exists(cwd_path):
        return FileResponse(cwd_path)
    return JSONResponse({"status": "error", "message": "index.html not found"}, status_code=404)

frontend_target = FRONTEND_DIR if os.path.exists(FRONTEND_DIR) else os.path.join(os.getcwd(), "frontend")
if os.path.exists(frontend_target):
    app.mount("/", StaticFiles(directory=frontend_target, html=True), name="static")
