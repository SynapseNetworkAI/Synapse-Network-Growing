"""FastAPI main application for Agentic Ops Dashboard."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server.database import init_db, get_db, AgentRow, TaskRow, ApprovalRow
from server.schemas import DashboardStats
from server.routers import agents, tasks, approvals


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Synapse Agentic Ops Dashboard", version="0.1.0", lifespan=lifespan)

from server.config import CORS_ORIGINS

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


@app.get("/health")
def health():
    return {"status": "ok"}
