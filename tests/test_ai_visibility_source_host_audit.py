import json
from pathlib import Path

from server.services.growth.ai_visibility_goal_audit import (
    _source_host_handoff_requirement,
    _source_host_live_requirement,
    _source_host_submission_requirement,
)
from server.services.growth.ai_visibility_source_host_audit import (
    merge_source_host_audit_facts,
    source_host_audit_facts,
    source_host_checklist_facts,
)
from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)


def test_source_host_audit_distinguishes_submission_from_live(tmp_path: Path):
    _write_json(
        tmp_path / "source-host-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "items": [
                {
                    "host": "aitoolnet.com",
                    "design_handoff_frame": "Directory Source-Host Submission Pack",
                    "submission_confirmation_command": (
                        "python scripts/growth/record_ai_visibility_source_host_execution.py "
                        "--evidence-mode submission-confirmation"
                    ),
                },
                {
                    "host": "alternativeto.net",
                    "design_handoff_frame": "Directory Source-Host Submission Pack",
                    "submission_confirmation_command": (
                        "python scripts/growth/record_ai_visibility_source_host_execution.py "
                        "--evidence-mode submission-confirmation"
                    ),
                },
            ],
        },
    )
    _write_json(
        tmp_path / "aitoolnet-submission.json",
        {
            "module_key": "ai_visibility_source_host_execution",
            "status": "submission_recorded",
            "evidence_type": "submission_confirmation",
            "surface": "aitoolnet",
        },
    )
    _write_json(
        tmp_path / "alternativeto-live.json",
        {
            "module_key": "ai_visibility_source_host_execution",
            "status": "live_verified",
            "surface": "alternativeto",
        },
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)
    handoff = _source_host_handoff_requirement(facts)
    submission = _source_host_submission_requirement(facts)
    live = _source_host_live_requirement(facts)

    assert facts.framed_checklist_hosts == ["aitoolnet.com", "alternativeto.net"]
    assert facts.submitted_or_live_surfaces == ["aitoolnet", "alternativeto"]
    assert handoff.status == "completed"
    assert submission.status == "completed"
    assert live.status == "blocked"
    assert "aitoolnet.com" in live.blocker
    assert "Directory submission is not enough" in live.blocker


def test_source_host_audit_uses_latest_checklist_for_required_hosts(tmp_path: Path):
    _write_json(
        tmp_path
        / "2026-06-09-after-provider-key-refresh-source-host-execution-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "items": [
                _checklist_item("aitoolnet.com", priority=1),
                _checklist_item("alternativeto.net", priority=2),
            ],
        },
    )
    _write_json(
        tmp_path
        / "2026-06-09-after-zshrc-provider-keys-source-host-execution-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "items": [
                _checklist_item("mcp.directory", priority=1),
                _checklist_item("alternativeto.net", priority=3),
                _checklist_item("mcp-marketplace.io", priority=7),
            ],
        },
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)
    submission = _source_host_submission_requirement(facts)

    assert facts.required_directory_hosts == ["mcp.directory", "alternativeto.net"]
    assert "mcp.directory" in submission.blocker
    assert "alternativeto.net" in submission.blocker
    assert "aitoolnet.com" not in submission.blocker
    assert "mcp-marketplace.io" not in submission.blocker


def test_source_host_audit_surfaces_submission_blocker_without_counting_submitted(
    tmp_path: Path,
):
    _write_json(
        tmp_path / "source-host-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "items": [
                _checklist_item("alternativeto.net", priority=1),
            ],
        },
    )
    _write_json(
        tmp_path / "alternativeto-submission-blocked.json",
        {
            "module_key": "ai_visibility_source_host_execution",
            "evidence_type": "submission_blocker",
            "status": "submission_blocked",
            "surface": "alternativeto",
            "blocker": "AlternativeTo presented Cloudflare security verification.",
            "next_action": "Use an operator-owned browser/account.",
        },
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)
    submission = _source_host_submission_requirement(facts)

    assert facts.submitted_or_live_surfaces == []
    assert facts.submission_blockers == [
        (
            "alternativeto: AlternativeTo presented Cloudflare security "
            "verification. Next action: Use an operator-owned browser/account."
        )
    ]
    assert submission.status == "blocked"
    assert "Known submission blocker" in submission.blocker
    assert "Cloudflare security verification" in submission.blocker
    assert "operator-owned browser/account" in submission.next_action


