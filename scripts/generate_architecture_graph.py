from __future__ import annotations

import ast
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / ".code-review-graph"
DOCS_ASSET_PATH = ROOT / "docs" / "assets" / "growing-project-architecture.svg"
JSON_PATH = OUTPUT_DIR / "architecture-overview.json"
SVG_PATH = OUTPUT_DIR / "graph.svg"
README_PATH = OUTPUT_DIR / "README.md"


@dataclass(frozen=True)
class Subsystem:
    key: str
    label: str
    short_label: str
    description: str
    prefixes: tuple[str, ...]
    x: int
    y: int
    width: int = 240
    height: int = 104
    fill: str = "#F5F7FA"
    stroke: str = "#D0D7E2"
    band: str = "core"


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    weight: int
    kind: str
    note: str | None = None


SUBSYSTEMS = (
    Subsystem(
        key="docs_assets",
        label="Docs, Roles and Demos",
        short_label="Docs / Roles / Demos",
        description="Frontmatter docs, agent personas, review outputs, and demo flows.",
        prefixes=("docs/", "roles/", "demos/"),
        x=60,
        y=80,
        fill="#F7F6FF",
        stroke="#C9C2F3",
        band="support",
    ),
    Subsystem(
        key="automation_scripts",
        label="Automation Scripts",
        short_label="scripts/",
        description="Local start, reset, publish, and repo maintenance entry points.",
        prefixes=("scripts/",),
        x=60,
        y=250,
        fill="#FFF6EC",
        stroke="#F0C596",
        band="support",
    ),
    Subsystem(
        key="frontend_dashboard",
        label="Dashboard Frontend",
        short_label="dashboard/src",
        description="React 19 + Vite workbench pages, routing, and API client.",
        prefixes=("dashboard/src/",),
        x=350,
        y=92,
        fill="#ECF8F1",
        stroke="#9AD0AE",
        band="surface",
    ),
    Subsystem(
        key="frontend_tests",
        label="Frontend Tests",
        short_label="dashboard/tests",
        description="Vitest and Playwright coverage for the dashboard flows.",
        prefixes=("dashboard/tests/",),
        x=350,
        y=430,
        fill="#F9F2FF",
        stroke="#D4B3F8",
        band="verification",
    ),
    Subsystem(
        key="api_surface",
        label="FastAPI Surface",
        short_label="server/main.py + routers",
        description="App bootstrap, router registration, schemas, and HTTP lifecycle middleware.",
        prefixes=("server/main.py", "server/routers/", "server/schemas.py"),
        x=640,
        y=92,
        fill="#EAF2FF",
        stroke="#9BBBF7",
        band="surface",
    ),
    Subsystem(
        key="persistence",
        label="Persistence and Config",
        short_label="database / config / logging",
        description="SQLAlchemy models, runtime config, and structured ops logging.",
        prefixes=("server/database.py", "server/config.py", "server/logging_utils.py"),
        x=640,
        y=430,
        fill="#F3F5F7",
        stroke="#C4CBD4",
        band="foundation",
    ),
    Subsystem(
        key="workflow_engine",
        label="Workflow Engine",
        short_label="services/workflows + requirements",
        description="Requirement planning, orchestration, verification, and execution handoff.",
        prefixes=("server/services/workflows/", "server/services/requirements/"),
        x=930,
        y=52,
        fill="#EEF5FF",
        stroke="#A6C1F4",
        band="core",
    ),
    Subsystem(
        key="runtime_agents",
        label="Runtime and Agents",
        short_label="services/runtime + agents",
        description="Agent loading, model/runtime adapters, monitors, and session state.",
        prefixes=("server/services/runtime/", "server/services/agents/"),
        x=930,
        y=222,
        fill="#EAFBF1",
        stroke="#9FD9B4",
        band="core",
    ),
    Subsystem(
        key="project_governance",
        label="Project Governance",
        short_label="services/projects",
        description="Project center, policy resolution, onboarding, and org mapping.",
        prefixes=("server/services/projects/", "server/org-structure.yaml"),
        x=930,
        y=392,
        fill="#FFF7E9",
        stroke="#E8C98A",
        band="core",
    ),
    Subsystem(
        key="reliability_loops",
        label="Reliability and Signals",
        short_label="bugs / signals / scheduling",
        description="Bug intake, error loops, recurring workflows, and optimization signals.",
        prefixes=(
            "server/services/bugs/",
            "server/services/signals/",
            "server/services/scheduling/",
            "server/services/reviews/",
        ),
        x=1220,
        y=52,
        fill="#FFF1F1",
        stroke="#F0B6B6",
        band="core",
    ),
    Subsystem(
        key="delivery_surface",
        label="Delivery Surface",
        short_label="services/delivery",
        description="VCS delivery, pull-request sync, and deployment governance.",
        prefixes=("server/services/delivery/",),
        x=1220,
        y=222,
        fill="#F7F4FF",
        stroke="#D0C1F4",
        band="core",
    ),
    Subsystem(
        key="backend_tests",
        label="Backend Tests",
        short_label="tests/",
        description="Pytest API, workflow, delivery, and runtime verification suite.",
        prefixes=("tests/",),
        x=1220,
        y=430,
        fill="#FFF8EC",
        stroke="#EBCB97",
        band="verification",
    ),
)

