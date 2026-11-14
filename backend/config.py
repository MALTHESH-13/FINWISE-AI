"""
Central configuration for FinWise AI / CashPilot.
Provides portable filesystem path resolution for local dev, Docker, and Vercel/Lambda serverless.
"""
import os
import shutil
import tempfile

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

def get_data_dir() -> str:
    """
    Returns a writable directory for sqlite database, user statements, and secrets.
    On Vercel, AWS Lambda, or read-only serverless filesystems, uses tempfile directory
    and seeds sample transactions and user directories.
    """
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        target_dir = os.path.join(tempfile.gettempdir(), "cashpilot_data")
    else:
        target_dir = os.path.join(BASE_DIR, "data")
        try:
            os.makedirs(target_dir, exist_ok=True)
            test_file = os.path.join(target_dir, ".test_write")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return target_dir
        except (OSError, PermissionError):
            target_dir = os.path.join(tempfile.gettempdir(), "cashpilot_data")

    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            pass

    # Copy seed data (sample transactions, existing configs) if available in repo
    repo_data = os.path.join(BASE_DIR, "data")
    if os.path.exists(repo_data) and os.path.abspath(repo_data) != os.path.abspath(target_dir):
        try:
            for item in os.listdir(repo_data):
                s = os.path.join(repo_data, item)
                d = os.path.join(target_dir, item)
                if not os.path.exists(d):
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
        except Exception:
            pass

    return target_dir

DATA_DIR = get_data_dir()
USERS_DIR = os.path.join(DATA_DIR, "users")
