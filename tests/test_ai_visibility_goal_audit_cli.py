import json
import sys

from scripts.growth import generate_ai_visibility_goal_audit as cli


def test_goal_audit_cli_binds_live_readiness_and_external_gate(monkeypatch, tmp_path):
    live_path = tmp_path / "live-readiness.json"
    gate_path = tmp_path / "external-gate.json"
    output_path = tmp_path / "goal-audit.json"
    live_path.write_text(json.dumps({"status": "ready_for_external_probe"}))
    gate_path.write_text(
        json.dumps({"status": "ready_to_execute_external_probes", "feed_ready": True})
    )

    class FakeDb:
        def close(self):
            pass

    class FakeAudit:
        def model_dump(self, *, mode: str):
            assert mode == "json"
            return {
                "module_key": "ai_visibility",
                "status": "incomplete",
                "goal_achieved": False,
                "bound_live_status": "ready_for_external_probe",
                "bound_gate_status": "ready_to_execute_external_probes",
            }

    def fake_goal_audit(db, *, live_readiness=None, external_gate=None):
        assert isinstance(db, FakeDb)
        assert live_readiness == {"status": "ready_for_external_probe"}
        assert external_gate == {
            "status": "ready_to_execute_external_probes",
            "feed_ready": True,
        }
        return FakeAudit()

    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", FakeDb)
    monkeypatch.setattr(cli, "ai_visibility_goal_audit", fake_goal_audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_goal_audit.py",
            "--live-readiness-json",
            str(live_path),
            "--external-gate-json",
            str(gate_path),
            "--output",
            str(output_path),
        ],
    )

    assert cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["bound_live_status"] == "ready_for_external_probe"
    assert payload["bound_gate_status"] == "ready_to_execute_external_probes"
