import os
import sys

APP_DIR = r"C:\Users\MALTHESH V AVATHADE\.gemini\antigravity\scratch\cashpilot"
sys.path.insert(0, APP_DIR)

from fastapi.testclient import TestClient
from backend.main import app

def test_gemini_integration():
    client = TestClient(app)
    # Login as demo user
    login_res = client.post("/api/auth/demo")
    assert login_res.status_code == 200
    cookies = login_res.cookies

    # Test /api/ai/status
    status_res = client.get("/api/ai/status", cookies=cookies).json()
    print("AI Status:", status_res)
    assert status_res["status"] == "ok"
    assert status_res["enabled"] is True
    assert status_res["provider"] == "Google Gemini"

    # Test /api/ai/insights
    insights_res = client.get("/api/ai/insights", cookies=cookies).json()
    print("AI Insights count:", len(insights_res.get("insights", [])))
    print("AI Insights:", insights_res.get("insights", []))
    assert insights_res["status"] == "ok"
    assert "insights" in insights_res

    # Test Chat with Gemini
    chat_res = client.post("/api/chat", json={"message": "Can I afford to buy a bike for ₹50,000 next month?"}, cookies=cookies).json()
    print("\nChat Reply from Gemini:")
    print(chat_res["reply"])
    assert len(chat_res["reply"]) > 20
    assert chat_res.get("ai_powered") is True

    print("\n✓ All Gemini integration tests passed successfully!")

if __name__ == "__main__":
    test_gemini_integration()
