#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "docs" / "assets" / "declarative-agent-workflow-factory-architecture.svg"
PNG_ASSET_PATH = ROOT / "docs" / "assets" / "declarative-agent-workflow-factory-architecture.png"


@dataclass(frozen=True)
class Box:
    key: str
    title: str
    lines: tuple[str, ...]
    x: int
    y: int
    w: int = 300
    h: int = 140
    fill: str = "#FFFFFF"
    stroke: str = "#CBD5E1"


BOXES = {
    "operator": Box(
        key="operator",
        title="Human Operator",
        lines=("Desired state", "Manual intent", "Approval decisions"),
        x=90,
        y=150,
        fill="#FFF7ED",
        stroke="#FDBA74",
    ),
    "manifest": Box(
        key="manifest",
        title="Control Manifest",
        lines=("Targets", "Budgets", "Risk policy"),
        x=470,
        y=150,
        fill="#FFF7ED",
        stroke="#FDBA74",
    ),
    "signals": Box(
        key="signals",
        title="External Signals",
        lines=("Logs and metrics", "GitHub events", "Discord, X, analytics"),
        x=850,
        y=150,
        fill="#FFF7ED",
        stroke="#FDBA74",
    ),
    "watcher": Box(
        key="watcher",
        title="Watcher",
        lines=("Detect drift", "Route signals", "Create requirement"),
        x=1230,
        y=150,
        fill="#EEF6FF",
        stroke="#93C5FD",
    ),
    "requirement": Box(
        key="requirement",
        title="Requirement",
        lines=("Acceptance brief", "Project policy", "Target repo"),
        x=90,
        y=430,
        fill="#F0FDF4",
        stroke="#86EFAC",
    ),
    "factory": Box(
        key="factory",
        title="Workflow Factory",
        lines=("Select workflow key", "Create run", "Initialize blackboard"),
        x=470,
        y=430,
        fill="#F0FDF4",
        stroke="#86EFAC",
    ),
    "definition": Box(
        key="definition",
        title="Workflow Definition",
        lines=("State machine YAML", "Atom bindings", "Loop guards"),
        x=850,
        y=430,
        fill="#F0FDF4",
        stroke="#86EFAC",
    ),
    "validator": Box(
        key="validator",
        title="Spec Validator",
        lines=("Schema checks", "Terminal states", "High risk gates"),
        x=1230,
        y=430,
        fill="#F0FDF4",
        stroke="#86EFAC",
    ),
    "run": Box(
        key="run",
        title="Workflow Run",
        lines=("Current state", "Retry counters", "Resolution"),
        x=90,
        y=710,
        fill="#F8FAFC",
        stroke="#94A3B8",
    ),
    "runner": Box(
        key="runner",
        title="State Machine Runner",
        lines=("Owns control flow", "Evaluates transitions", "Controls retry budget"),
        x=470,
        y=710,
        fill="#F8FAFC",
        stroke="#94A3B8",
    ),
    "blackboard": Box(
        key="blackboard",
        title="Blackboard",
        lines=("Shared run context", "Inputs and outputs", "Evidence pointers"),
        x=850,
        y=710,
        fill="#F8FAFC",
        stroke="#94A3B8",
    ),
    "registry": Box(
        key="registry",
        title="Atom Registry",
        lines=("Deterministic atoms", "Agent atoms", "Gate and delivery atoms"),
        x=1230,
        y=710,
        fill="#F8FAFC",
        stroke="#94A3B8",
    ),
    "deterministic": Box(
        key="deterministic",
        title="Deterministic Atom",
        lines=("Read logs", "Run commands", "Parse schemas"),
        x=90,
        y=990,
        w=280,
        fill="#F5F3FF",
        stroke="#C4B5FD",
    ),
    "agent": Box(
        key="agent",
        title="Agent Atom",
        lines=("Diagnose", "Patch", "Generate copy"),
        x=405,
        y=990,
        w=280,
        fill="#F5F3FF",
        stroke="#C4B5FD",
    ),
    "harness": Box(
        key="harness",
        title="Harness Verification",
        lines=("Run required checks", "Collect command logs", "Record evidence"),
        x=720,
        y=990,
        w=280,
        fill="#F5F3FF",
        stroke="#C4B5FD",
    ),
    "gate": Box(
        key="gate",
        title="Risk Evidence Gate",
        lines=("Auto flow", "Human required", "Funds always gated"),
        x=1035,
        y=990,
        w=280,
        fill="#FEF2F2",
        stroke="#FCA5A5",
    ),
    "delivery": Box(
        key="delivery",
        title="Delivery Atom",
        lines=("Commit", "Push branch", "Create draft PR"),
        x=1350,
        y=990,
        w=280,
        fill="#F5F3FF",
        stroke="#C4B5FD",
    ),
    "db": Box(
        key="db",
        title="Postgres / SQLite",
        lines=("workflow_runs", "state_events", "artifacts"),
        x=90,
        y=1260,
        fill="#ECFEFF",
        stroke="#67E8F9",
    ),
    "evidence": Box(
        key="evidence",
        title="Run Evidence",
        lines=("blackboard snapshots", "atom invocations", "human gate requests"),
        x=470,
        y=1260,
        fill="#ECFEFF",
        stroke="#67E8F9",
    ),
    "console": Box(
        key="console",
        title="Ops Console",
        lines=("Overview", "Steps", "Evidence, Gates, Debug"),
        x=850,
        y=1260,
        fill="#ECFEFF",
        stroke="#67E8F9",
    ),
    "github": Box(
        key="github",
        title="GitHub",
        lines=("Branches", "Draft PRs", "Reviews"),
        x=1230,
        y=1260,
        fill="#F1F5F9",
        stroke="#94A3B8",
    ),
    "target": Box(
        key="target",
        title="Target Projects",
        lines=("Synapse Network", "SDK", "Provider"),
        x=1230,
        y=1430,
        fill="#F1F5F9",
        stroke="#94A3B8",
    ),
}


