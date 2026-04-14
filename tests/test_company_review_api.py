from __future__ import annotations

import json

from server.database import ApprovalRequestRow, ArtifactRow, BugRecordRow, CompanyOperatingReviewRow, RecurringWorkflowRow, RequirementRow, TaskRow, WorkflowRunRow, WorkflowStepRow
from server.config import PROJECT_ROOT
from server.services.reviews.company_review import (
    materialize_company_review_automation_candidates,
    refresh_company_operating_review,
)


def test_company_review_refresh_serializes_workflow_ritual_datetimes(synced_client, db_session):
    synced_client.post("/api/recurring-workflows/sync")
    morning = db_session.query(RecurringWorkflowRow).filter(RecurringWorkflowRow.workflow_key == "morning_intake_sweep").first()
    assert morning is not None
    morning.last_run_at = morning.created_at
    morning.last_result_json = json.dumps(
        {
            "created_requirement_ids": [],
            "operator_attention_items": [],
            "requires_operator_review": False,
        }
    )
    db_session.add(morning)
    db_session.commit()

    review = refresh_company_operating_review(db_session)
    payload = json.loads(review.payload_json)
    assert payload["source_snapshot"]["workflow_rituals"]["morning_intake_sweep"]["last_run_at"] is not None


def test_company_review_refresh_maps_runtime_metrics_via_workflow_step_task_link(synced_client, db_session):
    requirement = RequirementRow(
        title="Gateway bug follow-up",
        description_markdown="Fix runtime bug",
        status="done",
        priority="high",
        source="bug_intake",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        current_plan_version=1,
    )
    db_session.add(requirement)
    db_session.flush()

    run = WorkflowRunRow(
        requirement_id=requirement.id,
        plan_version=1,
        status="completed",
        triggered_by="system",
    )
    db_session.add(run)
    db_session.flush()

    task = TaskRow(
        description="Implement bug fix",
        agent_id="seo_strategist",
        status="completed",
        runtime_backend="codex_cli",
        runtime_model="gpt-5-codex",
        tokens_used=321,
        budget_cost_points=17,
    )
    db_session.add(task)
    db_session.flush()

    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=requirement.id,
        step_key="implementation",
        step_type="implementation",
        title="Implement fix",
        status="completed",
        sequence_no=1,
        compatibility_task_id=task.id,
    )
    db_session.add(step)
    db_session.commit()

    review = refresh_company_operating_review(db_session)
    payload = json.loads(review.payload_json)
    assert payload["portfolio_summary"]["budget_spent_points"] >= 17
    assert payload["portfolio_summary"]["tokens_used"] >= 321