SUBSYSTEM_BY_KEY = {item.key: item for item in SUBSYSTEMS}

SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".mjs",
    ".sh",
    ".txt",
    ".svg",
    ".png",
}
IGNORE_PARTS = {"__pycache__", "node_modules", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
TS_IMPORT_RE = re.compile(r"(?:import|export)\s+(?:[^'\"]+?\s+from\s+)?['\"]([^'\"]+)['\"]")

CONTEXTUAL_EDGES = (
    Edge(
        source="docs_assets",
        target="workflow_engine",
        weight=4,
        kind="contextual",
        note="Agent personas and architecture docs are consumed as execution context.",
    ),
    Edge(
        source="docs_assets",
        target="frontend_dashboard",
        weight=2,
        kind="contextual",
        note="Design docs and screenshots steer the workbench UI.",
    ),
    Edge(
        source="automation_scripts",
        target="api_surface",
        weight=3,
        kind="contextual",
        note="Local start/restart scripts bootstrap the API service.",
    ),
    Edge(
        source="frontend_dashboard",
        target="api_surface",
        weight=5,
        kind="contextual",
        note="The React workbench talks to FastAPI through /api endpoints.",
    ),
)


def rel_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_ignore(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def detect_subsystem(path: Path) -> str | None:
    relative = rel_path(path)
    for subsystem in SUBSYSTEMS:
        for prefix in subsystem.prefixes:
            normalized = prefix.rstrip("/")
            if relative == normalized or relative.startswith(prefix):
                return subsystem.key
    return None


def collect_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if should_ignore(path.relative_to(ROOT)):
            continue
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        files.append(path)
    return files


def build_python_module_index(files: Iterable[Path]) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in files:
        if path.suffix != ".py":
            continue
        relative = path.relative_to(ROOT)
        dotted = relative.with_suffix("").as_posix().replace("/", ".")
        modules[dotted] = path
        if dotted.endswith(".__init__"):
            modules[dotted[: -len(".__init__")]] = path
    return modules


def resolve_python_import(source: Path, module_name: str, level: int) -> str:
    if not level:
        return module_name

    package_parts = list(source.relative_to(ROOT).with_suffix("").parts[:-1])
    if level == 1:
        base_parts = package_parts
    else:
        keep = max(0, len(package_parts) - (level - 1))
        base_parts = package_parts[:keep]

    if module_name:
        base_parts.extend(module_name.split("."))
    return ".".join(base_parts)


def detect_import_edges(files: list[Path]) -> dict[tuple[str, str], int]:
    edges: dict[tuple[str, str], int] = {}
    module_index = build_python_module_index(files)

    for path in files:
        source_key = detect_subsystem(path)
        if source_key is None:
            continue

        if path.suffix == ".py":
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue

            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(resolve_python_import(path, node.module or "", node.level))

            for imported in imports:
                candidate = imported
                target_path: Path | None = None
                while candidate:
                    target_path = module_index.get(candidate)
                    if target_path is not None:
                        break
                    if "." not in candidate:
                        break
                    candidate = candidate.rsplit(".", 1)[0]
                if target_path is None:
                    continue

                target_key = detect_subsystem(target_path)
                if target_key and target_key != source_key:
                    edges[(source_key, target_key)] = edges.get((source_key, target_key), 0) + 1

        elif path.suffix in {".ts", ".tsx"}:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for imported in TS_IMPORT_RE.findall(content):
                if not imported.startswith("."):
                    continue
                base = (path.parent / imported).resolve()
                candidates = (
                    base,
                    base.with_suffix(".ts"),
                    base.with_suffix(".tsx"),
                    base / "index.ts",
                    base / "index.tsx",
                )
                target_path = next((item for item in candidates if item.exists()), None)
                if target_path is None:
                    continue
                target_key = detect_subsystem(target_path)
                if target_key and target_key != source_key:
                    edges[(source_key, target_key)] = edges.get((source_key, target_key), 0) + 1

    return edges


def build_node_stats(files: list[Path]) -> dict[str, dict[str, int]]:
    stats = {
        subsystem.key: {"tracked_files": 0, "python_files": 0, "ts_files": 0, "doc_files": 0}
        for subsystem in SUBSYSTEMS
    }

    for path in files:
        key = detect_subsystem(path)
        if key is None:
            continue
        stats[key]["tracked_files"] += 1
        if path.suffix == ".py":
            stats[key]["python_files"] += 1
        elif path.suffix in {".ts", ".tsx"}:
            stats[key]["ts_files"] += 1
        elif path.suffix == ".md":
            stats[key]["doc_files"] += 1

    return stats


def select_edges(import_edges: dict[tuple[str, str], int]) -> list[Edge]:
    selected: list[Edge] = []
    must_show = {
        ("api_surface", "workflow_engine"),
        ("api_surface", "project_governance"),
        ("api_surface", "reliability_loops"),
        ("api_surface", "persistence"),
        ("workflow_engine", "runtime_agents"),
        ("workflow_engine", "project_governance"),
        ("workflow_engine", "delivery_surface"),
        ("workflow_engine", "persistence"),
        ("runtime_agents", "persistence"),
        ("project_governance", "persistence"),
        ("reliability_loops", "workflow_engine"),
        ("reliability_loops", "persistence"),
        ("frontend_tests", "frontend_dashboard"),
        ("backend_tests", "api_surface"),
        ("backend_tests", "workflow_engine"),
        ("backend_tests", "runtime_agents"),
    }
    for (source, target), weight in sorted(import_edges.items(), key=lambda item: (-item[1], item[0])):
        if weight >= 6 or (source, target) in must_show:
            selected.append(Edge(source=source, target=target, weight=weight, kind="import"))

    seen = {(edge.source, edge.target, edge.kind) for edge in selected}
    for edge in CONTEXTUAL_EDGES:
        if (edge.source, edge.target, edge.kind) not in seen:
            selected.append(edge)
    return selected


def band_rectangles() -> str:
    bands = [
        (28, 42, 1494, 170, "Support and Inputs", "#FBFCFE", "#E6EBF2"),
        (28, 232, 1494, 310, "Runtime Surfaces and Core Services", "#FFFFFF", "#E6EBF2"),
        (28, 572, 1494, 96, "Verification", "#FBFCFE", "#E6EBF2"),
    ]
    parts = []
    for x, y, width, height, label, fill, stroke in bands:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="20" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x + 20}" y="{y + 28}" font-size="15" font-weight="700" fill="#28323F">{escape_xml(label)}</text>'
        )
    return "".join(parts)


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines = [words[0]]
    for word in words[1:]:
        current = lines[-1]
        if len(current) + 1 + len(word) <= width:
            lines[-1] = f"{current} {word}"
        else:
            lines.append(word)
    return lines