EDGES = (
    ("operator", "manifest", "sets"),
    ("manifest", "watcher", "targets"),
    ("signals", "watcher", "events"),
    ("watcher", "requirement", "creates"),
    ("requirement", "factory", "submit"),
    ("factory", "definition", "loads"),
    ("definition", "validator", "validate"),
    ("validator", "run", "start"),
    ("run", "runner", "execute"),
    ("runner", "blackboard", "read/write"),
    ("runner", "registry", "dispatch"),
    ("registry", "deterministic", "atom"),
    ("registry", "agent", "atom"),
    ("registry", "harness", "atom"),
    ("registry", "gate", "atom"),
    ("registry", "delivery", "atom"),
    ("runner", "db", "events"),
    ("blackboard", "evidence", "snapshots"),
    ("db", "console", "timeline"),
    ("evidence", "console", "inspect"),
    ("delivery", "github", "PR"),
    ("delivery", "target", "branch"),
    ("harness", "target", "verify"),
)


def esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def box_center(box: Box) -> tuple[float, float]:
    return box.x + box.w / 2, box.y + box.h / 2


def anchor(box: Box, target: Box) -> tuple[float, float, float, float]:
    sx, sy = box_center(box)
    tx, ty = box_center(target)
    dx = tx - sx
    dy = ty - sy
    if abs(dx) > abs(dy):
        start_x = box.x + box.w if dx > 0 else box.x
        start_y = sy
        end_x = target.x if dx > 0 else target.x + target.w
        end_y = ty
    else:
        start_x = sx
        start_y = box.y + box.h if dy > 0 else box.y
        end_x = tx
        end_y = target.y if dy > 0 else target.y + target.h
    return start_x, start_y, end_x, end_y


def draw_box(box: Box) -> str:
    lines = [
        f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" rx="24" fill="{box.fill}" stroke="{box.stroke}" stroke-width="3"/>',
        f'<text x="{box.x + 28}" y="{box.y + 42}" font-size="28" font-weight="800" fill="#0F172A">{esc(box.title)}</text>',
    ]
    for index, line in enumerate(box.lines):
        lines.append(
            f'<text x="{box.x + 28}" y="{box.y + 78 + index * 28}" font-size="21" fill="#475569">{esc(line)}</text>'
        )
    return "\n".join(lines)