def test_source_host_audit_tracks_review_pending_without_counting_live(
    tmp_path: Path,
):
    _write_json(
        tmp_path / "source-host-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "items": [
                _checklist_item("mcp.directory", priority=1),
            ],
        },
    )
    _write_json(
        tmp_path / "mcp-directory-submission.json",
        {
            "module_key": "ai_visibility_source_host_execution",
            "evidence_type": "submission_confirmation",
            "status": "submission_recorded",
            "surface": "mcp_directory",
            "submitted_payload_summary": (
                "The API returned 409: This repository has already been "
                "submitted. We'll review it soon."
            ),
        },
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)
    submission = _source_host_submission_requirement(facts)
    live = _source_host_live_requirement(facts)

    assert facts.submitted_or_live_surfaces == ["mcp_directory"]
    assert facts.review_pending_surfaces == ["mcp_directory"]
    assert submission.status == "completed"
    assert live.status == "blocked"
    assert "Review pending after submission: mcp_directory" in live.blocker
    assert "Recheck review-pending directory listings" in live.next_action
    assert "after public listing evidence is live" in live.next_action


def test_source_host_audit_reports_completed_hosts_while_staying_fail_closed(
    tmp_path: Path,
):
    _write_json(
        tmp_path / "source-host-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "items": [
                _checklist_item("mcp.directory", priority=1),
                _checklist_item("alternativeto.net", priority=2),
            ],
        },
    )
    _write_json(
        tmp_path / "mcp-directory-submission.json",
        {
            "module_key": "ai_visibility_source_host_execution",
            "evidence_type": "submission_confirmation",
            "status": "submission_recorded",
            "surface": "mcp_directory",
            "submitted_payload_summary": (
                "This repository has already been submitted. We'll review it soon."
            ),
        },
    )
    _write_json(
        tmp_path / "protodex-live.json",
        {
            "module_key": "ai_visibility_source_host_execution",
            "status": "live_verified",
            "surface": "protodex",
        },
    )
    _write_json(
        tmp_path / "pulsemcp-live.json",
        {
            "module_key": "ai_visibility_source_host_execution",
            "status": "live_verified",
            "surface": "pulsemcp",
        },
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)
    submission = _source_host_submission_requirement(facts)
    live = _source_host_live_requirement(facts)

    assert submission.status == "blocked"
    assert (
        submission.evidence
        == "Submitted or live surfaces: mcp_directory, protodex, pulsemcp."
    )
    assert "alternativeto.net" in submission.blocker
    assert live.status == "blocked"
    assert live.evidence == "Live source-host listings verified: protodex, pulsemcp."
    assert "Review pending after submission: mcp_directory" in live.blocker
    assert "Already live source-hosts: protodex, pulsemcp" in live.blocker
    assert "do not repeat completed hosts" in live.blocker
    assert "Submit or record remaining directory evidence for: alternativeto.net" in (
        live.next_action
    )


