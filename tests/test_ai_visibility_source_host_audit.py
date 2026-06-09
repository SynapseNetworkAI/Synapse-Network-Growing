import json
from pathlib import Path

from server.services.growth.ai_visibility_goal_audit import (
    _source_host_handoff_requirement,
    _source_host_live_requirement,
    _source_host_submission_requirement,
)
from server.services.growth.ai_visibility_source_host_audit import (
    source_host_audit_facts,
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


def _write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")