def test_company_review_aggregates_bottlenecks_incidents_and_recommendations(synced_client, db_session):
    synced_client.post("/api/recurring-workflows/sync")
    morning = db_session.query(RecurringWorkflowRow).filter(RecurringWorkflowRow.workflow_key == "morning_intake_sweep").first()
    dispatcher = db_session.query(RecurringWorkflowRow).filter(RecurringWorkflowRow.workflow_key == "dispatcher_loop").first()
    closeout = db_session.query(RecurringWorkflowRow).filter(RecurringWorkflowRow.workflow_key == "closeout_and_compact_sweep").first()
    morning.last_result_json = json.dumps({
        "created_requirement_ids": [101, 102],
        "operator_attention_items": [{"kind": "signal", "title": "Signal A"}],
        "requires_operator_review": True,
    })
    dispatcher.last_result_json = json.dumps({
        "started_ids": [201],
        "stuck_requirement_ids": [301],
        "approval_reminders": [{"approval_request_id": 1}],
        "follow_up_actions": [{"action": "approval_reminder", "requirement_id": 55}],
    })
    closeout.last_result_json = json.dumps({
        "acceptance_candidates": 2,
        "stale_requirement_ids": [401],
        "compacted_requirement_ids": [401],
        "review_snapshot_requirement_ids": [402, 403],
    })
    approval = db_session.query(RecurringWorkflowRow).filter(RecurringWorkflowRow.workflow_key == "approval_sweep").first()
    assert approval is not None
    approval.last_result_json = json.dumps({
        "auto_approved_requirement_ids": [501, 502],
        "pending_count": 2,
        "stale_approval_request_ids": [77],
        "approval_source_counts": {"auto": 2, "human": 1},
        "pending_items": [
            {"requirement_id": 88, "needs_human_gate": True},
            {"requirement_id": 89, "needs_human_gate": False},
        ],
    })

    ready_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK onboarding hardening",
            "description_markdown": "Improve the SDK onboarding automation path.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )
    ready_id = ready_resp.json()["requirement"]["id"]

    blocked_requirement = RequirementRow(
        title="Network publish blocked",
        description_markdown="Release gate is blocked.",
        status="done",
        priority="high",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        current_plan_version=1,
    )
    db_session.add(blocked_requirement)
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="delivery_state",
            content_summary="Blocked publish",
            machine_readable_payload=json.dumps({
                "publish_status": "blocked",
                "publish_blockers": ["required check pending: npm run build"],
            }),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="bug_report",
            content_summary="Critical bug in release path",
            human_readable_body="Critical bug in release path",
            machine_readable_payload=json.dumps({
                "severity": "high",
                "summary": "Release validation exploded in production-like flow.",
            }),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="bug_report",
            content_summary="Release blocker regression",
            human_readable_body="Release blocker regression",
            machine_readable_payload=json.dumps({
                "severity": "high",
                "summary": "Release blocker keeps failing validation.",
            }),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="prompt_cache_profile",
            content_summary="Prompt cache profile",
            machine_readable_payload=json.dumps({
                "cache_key": "cache-company-review",
                "cached_chars_saved": 4200,
                "deduped_binding_count": 3,
            }),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="runtime_adaptation",
            content_summary="Escalation standard -> max",
            machine_readable_payload=json.dumps({
                "adaptation_type": "escalation",
                "from_tier": "standard",
                "to_tier": "max",
            }),
        )
    )
    db_session.add_all(
        [
            BugRecordRow(
                bug_key="delivery_blocker_bug::synapse-network-sdk::fp-release-blocker",
                source_key="delivery_blocker_bug",
                source_kind="artifact",
                status="open",
                title="SDK release blocker keeps failing",
                summary="Release pipeline repeatedly fails during validation.",
                severity="critical",
                fingerprint="fp-release-blocker",
                project_key="synapse-network-sdk",
                project_root_path="/Users/cliff/workspace/agent/Synapse-Network-Sdk",
                source_ref="release:bug-1",
                occurrence_count=5,
                evidence_json=json.dumps([{"log_excerpt": "npm run build failed in release stage"}]),
                metadata_json=json.dumps({"publish_blocked": True}),
                scorecard_json=json.dumps({
                    "total": 96.0,
                    "priority": "critical",
                    "auto_intake_eligible": True,
                    "blocker_flags": ["delivery_blocker", "critical"],
                }),
            ),
            BugRecordRow(
                bug_key="workflow_incident::synapse-network-sdk::fp-runtime-chain",
                source_key="workflow_incident",
                source_kind="signal",
                status="open",
                title="Runtime chain desync",
                summary="Workflow incident keeps recurring in the runtime path.",
                severity="high",
                fingerprint="fp-runtime-chain",
                project_key="synapse-network-sdk",
                project_root_path="/Users/cliff/workspace/agent/Synapse-Network-Sdk",
                source_ref="incident:runtime-1",
                occurrence_count=3,
                evidence_json=json.dumps([{"log_excerpt": "Session not found during workflow resume"}]),
                metadata_json=json.dumps({"incident_family": "runtime_reliability"}),
                scorecard_json=json.dumps({
                    "total": 84.0,
                    "priority": "high",
                    "auto_intake_eligible": True,
                    "blocker_flags": ["workflow_incident"],
                }),
            ),
            BugRecordRow(
                bug_key="workflow_incident::multi::fp-cross-project-runtime",
                source_key="workflow_incident",
                source_kind="signal",
                status="converted",
                title="Provider auth desync",
                summary="Failure path crosses core product and provider runtime.",
                severity="high",
                fingerprint="fp-cross-project-runtime",
                project_key="synapse-network",
                project_root_path="/Users/cliff/workspace/agent/Synapse-Network",
                source_ref="incident:cross-project-1",
                occurrence_count=4,
                evidence_json=json.dumps([{"log_excerpt": "provider auth mismatch"}]),
                metadata_json=json.dumps(
                    {
                        "affected_project_keys": ["synapse-network", "synapse-network-provider"],
                        "affected_project_root_paths": [
                            "/Users/cliff/workspace/agent/Synapse-Network",
                            "/Users/cliff/workspace/agent/Synapse-Network-Provider",
                        ],
                    }
                ),
                scorecard_json=json.dumps(
                    {
                        "total": 90.0,
                        "priority": "high",
                        "auto_intake_eligible": True,
                        "blocker_flags": ["workflow_incident"],
                    }
                ),
                converted_requirement_id=ready_id,
            ),
            BugRecordRow(
                bug_key="manual_bug_report::synapse-network-sdk::fp-already-converted",
                source_key="manual_bug_report",
                source_kind="manual_input",
                status="converted",
                title="SDK onboarding validation drift",
                summary="Already converted bug requirement.",
                severity="high",
                fingerprint="fp-already-converted",
                project_key="synapse-network-sdk",
                project_root_path="/Users/cliff/workspace/agent/Synapse-Network-Sdk",
                source_ref="bug:converted-1",
                occurrence_count=2,
                evidence_json=json.dumps([{"log_excerpt": "pytest drift"}]),
                metadata_json=json.dumps({}),
                scorecard_json=json.dumps({
                    "total": 79.0,
                    "priority": "high",
                    "auto_intake_eligible": True,
                }),
                converted_requirement_id=ready_id,
            ),
        ]
    )
    review_ready_requirement = RequirementRow(
        title="Manual publish promotion",
        description_markdown="Ready to publish but still gated by operator review.",
        status="done",
        priority="high",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        current_plan_version=1,
    )
    db_session.add(review_ready_requirement)
    db_session.flush()
    run = WorkflowRunRow(
        requirement_id=review_ready_requirement.id,
        plan_version=1,
        status="paused",
        triggered_by="user",
    )
    db_session.add(run)
    db_session.flush()
    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=review_ready_requirement.id,
        step_key="implementation",
        step_type="implementation",
        title="Implement expensive branch",
        status="blocked",
        sequence_no=10,
        approval_policy_json=json.dumps({
            "approval_scope": "max_tier",
            "requires_operator_confirmation": True,
            "operator_confirmation_actions": ["shell_access", "git_write"],
        }),
        execution_profile_json=json.dumps({
            "complexity_tier": "max",
        }),
        file_scope_json="{}",
        validation_targets_json="[]",
        failure_policy_json="{}",
        context_policy_json="{}",
        done_when_markdown="done",
    )
    db_session.add(step)
    db_session.flush()
    db_session.add(
        ApprovalRequestRow(
            requirement_id=review_ready_requirement.id,
            workflow_run_id=run.id,
            step_id=step.id,
            approval_type="step_operator_confirmation",
            status="pending",
            reviewer="operator",
            comment="max-tier branch requires operator confirmation",
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=review_ready_requirement.id,
            workflow_run_id=run.id,
            artifact_type="delivery_state",
            content_summary="Review-ready publish",
            machine_readable_payload=json.dumps({
                "publish_status": "review_ready",
                "requires_manual_approval": True,
                "publish_blockers": [],
            }),
        )
    )
    db_session.commit()

    review_resp = synced_client.get("/api/company-review")

    assert review_resp.status_code == 200
    payload = review_resp.json()
    assert payload["title"] == "Company Operating Review"
    assert payload["portfolio_summary"]["open_signals"] >= 1
    assert payload["portfolio_summary"]["budget_spent_points"] >= 0
    assert payload["portfolio_summary"]["prompt_cache_saved_chars"] >= 4200
    assert payload["portfolio_summary"]["escalations"] >= 1
    assert payload["portfolio_summary"]["completion_rate"] >= 0
    assert payload["portfolio_summary"]["human_gate_hotspots"] >= 1
    assert payload["portfolio_summary"]["open_bug_pressure"] >= 2
    assert payload["portfolio_summary"]["unresolved_critical_bugs"] >= 1
    assert payload["portfolio_summary"]["bug_requirements_created"] >= 1
    assert payload["portfolio_summary"]["recurring_bug_fingerprint_count"] >= 2
    assert set(payload["portfolio_summary"]["tier_mix"].keys()) >= {"mini", "standard", "max"}
    assert any(item["project_key"] == "synapse-network-sdk" for item in payload["project_highlights"])
    assert any(item["prompt_cache_saved_chars"] >= 4200 for item in payload["project_highlights"])
    assert any(item["escalations"] >= 1 for item in payload["project_highlights"])
    assert any(item["open_bug_count"] >= 2 for item in payload["project_highlights"])
    assert any(item["critical_bug_count"] >= 1 for item in payload["project_highlights"])
    assert any(item["converted_bug_count"] >= 1 for item in payload["project_highlights"])
    assert any(item["recurring_bug_count"] >= 1 for item in payload["project_highlights"])
    assert payload["recurring_bug_fingerprints"]
    assert any(item["severity"] == "critical" for item in payload["recurring_bug_fingerprints"])
    assert any(item["fingerprint"] == "fp-release-blocker" for item in payload["recurring_bug_fingerprints"])
    assert payload["portfolio_summary"]["cross_project_bug_recoveries"] >= 1
    assert payload["cross_project_bug_recoveries"]
    assert any(item["incident_family"] == "cross_project_bug_recovery" for item in payload["cross_project_bug_recoveries"])
    assert any(item["requirement_id"] == ready_id for item in payload["cross_project_bug_recoveries"])
    assert payload["human_gate_hotspots"]
    assert any(item["approval_scope"] in {"max_tier", "publish"} for item in payload["human_gate_hotspots"])
    assert payload["automation_candidates"]
    assert any(item["automation_type"] in {"max_tier_branch_reduction", "publish_automation"} for item in payload["automation_candidates"])
    assert any("publish gate is blocked" in item["title"] for item in payload["bottlenecks"])
    assert any(item.get("incident_code") for item in payload["incidents"])
    assert any("Verification incident" in item["title"] for item in payload["incidents"])
    assert any(item.get("incident_family") for item in payload["incidents"])
    assert any(item.get("project_display_name") for item in payload["incidents"])
    assert payload["next_cycle_requirement_bundle"]
    assert payload["operator_review_package"]["title"] == "Operator Review Package"
    assert payload["operator_review_package"]["recommended_bundle_item_keys"]
    assert payload["operator_review_package"]["autonomous_decision_count"] >= 1
    assert "Morning intake attention items" in payload["operator_review_package"]["summary_markdown"]
    assert "Dispatcher approval reminders" in payload["operator_review_package"]["summary_markdown"]
    assert all(
        str(item.get("severity") or "") in {"high", "critical"}
        for item in payload["operator_review_package"]["decisions"]
    )
    assert all(
        str(item.get("decision_type") or "") != "closeout_followthrough"
        for item in payload["operator_review_package"]["decisions"]
    )
    assert payload["autonomous_coo_posture"]["operator_only_high_risk"] is True
    assert payload["autonomous_coo_posture"]["auto_approved_requirement_count"] == 2
    assert payload["autonomous_coo_posture"]["stale_approval_count"] == 1
    assert payload["autonomous_coo_posture"]["pending_human_gate_count"] == 1
    assert payload["autonomous_coo_posture"]["high_risk_decision_count"] == len(payload["operator_review_package"]["decisions"])
    assert "approval_sweep" in payload["autonomous_coo_posture"]["autonomous_workflow_keys"]
    assert payload["source_snapshot"]["workflow_rituals"]["morning_intake_sweep"]["requires_operator_review"] is True
    assert payload["source_snapshot"]["workflow_rituals"]["dispatcher_loop"]["stuck_requirement_count"] >= 1
    assert payload["source_snapshot"]["workflow_rituals"]["closeout_and_compact_sweep"]["review_snapshot_count"] >= 2
    assert payload["source_snapshot"]["workflow_rituals"]["approval_sweep"]["auto_approved_count"] == 2
    assert payload["source_snapshot"]["bug_backlog_summary"]["open_bug_pressure"] >= 2
    assert any(
        item["source_ref"] in {f"requirement:{ready_id}", None} or item["project_key"] == "synapse-network-sdk"
        for item in payload["next_cycle_recommendations"]
    )
    assert any(
        item.get("candidate_type") == "incident" and item.get("incident_code")
        for item in payload["next_cycle_recommendations"]
    )