def draw_edge(source_key: str, target_key: str, label: str) -> str:
    source = BOXES[source_key]
    target = BOXES[target_key]
    sx, sy, ex, ey = anchor(source, target)
    dx = ex - sx
    dy = ey - sy
    if abs(dx) > abs(dy):
        c1x = sx + dx * 0.45
        c1y = sy
        c2x = ex - dx * 0.45
        c2y = ey
    else:
        c1x = sx
        c1y = sy + dy * 0.45
        c2x = ex
        c2y = ey - dy * 0.45
    lx = (sx + ex) / 2
    ly = (sy + ey) / 2 - 8
    return "\n".join(
        [
            f'<path d="M {sx:.1f} {sy:.1f} C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f}, {ex:.1f} {ey:.1f}" fill="none" stroke="#64748B" stroke-width="3" marker-end="url(#arrow)" opacity="0.72"/>',
            f'<rect x="{lx - 78:.1f}" y="{ly - 22:.1f}" width="156" height="32" rx="16" fill="#FFFFFF" opacity="0.92"/>',
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="17" text-anchor="middle" fill="#334155">{esc(label)}</text>',
        ]
    )


def layer_label(text: str, x: int, y: int, w: int, h: int, fill: str) -> str:
    return "\n".join(
        [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="34" fill="{fill}" stroke="#E2E8F0" stroke-width="2"/>',
            f'<text x="{x + 28}" y="{y + 44}" font-size="24" font-weight="800" fill="#334155">{esc(text)}</text>',
        ]
    )


def render() -> str:
    layers = "\n".join(
        [
            layer_label("1. Signals and Intent", 60, 100, 1540, 230, "#FFFDF7"),
            layer_label("2. Requirement and Factory", 60, 380, 1540, 230, "#F7FFF9"),
            layer_label("3. Runtime Control Plane", 60, 660, 1540, 230, "#F8FAFC"),
            layer_label("4. Execution Atoms", 60, 940, 1540, 230, "#FAF8FF"),
            layer_label("5. Persistence and Observability", 60, 1210, 1160, 230, "#F0FDFF"),
            layer_label("6. External Systems", 1210, 1210, 390, 400, "#F8FAFC"),
        ]
    )
    edges = "\n".join(draw_edge(*edge) for edge in EDGES)
    boxes = "\n".join(draw_box(box) for box in BOXES.values())
    legend = """
    <rect x="90" y="1625" width="1200" height="82" rx="24" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="2"/>
    <text x="120" y="1661" font-size="24" font-weight="800" fill="#0F172A">Boundary rule</text>
    <text x="320" y="1661" font-size="21" fill="#475569">Agent writes structured outputs. Runner changes state. High-risk actions stop at human gate.</text>
    <text x="120" y="1693" font-size="18" fill="#64748B">Generated by scripts/generate_declarative_workflow_architecture.py</text>
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1680" height="1740" viewBox="0 0 1680 1740" fill="none">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748B"/>
    </marker>
    <filter id="softShadow" x="-10%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#0F172A" flood-opacity="0.08"/>
    </filter>
  </defs>
  <rect width="1680" height="1740" fill="#F8FAFC"/>
  <text x="80" y="54" font-size="38" font-weight="900" fill="#0F172A">Declarative Agent Workflow Factory Architecture</text>
  <text x="80" y="90" font-size="22" fill="#475569">YAML rail, Agent engine, Blackboard memory, State Machine control, Human gate safety.</text>
  {layers}
  <g>{edges}</g>
  <g filter="url(#softShadow)">{boxes}</g>
  {legend}
</svg>
"""


def main() -> None:
    ASSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASSET_PATH.write_text(render(), encoding="utf-8")
    print(f"Wrote {ASSET_PATH.relative_to(ROOT)}")
    if shutil.which("sips"):
        subprocess.run(
            ["sips", "-s", "format", "png", str(ASSET_PATH), "--out", str(PNG_ASSET_PATH)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Wrote {PNG_ASSET_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