def node_card(subsystem: Subsystem, stats: dict[str, int]) -> str:
    header_y = subsystem.y + 24
    metric = f"{stats['tracked_files']} files"
    breakdown_parts = []
    if stats["python_files"]:
        breakdown_parts.append(f"{stats['python_files']} py")
    if stats["ts_files"]:
        breakdown_parts.append(f"{stats['ts_files']} ts")
    if stats["doc_files"]:
        breakdown_parts.append(f"{stats['doc_files']} md")
    breakdown = " | ".join(breakdown_parts) if breakdown_parts else "support assets"

    body_lines = wrap_text(subsystem.description, 36)
    tspans = []
    line_y = subsystem.y + 68
    for index, line in enumerate(body_lines[:3]):
        tspans.append(
            f'<tspan x="{subsystem.x + 18}" y="{line_y + (index * 16)}">{escape_xml(line)}</tspan>'
        )

    return f"""
    <g>
      <rect x="{subsystem.x}" y="{subsystem.y}" width="{subsystem.width}" height="{subsystem.height}" rx="18" fill="{subsystem.fill}" stroke="{subsystem.stroke}" stroke-width="2"/>
      <text x="{subsystem.x + 18}" y="{header_y}" font-size="17" font-weight="700" fill="#1E2833">{escape_xml(subsystem.label)}</text>
      <text x="{subsystem.x + 18}" y="{subsystem.y + 46}" font-size="12" fill="#546274">{escape_xml(subsystem.short_label)}</text>
      <text x="{subsystem.x + subsystem.width - 18}" y="{subsystem.y + 24}" font-size="12" font-weight="700" fill="#405067" text-anchor="end">{escape_xml(metric)}</text>
      <text x="{subsystem.x + subsystem.width - 18}" y="{subsystem.y + 42}" font-size="11" fill="#627286" text-anchor="end">{escape_xml(breakdown)}</text>
      <text font-size="12" fill="#425164">{''.join(tspans)}</text>
    </g>
    """