def test_company_review_refresh_persists_new_snapshot(synced_client, db_session):
    first = refresh_company_operating_review(db_session)
    second = refresh_company_operating_review(db_session)

    assert second.id > first.id

    rows = db_session.query(CompanyOperatingReviewRow).order_by(CompanyOperatingReviewRow.id.asc()).all()
    assert len(rows) >= 2

    latest = synced_client.get("/api/company-review")
    assert latest.status_code == 200
    assert latest.json()["id"] == rows[-1].id


def test_company_review_materialize_bundle_creates_and_reuses_requirements(synced_client, db_session):
    ready_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK onboarding hardening",
            "description_markdown": "Improve the SDK onboarding automation path.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )
    ready_id = ready_resp.json()["requirement"]["id"]

    blocked_requirement = RequirementRow(
        title="Network publish blocked",
        description_markdown="Release gate is blocked.",
        status="done",
        priority="high",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        current_plan_version=1,
    )
    db_session.add(blocked_requirement)
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="delivery_state",
            content_summary="Blocked publish",
            machine_readable_payload=json.dumps({
                "publish_status": "blocked",
                "publish_blockers": ["required check pending: npm run build"],
            }),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=blocked_requirement.id,
            artifact_type="bug_report",
            content_summary="Release blocker regression",
            human_readable_body="Release blocker regression",
            machine_readable_payload=json.dumps({
                "severity": "high",
                "summary": "Release blocker keeps failing validation.",
            }),
        )
    )
    db_session.commit()

    review = synced_client.get("/api/company-review").json()
    assert any(
        str(item.get("source_ref") or "").startswith("incident:")
        for item in review["next_cycle_requirement_bundle"]
    )

    materialize_resp = synced_client.post(
        f"/api/company-review/{review['id']}/materialize-bundle",
        json={},
    )
    assert materialize_resp.status_code == 200
    materialized = materialize_resp.json()
    assert materialized["review_id"] == review["id"]
    assert materialized["reused_requirement_ids"]
    assert materialized["created_requirement_ids"]
    assert any(item["status"] == "created" for item in materialized["items"])
    assert any(item["status"] == "linked_existing" for item in materialized["items"])
    second_resp = synced_client.post(
        f"/api/company-review/{review['id']}/materialize-bundle",
        json={},
    )
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    assert second_payload["created_requirement_ids"] == []
    assert any(item["status"] == "already_exists" for item in second_payload["items"])


