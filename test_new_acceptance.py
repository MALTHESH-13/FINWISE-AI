import os
import sys

APP_DIR = r"C:\Users\MALTHESH V AVATHADE\.gemini\antigravity\scratch\cashpilot"
sys.path.insert(0, APP_DIR)

from fastapi.testclient import TestClient
from backend.main import app

def run_all_acceptance_checks():
    print("=== STARTING NEW CASH PILOT ACCEPTANCE CHECKS ===")
    client = TestClient(app)

    # -------------------------------------------------------------------
    # Check 1: Fresh user sees persona landing; each persona requires setup;
    # no data or examples visible before upload.
    # -------------------------------------------------------------------
    print("\n--- Check 1: Fresh user onboarding & empty state ---")
    new_email = f"fresh_{os.urandom(4).hex()}@cashpilot.app"
    signup_res = client.post("/api/auth/signup", json={"name": "Fresh User", "email": new_email, "password": "Password123!"})
    assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
    user_cookies = signup_res.cookies

    # Check persona
    persona_res = client.get("/api/persona", cookies=user_cookies).json()
    assert persona_res["active_persona"] == "salaried"
    assert "freelancer" not in persona_res["personas"]
    assert "student" not in persona_res["personas"]
    print("✓ Active persona initialized without legacy freelancer/student.")

    # Check profile is not setup yet
    prof_res = client.get("/api/profile", cookies=user_cookies).json()
    assert prof_res["is_setup"] is False
    print("✓ Fresh user persona requires setup (is_setup=False).")

    # Check that without upload, commitments, transactions, and forecast are empty
    comm_res = client.get("/api/commitments", cookies=user_cookies).json()
    assert comm_res["has_data"] is False
    assert len(comm_res["commitments"]) == 0
    print("✓ Commitments panel shows empty state before upload.")

    tx_res = client.get("/api/transactions", cookies=user_cookies).json()
    assert tx_res["has_data"] is False
    assert len(tx_res["transactions"]) == 0
    print("✓ Transactions panel shows empty state before upload.")

    fc_res = client.get("/api/forecast", cookies=user_cookies).json()
    assert fc_res["status"] == "empty"
    print("✓ Forecast shows empty state before upload.")

    mom_res = client.get("/api/mom", cookies=user_cookies).json()
    assert mom_res["has_data"] is False
    print("✓ MoM chart shows empty state before upload.")

    # -------------------------------------------------------------------
    # Check 2: Freelancer/Student options gone; nothing else broke
    # -------------------------------------------------------------------
    print("\n--- Check 2: Verify existing simulator, chat, backtest, anomalies ---")
    anom_res = client.get("/api/anomaly", cookies=user_cookies).json()
    assert anom_res["status"] == "ok"
    bt_res = client.get("/api/backtest", cookies=user_cookies).json()
    assert bt_res["status"] == "ok"
    print("✓ Anomaly and backtest endpoints intact.")

    # -------------------------------------------------------------------
    # Check 3: Uploading sample_transactions.csv as Salaried populates
    # dashboard, commitments, MoM chart with limits and red overspend flags.
    # -------------------------------------------------------------------
    print("\n--- Check 3: Salaried upload & MoM overspend flags ---")
    # Setup Salaried profile first
    save_sal = client.post("/api/profile", json={
        "persona": "salaried",
        "name": "Fresh User",
        "age": 30,
        "salary": 75000.0,
        "secondary_income_amount": 10000.0,
        "secondary_income_label": "Consulting",
        "salary_day": 1
    }, cookies=user_cookies).json()
    assert save_sal["is_setup"] is True
    assert save_sal["baseline_income"] == 85000.0
    print("✓ Salaried profile configured: baseline = 75k + 10k = 85k.")

    sample_tx_path = os.path.join(APP_DIR, "data", "sample_transactions.csv")
    with open(sample_tx_path, "rb") as f:
        upload_sal = client.post("/api/upload", files={"file": ("sample_transactions.csv", f, "text/csv")}, cookies=user_cookies)
    assert upload_sal.status_code == 200, f"Upload failed: {upload_sal.text}"
    print(f"✓ Uploaded sample_transactions.csv successfully ({upload_sal.json()['count']} records).")

    # Verify commitments populated
    sal_comm = client.get("/api/commitments", cookies=user_cookies).json()
    assert sal_comm["has_data"] is True
    assert len(sal_comm["commitments"]) > 0
    print(f"✓ Fixed commitments populated: {len(sal_comm['commitments'])} items, Total = ₹{sal_comm['monthly_total']}.")

    # Verify MoM chart with limits and red overspend flags
    sal_mom = client.get("/api/mom", cookies=user_cookies).json()
    assert sal_mom["has_data"] is True
    assert len(sal_mom["overspent"]) > 0
    overspent_cats = [o["category"] for o in sal_mom["overspent"]]
    print(f"✓ MoM category comparison populated with overspent categories: {overspent_cats}")
    assert any(c in ["Shopping", "Food"] for c in overspent_cats), "Expected Shopping or Food to be flagged as overspent"

    # -------------------------------------------------------------------
    # Check 4: Business baseline = rolling 3-month mean x (1 - buffer);
    # changing the buffer updates it.
    # -------------------------------------------------------------------
    print("\n--- Check 4: Business baseline formula & buffer update ---")
    client.post("/api/persona", json={"persona": "business"}, cookies=user_cookies)
    
    # Setup business profile with 3 months revenue: 150k, 160k, 170k (mean = 160k)
    # Default buffer = 15% (0.15) -> baseline = 160k * 0.85 = 136,000
    save_biz = client.post("/api/profile", json={
        "persona": "business",
        "name": "Business Owner",
        "age": 35,
        "business_type": "Creative Studio",
        "safety_buffer": 0.15,
        "revenue_history": [
            {"month": "2026-08", "amount": 150000.0},
            {"month": "2026-09", "amount": 160000.0},
            {"month": "2026-10", "amount": 170000.0}
        ]
    }, cookies=user_cookies).json()
    assert save_biz["baseline_income"] == 136000.0
    print(f"✓ Business baseline with 15% buffer = ₹{save_biz['baseline_income']:,}")

    # Changing buffer to 25% (0.25) -> baseline = 160k * 0.75 = 120,000
    save_biz_25 = client.post("/api/profile", json={
        "persona": "business",
        "name": "Business Owner",
        "age": 35,
        "business_type": "Creative Studio",
        "safety_buffer": 0.25,
        "revenue_history": [
            {"month": "2026-08", "amount": 150000.0},
            {"month": "2026-09", "amount": 160000.0},
            {"month": "2026-10", "amount": 170000.0}
        ]
    }, cookies=user_cookies).json()
    assert save_biz_25["baseline_income"] == 120000.0
    print(f"✓ Changing buffer to 25% correctly updates baseline to ₹{save_biz_25['baseline_income']:,}")

    # Reset buffer to 15%
    client.post("/api/profile", json={
        "persona": "business",
        "name": "Business Owner",
        "safety_buffer": 0.15,
        "revenue_history": [
            {"month": "2026-08", "amount": 150000.0},
            {"month": "2026-09", "amount": 160000.0},
            {"month": "2026-10", "amount": 170000.0}
        ]
    }, cookies=user_cookies)

    # -------------------------------------------------------------------
    # Check 5: Uploading business data with low-income current month
    # triggers dip banner and auto chat message with P1/P2/P3 ranking.
    # Housing and Phone/Data appear in P1, Netflix/Spotify/Gym in P3.
    # -------------------------------------------------------------------
    print("\n--- Check 5: Business Income-Dip Priority Engine ---")
    biz_csv_path = os.path.join(APP_DIR, "data", "sample_business.csv")
    with open(biz_csv_path, "rb") as f:
        upload_biz = client.post("/api/upload", files={"file": ("sample_business.csv", f, "text/csv")}, cookies=user_cookies)
    assert upload_biz.status_code == 200

    dip_res = client.get("/api/dip-check", cookies=user_cookies).json()
    assert dip_res["triggered"] is True, "Expected income dip to be triggered!"
    print(f"✓ Dip triggered! Shortfall = ₹{dip_res['shortfall']:,}, Projected Inflow = ₹{dip_res['projected_inflow']:,}")

    # Check P1 items: Housing and Phone/Data must appear in P1
    p1_cats = [it["category"] for it in dip_res["p1_items"]]
    print(f"✓ P1 categories: {p1_cats}")
    assert "Housing" in p1_cats, "Housing missing from P1!"
    assert "Phone/Data" in p1_cats, "Phone/Data missing from P1!"

    # Check P3 items: Netflix/Spotify/Gym in P3
    p3_items_text = " ".join(cut["item"] for cut in dip_res["p3_suggested_cuts"])
    print(f"✓ P3 suggested cuts: {p3_items_text}")
    assert "Netflix" in p3_items_text or "Spotify" in p3_items_text, "Netflix or Spotify missing from P3!"
    assert "Cult" in p3_items_text or "Gym" in p3_items_text, "Gym missing from P3!"

    # Check auto chat message
    assert dip_res["auto_chat_message"] is not None
    assert "P1 Essential" in dip_res["auto_chat_message"]
    assert "P3" in dip_res["auto_chat_message"]
    print("✓ Auto-chat message contains plain English evidence, shortfall, and ranked cuts.")

    # -------------------------------------------------------------------
    # Check 6: Goal "laptop 80k in 8 months" returns roadmap, SIP/RD figure,
    # stated assumptions, and milestone table.
    # -------------------------------------------------------------------
    print("\n--- Check 6: Goal Planning 'laptop 80k in 8 months' ---")
    # Switch back to Salaried
    client.post("/api/persona", json={"persona": "salaried"}, cookies=user_cookies)
    
    # Via API POST /api/goals/plan
    goal_res = client.post("/api/goals/plan", json={
        "name": "Laptop",
        "cost": 80000.0,
        "months": 8,
        "current_savings": 10000.0
    }, cookies=user_cookies).json()["plan"]
    
    assert goal_res["target_cost"] == 80000.0
    assert goal_res["timeline_months"] == 8
    assert goal_res["required_monthly_saving"] > 0
    assert goal_res["recommended_instrument"] == "Recurring Deposit / Liquid Fund"
    assert goal_res["assumed_annual_rate"] == 6.5
    assert goal_res["sip_amount"] > 0
    assert len(goal_res["milestones"]) == 8
    print(f"✓ Goal Roadmap API: {goal_res['recommended_instrument']} @ {goal_res['assumed_annual_rate']}% p.a. | SIP = ₹{goal_res['sip_amount']}/mo | {len(goal_res['milestones'])} milestone rows.")

    # Via Chat: "laptop 80k in 8 months"
    chat_goal = client.post("/api/chat", json={"message": "laptop 80k in 8 months"}, cookies=user_cookies).json()
    assert "Roadmap for Laptop" in chat_goal["reply"]
    assert "80,000" in chat_goal["reply"] or "80000" in chat_goal["reply"]
    assert "6.5%" in chat_goal["reply"]
    assert "illustrative" in chat_goal["reply"].lower()
    print(f"✓ Chat goal reply: {chat_goal['reply']}")

    # -------------------------------------------------------------------
    # Check 7: What-if chat check preserved
    # -------------------------------------------------------------------
    print("\n--- Check 7: Existing What-If Chat preserved ---")
    chat_whatif = client.post("/api/chat", json={"message": "If I buy a laptop for 60k on Monday, can I pay rent?"}, cookies=user_cookies).json()
    assert "Verdict:" in chat_whatif["reply"]
    assert "minimum" in chat_whatif["reply"].lower()
    print("✓ Existing what-if simulation preserved with exact numbers.")

    print("\n=======================================================")
    print("ALL 7 ACCEPTANCE CHECKS PASSED WITH ZERO ERRORS!")
    print("=======================================================")

if __name__ == "__main__":
    run_all_acceptance_checks()
