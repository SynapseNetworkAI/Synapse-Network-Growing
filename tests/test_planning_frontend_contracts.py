from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_planning_frontend_does_not_hardcode_operator_timezone():
    planning_page = (ROOT / "dashboard/src/pages/PlanningPage.tsx").read_text()

    assert "Asia" + "/Kuala_Lumpur" not in planning_page
    assert "UTC" + "+8" not in planning_page
    assert "<time" in planning_page
    assert "dateTime" in planning_page


def test_canonical_docs_capture_planning_density_contracts():
    docs = "\n".join(
        [
            (ROOT / "docs/design-docs/planning-lifecycle-operating-manifest.md").read_text(),
            (ROOT / "docs/design-docs/system-design-principles.md").read_text(),
            (ROOT / "docs/design-docs/frontend-control-plane-figma-implementation.md").read_text(),
        ]
    )

    required_phrases = [
        "Active / Achieved / Dropped",
        "virtualized history",
        "deduped planner intercepts",
        "local time",
        "UTC",
    ]
    for phrase in required_phrases:
        assert phrase in docs