def edge_anchor(subsystem: Subsystem, side: str) -> tuple[float, float]:
    mid_x = subsystem.x + (subsystem.width / 2)
    mid_y = subsystem.y + (subsystem.height / 2)
    if side == "left":
        return subsystem.x, mid_y
    if side == "right":
        return subsystem.x + subsystem.width, mid_y
    if side == "top":
        return mid_x, subsystem.y
    return mid_x, subsystem.y + subsystem.height


def edge_path(edge: Edge) -> str:
    source = SUBSYSTEM_BY_KEY[edge.source]
    target = SUBSYSTEM_BY_KEY[edge.target]
    horizontal_gap = target.x - source.x
    if horizontal_gap > 0:
        start_x, start_y = edge_anchor(source, "right")
        end_x, end_y = edge_anchor(target, "left")
    elif horizontal_gap < 0:
        start_x, start_y = edge_anchor(source, "left")
        end_x, end_y = edge_anchor(target, "right")
    elif target.y > source.y:
        start_x, start_y = edge_anchor(source, "bottom")
        end_x, end_y = edge_anchor(target, "top")
    else:
        start_x, start_y = edge_anchor(source, "top")
        end_x, end_y = edge_anchor(target, "bottom")

    delta_x = end_x - start_x
    control = max(48, abs(delta_x) * 0.35)
    control_y = max(42, abs(end_y - start_y) * 0.25)
    if abs(delta_x) >= abs(end_y - start_y):
        c1_x = start_x + control if end_x >= start_x else start_x - control
        c2_x = end_x - control if end_x >= start_x else end_x + control
        c1_y = start_y
        c2_y = end_y
    else:
        c1_x = start_x
        c2_x = end_x
        c1_y = start_y + control_y if end_y >= start_y else start_y - control_y
        c2_y = end_y - control_y if end_y >= start_y else end_y + control_y

    return (
        f"M {start_x:.1f} {start_y:.1f} "
        f"C {c1_x:.1f} {c1_y:.1f}, {c2_x:.1f} {c2_y:.1f}, {end_x:.1f} {end_y:.1f}"
    )


def edge_stroke_width(weight: int, kind: str) -> float:
    if kind == "contextual":
        return 2.2
    return min(6.0, 1.2 + (weight / 10))


def render_edges(edges: list[Edge]) -> str:
    parts = []
    for edge in edges:
        stroke = "#8AA3C7" if edge.kind == "import" else "#7F63C4"
        dash = "" if edge.kind == "import" else ' stroke-dasharray="8 6"'
        opacity = "0.82" if edge.kind == "import" else "0.92"
        parts.append(
            f'<path d="{edge_path(edge)}" fill="none" stroke="{stroke}" stroke-width="{edge_stroke_width(edge.weight, edge.kind):.2f}" stroke-linecap="round" marker-end="url(#arrow-{edge.kind})" opacity="{opacity}"{dash}/>'
        )
    return "".join(parts)


def build_summary(files: list[Path], stats: dict[str, dict[str, int]], edges: list[Edge]) -> dict[str, object]:
    subsystem_rows = []
    for subsystem in SUBSYSTEMS:
        subsystem_rows.append(
            {
                "key": subsystem.key,
                "label": subsystem.label,
                "description": subsystem.description,
                "tracked_files": stats[subsystem.key]["tracked_files"],
                "python_files": stats[subsystem.key]["python_files"],
                "ts_files": stats[subsystem.key]["ts_files"],
                "doc_files": stats[subsystem.key]["doc_files"],
                "prefixes": list(subsystem.prefixes),
            }
        )

    edge_rows = []
    for edge in edges:
        row = {
            "source": edge.source,
            "target": edge.target,
            "weight": edge.weight,
            "kind": edge.kind,
        }
        if edge.note:
            row["note"] = edge.note
        edge_rows.append(row)

    return {
        "generator": "scripts/generate_architecture_graph.py",
        "style": "code-review-graph-inspired offline architecture export",
        "upstream_repository": "https://github.com/tirth8205/code-review-graph",
        "installation_status": {
            "attempted_command": "python3 -m pip download code-review-graph --no-deps -d /tmp/code-review-graph-download",
            "result": "failed",
            "reason": "sandbox shell has no outbound package index access",
        },
        "repository_root": str(ROOT),
        "tracked_source_like_files": len(files),
        "subsystems": subsystem_rows,
        "edges": edge_rows,
        "legend": {
            "solid": "import-derived dependency between grouped subsystems",
            "dashed": "contextual dependency not visible from imports alone",
        },
    }


