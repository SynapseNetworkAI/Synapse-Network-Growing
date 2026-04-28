#!/usr/bin/env python3
"""Reset local Goal Mission Lanes demo data.

This is intentionally dev-only and guarded.  It is for cleaning a local
`server/ops.db` that accumulated dogfood/demo planning noise; it is not a
production migration or data management endpoint.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "server" / "ops.db"
CONFIRM = "LOCAL_MISSION_RESET"
RESET_TABLES = (
    "product_opportunities",
    "planner_sweeps",
    "requirement_candidates",
    "workflow_state_events",
    "atom_invocations",
    "workflow_artifacts",
    "blackboard_snapshots",
    "human_gate_requests",
    "workflow_runs",
    "requirement_acceptance_checks",
    "requirement_attachments",
    "requirements",
    "operating_manifests",
    "planning_goals",
)
GOAL_KEY = "synapse_public_preview_traction"
GOAL_TITLE = "Launch Synapse Network public preview and prove agent-payment traction"
GOAL_INTENT = """Synapse Network is now moving from internal dogfood toward public-preview traction.

The current company objective is to connect the main Gateway, Provider runtime, SDK, public docs/staging site, X official-account growth, releases, and the Ops control plane into one verifiable loop.

The product_planner lane discovers product gaps and creates Product Opportunities only. The growth_lead lane turns approved goals into X/social, trend, reply, repost, and conversion work. The software_engineer lane turns approved product capabilities, bugs, release gaps, and automation needs into evidence-bound Requirements and Workflow Runs.

