"""
Alternative entrypoint alias for FinWise AI / CashPilot.
Exposes the FastAPI instance `app` from `backend.main`.
"""
from backend.main import app

__all__ = ["app"]
