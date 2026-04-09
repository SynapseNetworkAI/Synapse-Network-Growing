"""FastAPI main application for Agentic Ops Dashboard."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server.config import CORS_ORIGINS, ENV, PORT, LOG_LEVEL
from server.database import init_db, get_db, AgentRow, TaskRow, ApprovalRow
from server.schemas import DashboardStats
from server.routers import agents, tasks, approvals, skills
from server.services.org_builder import build_org_tree

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ops-dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Ops Dashboard (env=%s, port=%s)", ENV, PORT)
    init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down")


app = FastAPI(title="Synapse Agentic Ops Dashboard", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(approvals.router)
app.include_router(skills.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.debug("%s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.debug("%s %s → %s", request.method, request.url.path, response.status_code)
    return response


@app.get("/api/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    return DashboardStats(
        agent_count=db.query(AgentRow).count(),
        task_total=db.query(TaskRow).count(),
        task_pending=db.query(TaskRow).filter(TaskRow.status == "pending").count(),
        task_running=db.query(TaskRow).filter(TaskRow.status.in_(["running", "pending_approval"])).count(),
        task_completed=db.query(TaskRow).filter(TaskRow.status == "completed").count(),
        task_failed=db.query(TaskRow).filter(TaskRow.status.in_(["failed", "rejected"])).count(),
        approval_pending=db.query(ApprovalRow).filter(ApprovalRow.status == "pending").count(),
    )


@app.get("/api/org")
def get_org_tree():
    """Return the full multi-project org tree."""
    return build_org_tree()


@app.get("/health")
def health():
    return {"status": "ok"}