Success means an operator can look at Command Center and immediately understand what Synapse is trying to prove, which product line owns the next step, and what evidence shows public-preview traction."""
GOAL_SUCCESS_METRIC = (
    "staging/docs/GitHub visits, provider onboarding proof, SDK demo completion, "
    "X engagement, successful staging releases, and Ops Console lane health are visible in the control plane."
)


def _opportunity(
    title: str,
    problem: str,
    why_now: str,
    evidence: list[str],
    goal_key: str,
    lane: str,
    metric: str,
    next_action: str,
    *,
    risk: str = "normal",
) -> dict[str, object]:
    return {
        "title": title,
        "problem": problem,
        "why_now": why_now,
        "evidence": evidence,
        "suggested_goal_key": goal_key,
        "recommended_lane": lane,
        "risk_level": risk,
        "success_metric": metric,
        "next_action": next_action,
    }


PRODUCT_LINE_OPPORTUNITIES = [
    _opportunity(
        "Core Gateway & Settlement public-preview proof",
        "Prove discover -> invoke -> pay -> receipt in staging.",
        "Public-preview messaging needs one reproducible product proof path.",
        [
            "Product context: settlement layer for AI agents.",
            "Gateway, settlement, SDK, provider runtime, and release records exist.",
        ],
        "core_gateway_settlement_preview",
        "software_engineer",
        "A staging smoke proves discover -> invoke -> pay -> receipt with bounded budget and visible evidence.",
        "Create an engineering goal for the end-to-end payment path.",
    ),
    _opportunity(
        "Provider Runtime self-serve onboarding path",
        "Make provider registration, staging health, release, and Gateway visibility self-serve.",
        "Provider is now a first-class release target, so onboarding is the next supply-side bottleneck.",
        [
            "Provider runtime exposes service endpoints.",
            "Successful Provider staging deployments are preserved in DeploymentRecords.",
        ],
        "provider_self_serve_onboarding",
        "software_engineer",
        "A provider can register/update a service, pass staging health, and appear through Gateway discovery.",
        "Create a provider onboarding goal and route docs/API/health gaps into software_engineer.",
    ),
    _opportunity(
        "SDK & Developer Experience quickstart",
        "Create a 5-minute Python/TypeScript quickstart with agent demo, receipt example, and troubleshooting.",
        "Public-preview conversion depends on a fast runnable proof for real agent builders.",
        [
            "SDK examples default to staging.",
            "Python and TypeScript surfaces exist for search, invoke, and receipt.",
        ],
        "sdk_developer_quickstart",
        "both",
        "A new developer completes install, service search, invocation, and receipt verification in under 5 minutes.",
        "Create a cross-lane goal: growth_lead frames the story and software_engineer fills runnable demo gaps.",
    ),
    _opportunity(
        "Growth / Social Ops conversion loop",
        "Connect X content, trend radar, repost/reply actions, and docs/staging/GitHub conversion signals.",
        "The official X account is active; the next step is proving downstream product interest.",
        [
            "X drafts, repost candidates, and reply items are preserved.",
            "Growth work remains human-gated.",
        ],
        "growth_social_conversion_loop",
        "growth_lead",
        "Daily content and published-effect metrics feed Planning with docs/staging/GitHub conversion evidence.",
        "Create a growth goal for cadence, source quality, and attribution without automatic public actions.",
    ),
    _opportunity(
        "Ops Control Plane stabilization",
        "Make Mission Board, Planning Queues, Release sync, Quality Gates, and Product Planner reliable.",
        "Autonomous work can only be trusted when the operator surface is clear and evidence-bound.",
        [
            "Mission Board and top navigation are the operating surface.",
            "Release sync and quality gates are core trust mechanisms.",
        ],
        "ops_control_plane_stabilization",
        "software_engineer",
        "Command Center shows clean active goals, lane queues, release sync status, quality gates, and unassigned red lights.",
        "Create an engineering goal for remaining control-plane reliability and UX gaps.",
    ),
    _opportunity(
        "Trust / Production Readiness governance",
        "Document Human Gate rules, rollback policy, auth/secret handling, observability, and public trust boundaries.",
        "Staging works; production cannot inherit staging shortcuts.",
        [
            "Staging deployment records prove release automation is viable.",
            "Production deploy, rollback, auth, settlement, and social actions are high-risk.",
        ],
        "trust_production_readiness",
        "both",
        "Production deploy/rollback, X public actions, OAuth/secret flows, and observability have audit evidence.",
        "Create a trust/governance goal before production promotion or higher-risk automation.",
        risk="high",
    ),
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _delete_if_table_exists(
    conn: sqlite3.Connection, table: str, where: str | None = None
) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return 0
    if table not in RESET_TABLES:
        raise ValueError(f"refusing to delete non-reset table: {table}")
    sql = f"DELETE FROM {table}"  # nosec B608 - table is restricted to RESET_TABLES.
    if where:
        sql += f" WHERE {where}"
    cursor = conn.execute(sql)
    return int(cursor.rowcount or 0)


def _ensure_product_opportunities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_opportunities (
          id INTEGER PRIMARY KEY,
          manifest_id INTEGER NOT NULL,
          converted_goal_id INTEGER,
          title TEXT NOT NULL,
          problem TEXT NOT NULL,
          why_now TEXT NOT NULL DEFAULT '',
          evidence_json TEXT NOT NULL DEFAULT '[]',
          suggested_goal_key TEXT NOT NULL,
          recommended_lane TEXT NOT NULL DEFAULT 'growth_lead',
          risk_level TEXT NOT NULL DEFAULT 'normal',
          success_metric TEXT NOT NULL DEFAULT '',
          next_action TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'proposed',
          source TEXT NOT NULL DEFAULT 'product_planning_sweep',
          created_by TEXT NOT NULL DEFAULT 'product_planner',
          reviewed_by TEXT,
          review_note TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at DATETIME NOT NULL,
          updated_at DATETIME NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_opportunities_manifest_status ON product_opportunities (manifest_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_opportunities_lane_status ON product_opportunities (recommended_lane, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_opportunities_goal_key ON product_opportunities (manifest_id, suggested_goal_key)"
    )


def _insert_seed(conn: sqlite3.Connection) -> None:
    _ensure_product_opportunities_table(conn)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "global_budget": {"daily_usd_limit": 25, "max_concurrent_workers": 2},
        "focus_weights": {
            "product_planner": 0.34,
            "growth_lead": 0.33,
            "software_engineer": 0.33,
        },
        "global_constraints": [
            "Product planner proposes only; human review creates formal goals.",
            "Public X/social actions require operator confirmation.",
            "Production deploy and rollback require Human Gate.",
            "Release records and X operating data are preserved as real company evidence.",
        ],
        "operating_model": "company_goal_without_cycle",
    }
    conn.execute(
        """
        INSERT INTO operating_manifests (
          manifest_key, version_name, cycle_label, status, active_slot, revision,
          payload_json, review_summary_json, change_log_json, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"mission-reset-{_utc_stamp()}",
            "Company Operating Plan",
            "Active",
            "active",
            "global",
            1,
            json.dumps(payload, ensure_ascii=False),
            "{}",
            "[]",
            "operator",
            now,
            now,
        ),
    )
    manifest_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO planning_goals (
          manifest_id, goal_key, title, intent_markdown, success_metric, domain,
          status, workflow_key, project_key, priority, risk_level, weight,
          acceptance_kind, execution_acceptance_steps_json, metadata_json,
          drop_decision_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            manifest_id,
            GOAL_KEY,
            GOAL_TITLE,
            GOAL_INTENT,
            GOAL_SUCCESS_METRIC,
            "company",
            "active",
            "agent_self_repair",
            "synapse-network-growing",
            "normal",
            "normal",
            1.0,
            "business",
            "[]",
            json.dumps(
                {"source": "local_mission_reset", "company_goal": True},
                ensure_ascii=False,
            ),
            "{}",
            now,
            now,
        ),
    )
    goal_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    for spec in PRODUCT_LINE_OPPORTUNITIES:
        conn.execute(
            """
            INSERT INTO product_opportunities (
              manifest_id, converted_goal_id, title, problem, why_now, evidence_json,
              suggested_goal_key, recommended_lane, risk_level, success_metric,
              next_action, status, source, created_by, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest_id,
                None,
                spec["title"],
                spec["problem"],
                spec["why_now"],
                json.dumps(spec["evidence"], ensure_ascii=False),
                spec["suggested_goal_key"],
                spec["recommended_lane"],
                spec["risk_level"],
                spec["success_metric"],
                spec["next_action"],
                "proposed",
                "local_mission_reset",
                "product_planner",
                json.dumps(
                    {"seed_goal_id": goal_id, "company_goal_key": GOAL_KEY},
                    ensure_ascii=False,
                ),
                now,
                now,
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset local Goal Mission Lanes demo data."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite ops.db")
    parser.add_argument("--confirm", default="", help=f"Required literal: {CONFIRM}")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if args.confirm != CONFIRM:
        print(f"Refusing to reset. Re-run with --confirm {CONFIRM}.")
        return 2
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1
    if db_path.name != "ops.db":
        print(f"Refusing to reset non-standard DB path: {db_path}")
        return 1

    backup = db_path.with_name(f"{db_path.name}.mission-reset-{_utc_stamp()}.bak")
    shutil.copy2(db_path, backup)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA busy_timeout=5000")
        deleted: dict[str, int] = {}
        for table in RESET_TABLES:
            deleted[table] = _delete_if_table_exists(conn, table)
        _insert_seed(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"Backed up DB to {backup}")
    print("Reset complete:")
    for table, count in deleted.items():
        if count:
            print(f"- {table}: deleted {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