def test_company_review_materializes_approval_automation_into_control_plane_repo(synced_client, db_session):
    review = CompanyOperatingReviewRow(
        cycle_label="2026-W16",
        summary_markdown="approval automation candidate",
        payload_json=json.dumps(
            {
                "automation_candidates": [
                    {
                        "candidate_key": "automation:stale_memory_review::expensive_branches_only::implementation::synapse-network",
                        "title": "Approval Automation: Synapse-Network - Automate gate: Synapse-Network expensive_branches_only",
                        "project_key": "synapse-network",
                        "project_display_name": "Synapse-Network",
                        "priority": "normal",
                        "automation_type": "context_refresh_automation",
                        "occurrence_count": 1,
                        "rationale": "Narrow repeated stale-memory manual gate handling.",
                        "gate_key": "stale_memory_review::expensive_branches_only::implementation::synapse-network",
                    }
                ],
                "operator_review_package": {"title": "Cycle review package"},
            }
        ),
    )
    db_session.add(review)
    db_session.commit()

    result = materialize_company_review_automation_candidates(db_session, review_id=review.id)
    assert result.created_requirement_ids

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == result.created_requirement_ids[0]).first()
    assert requirement is not None
    assert requirement.target_project_path == str(PROJECT_ROOT)
    intake = json.loads(requirement.intake_metadata_json or "{}")
    assert intake["source_key"] == "automation_candidate"
