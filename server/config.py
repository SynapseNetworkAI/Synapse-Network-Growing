"""Centralized configuration for Synapse Ops Dashboard."""
import os
from pathlib import Path

# ── Environment ───────────────────────────────────────────────
ENV = os.environ.get("OPS_ENV", "local")  # local | prod

# ── Paths ─────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = os.environ.get("ROLES_DIR", str(PROJECT_ROOT / "roles"))

# ── Server ────────────────────────────────────────────────────
HOST = os.environ.get("OPS_HOST", "127.0.0.1" if ENV == "local" else "0.0.0.0")
PORT = int(os.environ.get("OPS_PORT", "9600"))
WORKERS = int(os.environ.get("OPS_WORKERS", "1" if ENV == "local" else "4"))
LOG_LEVEL = os.environ.get("OPS_LOG_LEVEL", "debug" if ENV == "local" else "info")
RELOAD = ENV == "local"

# ── Database ──────────────────────────────────────────────────
DB_PATH = os.environ.get("OPS_DB_PATH", str(PROJECT_ROOT / "server" / "ops.db"))
DATABASE_URL = os.environ.get("OPS_DATABASE_URL", f"sqlite:///{DB_PATH}")

# ── LLM ───────────────────────────────────────────────────────
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))
MAX_CONTEXT_SIZE = int(os.environ.get("MAX_CONTEXT_SIZE", "500000"))
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "100000"))

# ── CORS ──────────────────────────────────────────────────────
CORS_ORIGINS = os.environ.get("OPS_CORS_ORIGINS", "*").split(",")