def render_svg(stats: dict[str, dict[str, int]], edges: list[Edge]) -> str:
    cards = "".join(node_card(subsystem, stats[subsystem.key]) for subsystem in SUBSYSTEMS)
    notes = []
    for index, line in enumerate(
        (
            "Solid edges come from local Python and TypeScript import scanning.",
            "Dashed edges capture docs, prompt, and HTTP relationships that do not show up as imports.",
            "This export is written to .code-review-graph/graph.svg to mirror code-review-graph artifact layout.",
        )
    ):
        notes.append(
            f'<text x="60" y="{620 + (index * 18)}" font-size="12" fill="#526172">{escape_xml(line)}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1550" height="700" viewBox="0 0 1550 700" fill="none">
  <defs>
    <marker id="arrow-import" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#8AA3C7"/>
    </marker>
    <marker id="arrow-contextual" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#7F63C4"/>
    </marker>
    <filter id="card-shadow" x="-10%" y="-10%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#0F1720" flood-opacity="0.08"/>
    </filter>
  </defs>
  <rect width="1550" height="700" fill="#F4F7FB"/>
  <g>{band_rectangles()}</g>
  <text x="60" y="28" font-size="28" font-weight="800" fill="#1D2733">Synapse-Network-Growing Architecture Overview</text>
  <text x="60" y="50" font-size="14" fill="#506173">code-review-graph-style offline export grouped by subsystem boundaries</text>
  <g filter="url(#card-shadow)">{render_edges(edges)}{cards}</g>
  <g>
    <rect x="1256" y="578" width="266" height="82" rx="14" fill="#FFFFFF" stroke="#D9E1EB" stroke-width="1.5"/>
    <line x1="1276" y1="603" x2="1320" y2="603" stroke="#8AA3C7" stroke-width="3" stroke-linecap="round"/>
    <text x="1332" y="607" font-size="12" fill="#445368">Import-derived dependency</text>
    <line x1="1276" y1="629" x2="1320" y2="629" stroke="#7F63C4" stroke-width="3" stroke-linecap="round" stroke-dasharray="8 6"/>
    <text x="1332" y="633" font-size="12" fill="#445368">Contextual dependency</text>
  </g>
  <g>{''.join(notes)}</g>
</svg>
"""


def write_readme() -> None:
    README_PATH.write_text(
        "\n".join(
            [
                "# .code-review-graph",
                "",
                "This directory keeps the local architecture export for `Synapse-Network-Growing`.",
                "",
                "- `graph.svg`: canonical SVG architecture graph",
                "- `architecture-overview.json`: subsystem and edge summary used by the docs",
                "",
                "Regenerate with:",
                "",
                "```bash",
                "python3 scripts/generate_architecture_graph.py",
                "```",
                "",
                "The output format intentionally mirrors the artifact layout used by `code-review-graph visualize --format svg`,",
                "while staying offline-friendly for this repository's sandboxed execution environment.",
                "",
                "Direct package download was attempted with:",
                "",
                "```bash",
                "python3 -m pip download code-review-graph --no-deps -d /tmp/code-review-graph-download",
                "```",
                "",
                "That command failed because the sandbox shell cannot reach the package index, so this repository keeps",
                "an offline-compatible export instead of pretending the upstream package is installed locally.",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    files = collect_files()
    stats = build_node_stats(files)
    import_edges = detect_import_edges(files)
    selected_edges = select_edges(import_edges)
    summary = build_summary(files, stats, selected_edges)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_ASSET_PATH.parent.mkdir(parents=True, exist_ok=True)

    JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    svg = render_svg(stats, selected_edges)
    SVG_PATH.write_text(svg, encoding="utf-8")
    shutil.copyfile(SVG_PATH, DOCS_ASSET_PATH)
    write_readme()

    print(f"Wrote {SVG_PATH.relative_to(ROOT)}")
    print(f"Wrote {JSON_PATH.relative_to(ROOT)}")
    print(f"Wrote {DOCS_ASSET_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
