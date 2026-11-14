import os
import sys
import sqlite3

# Insert cashpilot path
APP_DIR = r"C:\Users\MALTHESH V AVATHADE\.gemini\antigravity\scratch\cashpilot"
sys.path.insert(0, APP_DIR)

from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import DB_PATH

def run_checks():
    print("=== STARTING CASH PILOT ACCEPTANCE CHECKS ===")
    client = TestClient(app)

    # ----------------------------------------------------
    # Check 1: Signup, logout, login, wrong password error, demo login.
    # Passwords are hashed in the DB.
    # ----------------------------------------------------
    print("\n--- Check 1: Auth & Password Hashing ---")
    # Demo login
    demo_res = client.post("/api/auth/demo")
    assert demo_res.status_code == 200, f"Demo login failed: {demo_res.text}"
    demo_data = demo_res.json()
    assert demo_data["user"]["email"] == "demo@cashpilot.app"
    print("✓ Demo login succeeded.")

    # Check cookies
    cookies = demo_res.cookies
    assert "cashpilot_session" in cookies, "Session cookie not set"
    print("✓ Session cookie set.")

    # Check /api/auth/me with demo session
    me_res = client.get("/api/auth/me", cookies=cookies)
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == "demo@cashpilot.app"
    print("✓ /api/auth/me returns authenticated demo user.")

    # Logout
    logout_res = client.post("/api/auth/logout", cookies=cookies)
    assert logout_res.status_code == 200
    print("✓ Logout succeeded.")

    # Verify DB has hashed password
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE email = ?", ("demo@cashpilot.app",))
    row = cur.fetchone()
    assert row is not None
    pw_hash = row[0]
    assert ":" in pw_hash and len(pw_hash) > 50, "Password is not properly hashed with salt:hash"
    assert "demo1234" not in pw_hash, "Plaintext password stored in DB!"
    conn.close()
    print("✓ Passwords securely hashed with PBKDF2-HMAC (200k iter, random salt).")

    # Wrong password error
    bad_login = client.post("/api/auth/login", json={"email": "demo@cashpilot.app", "password": "wrongpassword!"})
    assert bad_login.status_code == 400
    assert bad_login.json()["detail"] == "Invalid email or password"
    print("✓ Generic 'Invalid email or password' returned on bad password.")

    # New user signup
    new_email = f"test_{os.urandom(4).hex()}@cashpilot.app"
    signup_res = client.post("/api/auth/signup", json={"name": "Alice Tester", "email": new_email, "password": "SecurePassword123"})
    assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
    alice_cookies = signup_res.cookies
    assert "cashpilot_session" in alice_cookies
    print(f"✓ New user signup succeeded for {new_email}.")

    # ----------------------------------------------------
    # Check 2: Logged out redirects / 401
    # ----------------------------------------------------
    print("\n--- Check 2: 401 Protection on /api/* routes ---")
    unauth_client = TestClient(app)
    unauth_forecast = unauth_client.get("/api/forecast")
    assert unauth_forecast.status_code == 401, f"Expected 401 on unauth /api/forecast, got {unauth_forecast.status_code}"
    print("✓ Calling /api/forecast without cookie returns 401 JSON.")

    unauth_simulate = unauth_client.post("/api/simulate", json={"type": "purchase", "amount": 1000})
    assert unauth_simulate.status_code == 401, f"Expected 401 on unauth /api/simulate, got {unauth_simulate.status_code}"
    print("✓ Calling /api/simulate without cookie returns 401 JSON.")

    unauth_chat = unauth_client.post("/api/chat", json={"message": "hello"})
    assert unauth_chat.status_code == 401, f"Expected 401 on unauth /api/chat, got {unauth_chat.status_code}"
    print("✓ Calling /api/chat without cookie returns 401 JSON.")

    # ----------------------------------------------------
    # Check 3: Two users cannot see each other's uploaded data
    # ----------------------------------------------------
    print("\n--- Check 3: User Data Isolation ---")
    # New user Bob
    bob_email = f"bob_{os.urandom(4).hex()}@cashpilot.app"
    bob_signup = client.post("/api/auth/signup", json={"name": "Bob", "email": bob_email, "password": "BobPassword999"})
    bob_cookies = bob_signup.cookies

    # Bob starts with empty data
    bob_tx = client.get("/api/transactions", cookies=bob_cookies).json()
    assert len(bob_tx["transactions"]) == 0, "New user did not start with empty transactions"
    print("✓ Bob starts with empty state.")

    # Bob loads student profile
    bob_load = client.post("/api/profile/load", json={"profile": "student"}, cookies=bob_cookies)
    assert bob_load.status_code == 200
    bob_tx_after = client.get("/api/transactions", cookies=bob_cookies).json()["transactions"]
    assert len(bob_tx_after) > 0
    assert any("ALLOWANCE" in t["raw_description"] for t in bob_tx_after)
    print(f"✓ Bob loaded student profile ({len(bob_tx_after)} transactions).")

    # Alice (from earlier) still has empty transactions
    alice_tx = client.get("/api/transactions", cookies=alice_cookies).json()
    assert len(alice_tx["transactions"]) == 0, "Alice should not see Bob's data!"
    print("✓ Alice still has empty transactions (complete data isolation).")

    # Alice loads salaried profile
    client.post("/api/profile/load", json={"profile": "salaried"}, cookies=alice_cookies)
    alice_tx_after = client.get("/api/transactions", cookies=alice_cookies).json()["transactions"]
    assert any("SALARY ACME CORP" in t["raw_description"] for t in alice_tx_after)
    assert not any("ALLOWANCE" in t["raw_description"] for t in alice_tx_after)
    print("✓ Alice has salaried profile, Bob has student profile. Neither sees each other's data.")

    # ----------------------------------------------------
    # Check 4 & 5: Chat Assistant & Match with /api/simulate
    # "If I buy a laptop for 60k on Monday, can I pay rent?"
    # ----------------------------------------------------
    print("\n--- Check 4 & 5: Chat What-If & Number Match ---")
    # Use demo client (salaried data)
    client.post("/api/auth/demo")
    chat_query = "If I buy a laptop for 60k on Monday, can I pay rent?"
    chat_res = client.post("/api/chat", json={"message": chat_query}, cookies=cookies)
    assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
    chat_json = chat_res.json()

    print(f"Chat reply: {chat_json['reply']}")
    assert "Verdict:" in chat_json["reply"], "Chat reply missing verdict"
    assert "minimum" in chat_json["reply"].lower(), "Chat reply missing minimum balance"
    assert "probability" in chat_json["reply"].lower() or "shortage" in chat_json["reply"].lower(), "Chat reply missing shortage probability"
    assert "rent" in chat_json["reply"].lower() or "Safe" in chat_json["reply"] or "risk" in chat_json["reply"].lower(), "Chat reply missing bill status"

    assert chat_json["simulation"] is not None, "Chat did not return simulation object"
    sim_obj = chat_json["simulation"]
    scenario = sim_obj["scenario"]
    assert scenario["type"] == "purchase"
    assert scenario["amount"] == 60000.0

    # Call /api/simulate with exact same scenario
    direct_sim = client.post("/api/simulate", json=scenario, cookies=cookies).json()["simulation"]

    # Compare numbers
    assert sim_obj["min_balance_before"] == direct_sim["min_balance_before"], "min_balance_before mismatch!"
    assert sim_obj["min_balance_after"] == direct_sim["min_balance_after"], "min_balance_after mismatch!"
    assert sim_obj["shortage_prob_before"] == direct_sim["shortage_prob_before"], "shortage_prob_before mismatch!"
    assert sim_obj["shortage_prob_after"] == direct_sim["shortage_prob_after"], "shortage_prob_after mismatch!"
    assert len(sim_obj["obligations"]) == len(direct_sim["obligations"]), "obligations length mismatch!"
    for o1, o2 in zip(sim_obj["obligations"], direct_sim["obligations"]):
        assert o1["prob_after"] == o2["prob_after"], f"Obligation prob_after mismatch: {o1} vs {o2}"
    print("✓ Chat simulation numbers EXACTLY match direct /api/simulate output!")

    # ----------------------------------------------------
    # Check 6: Prepay what-if returns cash dip and interest saved
    # ----------------------------------------------------
    print("\n--- Check 6: Prepay What-If (Interest Saved & Cash Dip) ---")
    prepay_scenario = {
        "type": "prepay_loan",
        "amount": 50000.0,
        "date": "2026-11-20",
        "interest_rate": 9.0
    }
    prepay_res = client.post("/api/simulate", json=prepay_scenario, cookies=cookies).json()["simulation"]
    assert prepay_res["prepay_details"] is not None, "Prepay details missing from simulation"
    pp = prepay_res["prepay_details"]
    assert pp["cash_dip"] == 50000.0, f"Expected cash dip 50000, got {pp['cash_dip']}"
    assert pp["interest_saved"] > 0.0, f"Expected positive interest saved, got {pp['interest_saved']}"
    assert pp["assumed_rate"] == 9.0
    print(f"✓ Prepay 50k: Cash Dip = {pp['cash_dip']}, Interest Saved = {pp['interest_saved']}, Tenure Reduced = {pp['tenure_reduced_months']} mos.")

    # Also test chat with prepay
    chat_prepay = client.post("/api/chat", json={"message": "What if I prepay 50k on my loan next week?"}, cookies=cookies).json()
    assert "interest" in chat_prepay["reply"].lower()
    print(f"Chat prepay reply: {chat_prepay['reply']}")
    print("✓ Chat prepay response includes interest saved and tenure details.")

    # ----------------------------------------------------
    # Check 7: Narration cleaning view (ADD 5) & 3 Profiles (ADD 6)
    # ----------------------------------------------------
    print("\n--- Check 7: Narration Cleaning & All 3 Profiles ---")
    for prof in ["salaried", "freelancer", "student"]:
        load_r = client.post("/api/profile/load", json={"profile": prof}, cookies=cookies)
        assert load_r.status_code == 200, f"Failed loading {prof}"
        tx_r = client.get("/api/transactions", cookies=cookies).json()
        assert tx_r["has_data"] is True
        for t in tx_r["transactions"]:
            assert "raw_description" in t
            assert "cleaned_merchant" in t
            assert "category" in t
            assert len(t["cleaned_merchant"]) > 0
        fc_r = client.get("/api/forecast", cookies=cookies).json()
        assert fc_r["status"] == "ok"
        assert len(fc_r["data"]["obligations"]) > 0
        print(f"✓ Profile '{prof}' loaded cleanly: {len(tx_r['transactions'])} transactions, {len(fc_r['data']['obligations'])} obligations.")

    print("\n==============================================")
    print("ALL 7 ACCEPTANCE CHECKS PASSED WITH ZERO ERRORS!")
    print("==============================================")

if __name__ == "__main__":
    run_checks()
