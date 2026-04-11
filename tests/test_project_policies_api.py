from server.database import ProjectPolicyRow


def test_project_policies_list_includes_default_managed_projects(synced_client):
    resp = synced_client.get("/api/project-policies")

    assert resp.status_code == 200
    payload = resp.json()
    project_keys = {item["project_key"] for item in payload}
    assert "synapse-network" in project_keys
    assert "synapse-network-growing" in project_keys
    assert "agents-memory" in project_keys
    synapse_policy = next(item for item in payload if item["project_key"] == "synapse-network")
    assert synapse_policy["autonomy_mode"] in {"observe", "recommend", "execute_with_approval", "execute_autonomously"}
    assert synapse_policy["scheduler_weight"] >= 1.0
    assert synapse_policy["max_parallel_requirements"] >= 1
    assert synapse_policy["portfolio_budget_points"] >= 20
    assert synapse_policy["capability_matrix"]["shell_access"] is True
    assert "publish" in synapse_policy["interrupt_policy"]["operator_confirmation_actions"]


def test_project_policy_can_be_updated(synced_client):
    list_resp = synced_client.get("/api/project-policies")
    policy = next(item for item in list_resp.json() if item["project_key"] == "synapse-network")

    patch_resp = synced_client.patch(
        f"/api/project-policies/{policy['id']}",
        json={
            "release_mode": "disabled",
            "autonomy_mode": "execute_autonomously",
            "allow_rebalance": True,
            "allow_preemption": True,
            "capability_matrix": {
                "shell_access": True,
                "git_read": True,
                "git_write": True,
                "git_push": True,
                "network_access": True,
                "publish": True,
            },
            "interrupt_policy": {
                "operator_confirmation_actions": ["publish"],
                "auto_pause_on_events": ["capability_denied", "policy_violation"],
                "auto_abort_on_events": ["publish_without_gate"],
            },
            "required_checks": ["pytest -q", "npm test"],
            "scheduler_weight": 1.8,
            "max_parallel_requirements": 2,
            "portfolio_budget_points": 160,
            "notes": "Tightened during validation.",
        },
    )

    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["release_mode"] == "disabled"
    assert updated["autonomy_mode"] == "execute_autonomously"
    assert updated["allow_rebalance"] is True
    assert updated["allow_preemption"] is True
    assert updated["capability_matrix"]["publish"] is True
    assert updated["interrupt_policy"]["operator_confirmation_actions"] == ["publish"]
    assert updated["required_checks"] == ["pytest -q", "npm test"]
    assert updated["scheduler_weight"] == 1.8
    assert updated["max_parallel_requirements"] == 2
    assert updated["portfolio_budget_points"] == 160
    assert updated["notes"] == "Tightened during validation."


def test_project_policy_can_be_created(synced_client):
    create_resp = synced_client.post(
        "/api/project-policies",
        json={
            "project_key": "sandbox-app",
            "display_name": "Sandbox App",
            "root_path": "/tmp/sandbox-app",
            "allowed_write_globs": ["src/**"],
            "forbidden_globs": ["secrets/**"],
            "required_checks": ["pytest -q"],
            "release_mode": "manual",
            "requires_manual_approval": True,
            "autonomy_mode": "recommend",
            "allow_rebalance": True,
            "allow_preemption": False,
            "capability_matrix": {
                "shell_access": True,
                "git_read": True,
                "git_write": True,
                "git_push": False,
                "network_access": False,
                "publish": False,
            },
            "interrupt_policy": {
                "operator_confirmation_actions": ["git_push", "publish"],
                "auto_pause_on_events": ["capability_denied"],
                "auto_abort_on_events": ["forbidden_write"],
            },
            "scheduler_weight": 1.3,
            "max_parallel_requirements": 2,
            "portfolio_budget_points": 120,
            "notes": "Temporary sandbox policy.",
        },
    )

    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["project_key"] == "sandbox-app"
    assert created["allowed_write_globs"] == ["src/**"]
    assert created["forbidden_globs"] == ["secrets/**"]
    assert created["autonomy_mode"] == "recommend"
    assert created["capability_matrix"]["git_push"] is False
    assert created["interrupt_policy"]["auto_pause_on_events"] == ["capability_denied"]
    assert created["scheduler_weight"] == 1.3
    assert created["max_parallel_requirements"] == 2
    assert created["portfolio_budget_points"] == 120


def test_planning_requires_registered_project_policy(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Unknown target project",
            "description_markdown": "Implement code in an unmanaged project.",
            "target_project_path": "/tmp/unknown-project",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")

    assert plan_resp.status_code == 400
    assert "No project policy registered" in plan_resp.json()["detail"]


def test_start_requirement_revalidates_active_project_policy(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Managed target project",
            "description_markdown": "Implement code in the managed product repo.",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == "synapse-network").first()
    assert policy is not None
    policy.status = "disabled"
    db_session.commit()

    start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 400
    assert "not active" in start_resp.json()["detail"]


def test_project_onboarding_creates_policy_and_returns_ready_checklist(synced_client, tmp_path):
    repo = tmp_path / "sandbox-app"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    docs_dir = repo / "docs"
    docs_dir.mkdir()
    entrypoint = docs_dir / "README.md"
    entrypoint.write_text("# Docs\n", encoding="utf-8")

    resp = synced_client.post(
        "/api/project-onboarding",
        json={
            "project_key": "sandbox-app",
            "display_name": "Sandbox App",
            "root_path": str(repo),
            "docs_entrypoints": [str(entrypoint)],
            "validation_commands": ["pytest -q"],
            "agents_memory_namespace": "sandbox-app",
            "auto_create_policy": True,
            "allowed_write_globs": ["src/**"],
            "forbidden_globs": [".git/**"],
            "release_mode": "manual",
            "requires_manual_approval": True,
            "notes": "Sandbox onboarding",
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["readiness_status"] == "ready"
    assert payload["readiness_score"] == 100
    assert payload["policy_id"] is not None
    assert payload["missing_items"] == []

    policies = synced_client.get("/api/project-policies").json()
    created_policy = next(item for item in policies if item["project_key"] == "sandbox-app")
    assert created_policy["required_checks"] == ["pytest -q"]


def test_project_onboarding_incomplete_project_surfaces_readiness_gaps(synced_client, tmp_path):
    repo = tmp_path / "incomplete-app"
    repo.mkdir()

    resp = synced_client.post(
        "/api/project-onboarding",
        json={
            "project_key": "incomplete-app",
            "display_name": "Incomplete App",
            "root_path": str(repo),
            "docs_entrypoints": [str(repo / "docs" / "README.md")],
            "validation_commands": [],
            "agents_memory_namespace": "",
            "auto_create_policy": False,
            "allowed_write_globs": ["src/**"],
            "forbidden_globs": [".git/**"],
            "release_mode": "manual",
            "requires_manual_approval": True,
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["readiness_status"] == "needs_setup"
    assert payload["policy_id"] is None
    assert "Git Repository" in payload["missing_items"]
    assert "Docs Entrypoints" in payload["missing_items"]
    assert "Validation Commands" in payload["missing_items"]
    assert "Project Policy" in payload["missing_items"]
