"""
Main entrypoint for FinWise AI / CashPilot.
Exposes the FastAPI instance `app` from `backend.main`.
Enables auto-detection on PaaS platforms (Koyeb, Render, Railway, Fly.io, Heroku, etc.).
"""
import os
import uvicorn
from backend.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
