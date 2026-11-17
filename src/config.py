"""Configuration settings for Portland Ground-Truth Pilot."""
from pathlib import Path
import os

# Load .env file safely using standard library
PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            os.environ[k.strip()] = v

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OPERATOR_CHAT_ID = int(os.getenv("TELEGRAM_OPERATOR_CHAT_ID", "0"))

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
BASE_PUBLIC_URL = os.getenv("BASE_PUBLIC_URL", f"http://{HOST}:{PORT}")

# Operational guardrails
MAX_ACTIVE_TASKS = int(os.getenv("MAX_ACTIVE_TASKS", "1"))
DAILY_DISPATCH_LIMIT = int(os.getenv("DAILY_DISPATCH_LIMIT", "3"))
TASK_EXPIRATION_MINUTES = int(os.getenv("TASK_EXPIRATION_MINUTES", "15"))
LOCATION_COOLDOWN_HOURS = int(os.getenv("LOCATION_COOLDOWN_HOURS", "12"))
CLIENT_RATE_LIMIT_MINUTES = int(os.getenv("CLIENT_RATE_LIMIT_MINUTES", "30"))

# Storage paths
DATA_DIR = PROJECT_ROOT / "data"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

PROOF_DIR = DATA_DIR / "proof"
try:
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

DB_PATH = DATA_DIR / "tasks.db"
DEMAND_LOG_PATH = DATA_DIR / "demand_research.jsonl"