def test_source_host_audit_prefers_generated_at_over_filename_order(tmp_path: Path):
    _write_json(
        tmp_path
        / "2026-06-09-after-zshrc-provider-keys-source-host-execution-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "generated_at": "2026-06-09T05:57:06.274286Z",
            "items": [
                _checklist_item("mcp.directory", priority=1),
                _checklist_item("alternativeto.net", priority=2),
            ],
        },
    )
    _write_json(
        tmp_path
        / "2026-06-09-after-challenge-failclosed-refresh5-source-host-execution-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "generated_at": "2026-06-09T11:45:47.309958Z",
            "items": [
                _checklist_item("alternativeto.net", priority=1),
                _checklist_item("mcpservers.org", priority=2),
                _checklist_item("glama.ai", priority=3),
            ],
        },
    )

    facts = source_host_audit_facts(evidence_dir=tmp_path)
    submission = _source_host_submission_requirement(facts)

    assert facts.required_directory_hosts == [
        "alternativeto.net",
        "mcpservers.org",
        "glama.ai",
    ]
    assert "mcpservers.org" in submission.blocker
    assert "glama.ai" in submission.blocker
    assert "mcp.directory" not in submission.blocker


def test_source_host_audit_merge_prefers_archived_checklist_over_generated_db_facts(
    tmp_path: Path,
):
    _write_json(
        tmp_path / "2026-06-09-refresh5-source-host-execution-checklist.json",
        {
            "module_key": "ai_visibility",
            "checklist_type": "source_host_feed_execution",
            "generated_at": "2026-06-09T11:45:47.309958Z",
            "items": [
                _checklist_item("alternativeto.net", priority=1),
                _checklist_item("mcpservers.org", priority=2),
            ],
        },
    )

    db_facts = source_host_checklist_facts(
        _Checklist(
            [
                _ChecklistItem("mcp.directory", 1),
                _ChecklistItem("alternativeto.net", 2),
            ]
        )
    )
    archived_facts = source_host_audit_facts(evidence_dir=tmp_path)
    merged = merge_source_host_audit_facts(db_facts, archived_facts)

    assert merged.required_directory_hosts == [
        "alternativeto.net",
        "mcpservers.org",
    ]


def test_source_host_surface_uses_precise_directory_keys():
    assert source_host_surface("mcp.directory") == "mcp_directory"
    assert source_host_surface("https://mcp.directory/submit") == "mcp_directory"
    assert source_host_surface("chat.mcp.so") == "chat_mcp_so"
    assert source_host_surface("https://chat.mcp.so/") == "chat_mcp_so"
    assert source_host_surface("dock0.dev") == "dock0_dev"
    assert source_host_surface("mcpfind.org") == "mcpfind"
    assert source_host_surface("https://mcpfind.org/submit") == "mcpfind"
    assert source_host_surface("mcp-marketplace.io") == "mcp_marketplace"
    assert source_host_surface("lobehub.com") == "lobehub"
    assert (
        source_host_surface(
            "https://lobehub.com/mcp/synapsenetworkai-synapse-network-mcp-server"
        )
        == "lobehub"
    )
    assert source_host_surface("protodex.io") == "protodex"
    assert source_host_surface("https://protodex.io/submit.html") == "protodex"
    assert source_host_surface("pulsemcp.com") == "pulsemcp"
    assert source_host_surface("https://www.pulsemcp.com/servers/synapse-network") == (
        "pulsemcp"
    )
    assert source_host_surface("alternativeto.net") == "alternativeto"


def _checklist_item(host: str, *, priority: int) -> dict:
    return {
        "host": host,
        "priority": priority,
        "design_handoff_frame": "Directory Source-Host Submission Pack",
        "submission_confirmation_command": (
            "python scripts/growth/record_ai_visibility_source_host_execution.py "
            "--evidence-mode submission-confirmation"
        ),
    }


def _write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


class _Checklist:
    def __init__(self, items: list["_ChecklistItem"]):
        self.items = items


class _ChecklistItem:
    host: str
    priority: int
    design_handoff_frame = "Directory Source-Host Submission Pack"
    submission_confirmation_command = (
        "python scripts/growth/record_ai_visibility_source_host_execution.py "
        "--evidence-mode submission-confirmation"
    )

    def __init__(self, host: str, priority: int):
        self.host = host
        self.priority = priority
