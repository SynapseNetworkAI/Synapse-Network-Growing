#!/usr/bin/env python3
"""Build a safe narrated screen-demo video for the SynapseNetwork workflow pack.

The generated visuals are synthetic screen-style frames, so the video can be
shared without exposing local credentials, browser sessions, or private paths.
"""

from __future__ import annotations

import json
import math
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "assets" / "recordings" / "raw"
EDITED_DIR = ROOT / "assets" / "recordings" / "edited"
FINAL_DIR = ROOT / "assets" / "final"
WORK_DIR = ROOT / "assets" / "recordings" / "_build"

WIDTH = 1920
HEIGHT = 1080
FPS = 30


@dataclass(frozen=True)
class Scene:
    key: str
    title: str
    eyebrow: str
    narration: str
    bullets: tuple[str, ...]
    terminal: tuple[str, ...] = ()


SCENES: tuple[Scene, ...] = (
    Scene(
        key="opening",
        eyebrow="SYNAPSENETWORK WORKFLOW",
        title="Building MCP/provider services with AI-native tooling",
        narration=(
            "Most MCP Server demos show the server. This video shows the workflow around the server: "
            "Claude Code, Apidog, SDK end to end tests, staging, and a publishing queue."
        ),
        bullets=(
            "Agents discover APIs",
            "Gateway handles pricing and settlement",
            "Providers execute signed requests",
        ),
        terminal=("synapse workflow demo --safe-mode", "env: staging / testnet / mock credentials"),
    ),
    Scene(
        key="workspace",
        eyebrow="WORKSPACE MAP",
        title="Each repo owns one part of the system",
        narration=(
            "The gateway is the main product. Provider exposes services. SDK is the agent integration layer. "
            "Growing is the ops console. The content pack keeps articles, scripts, recordings, and distribution notes."
        ),
        bullets=(
            "Synapse-Network: gateway, settlement, docs",
            "Synapse-Network-Provider: provider runtime",
            "Synapse-Network-Sdk: agent and owner integration",
            "Synapse-Network-Growing: ops, execution, publishing",
        ),
        terminal=("content/synapse-workflows/2026-04-mcp-server-toolchain", "video/shot-list.md", "distribution.md"),
    ),
    Scene(
        key="claude",
        eyebrow="CLAUDE CODE / CODEX LOOP",
        title="Search first, patch small, verify fast",
        narration=(
            "When I add a provider service, I do not ask the model to write random code. "
            "I ask it to search existing patterns, patch the smallest surface, add tests, and run the closest gate."
        ),
        bullets=(
            "Inspect schemas, routers, catalog, tests",
            "Make surgical changes",
            "Run source quality and unit tests",
        ),
        terminal=("rg \"provider-services\" app tests", "python scripts/ci/source_quality_checks.py", "bash scripts/ci/pr_checks.sh"),
    ),
    Scene(
        key="apidog",
        eyebrow="APIDOG CONTRACT DEBUGGING",
        title="The wire contract is the truth",
        narration=(
            "Apidog helps inspect request bodies, headers, status codes, and error responses. "
            "For paid provider services, direct anonymous calls should fail; agents should call the gateway."
        ),
        bullets=(
            "Gateway owns discovery, pricing, budgets, receipts",
            "Provider only accepts gateway-signed requests",
            "Failures stay visible at the HTTP boundary",
        ),
        terminal=("POST /api/v1/agent/invoke", "X-Synapse-Signature: <gateway-signed>", "401 if signature is missing"),
    ),
    Scene(
        key="sdk",
        eyebrow="SDK E2E",
        title="The public product test is the SDK path",
        narration=(
            "The test that matters is provider registration, gateway discovery, SDK search, SDK invoke, "
            "a gateway signed provider call, and a receipt. If that passes locally and in staging, agents can use it."
        ),
        bullets=(
            "provider ensure / register",
            "SynapseClient.search",
            "SynapseClient.invoke",
            "get invocation receipt",
        ),
        terminal=("client.search(\"deepseek chat\")", "client.invoke(service_id, payload, cost_usdc=price)", "receipt.status == \"succeeded\""),
    ),
    Scene(
        key="staging",
        eyebrow="LOCAL VS STAGING",
        title="Local is for speed. Staging is for truth.",
        narration=(
            "Local uses local URLs and local-only credentials. Staging uses protected secrets and public URLs. "
            "Provider runtime never gets owner private keys; it only gets runtime secrets and rate limits."
        ),
        bullets=(
            "No owner key inside provider runtime",
            "Secret Manager only for protected jobs",
            "Local E2E cannot read staging secrets",
        ),
        terminal=("SYNAPSE_ENV=staging", "PROVIDER_PUBLIC_BASE_URL=https://provider-staging...", "GATEWAY_PROVIDER_SIGNATURE_ENABLED=true"),
    ),
    Scene(
        key="quality",
        eyebrow="QUALITY GATES",
        title="AI-native development needs rails",
        narration=(
            "The workflow includes quality gates for typed public returns, file and function size, complexity, "
            "duplicate code, coverage, documentation consistency, and secret hygiene."
        ),
        bullets=(
            "Public APIs return objects, not raw maps",
            "Complexity and duplication are blocked",
            "Coverage proves the important paths",
        ),
        terminal=("[ci:source-quality] passed", "[ci:maintainability] passed", "Required coverage reached"),
    ),
    Scene(
        key="publishing",
        eyebrow="PUBLISHING LOOP",
        title="Debugging becomes reusable knowledge",
        narration=(
            "Long articles, scripts, screenshots, and recordings stay in git. Short social drafts go into the "
            "publishing queue, where they are reviewed before posting."
        ),
        bullets=(
            "Source content stays in content/synapse-workflows",
            "X drafts go to /publishing",
            "HN, Reddit, and V2EX are posted manually",
        ),
        terminal=("article.en.md", "x-thread.en.md -> /publishing", "distribution.md tracks final URLs"),
    ),
    Scene(
        key="closing",
        eyebrow="TAKEAWAY",
        title="Design the workflow, not just the server",
        narration=(
            "If you build MCP Servers or agent-facing API infrastructure, design the debug loop, staging proof, "
            "SDK end to end test, and publishing loop. That is what makes the system shippable."
        ),
        bullets=(
            "Observable",
            "Billable",
            "Debuggable",
            "Safe enough to run in public",
        ),
        terminal=("workflow > one-off demo", "ship the loop"),
    ),
)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


FONT_EYEBROW = font(30, bold=True)
FONT_TITLE = font(66, bold=True)
FONT_BODY = font(36)
FONT_MONO = font(30)
FONT_SMALL = font(24)


def wrap(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt: ImageFont.ImageFont) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=fnt)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, outline: str | None = None, radius: int = 28, width: int = 2) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def render_caption(draw: ImageDraw.ImageDraw, scene: Scene) -> None:
    caption_font = font(30, bold=True)
    caption_lines = wrap(draw, subtitle_text(scene), WIDTH - 360, caption_font)[:3]
    line_height = 42
    box_height = 58 + len(caption_lines) * line_height
    top = HEIGHT - box_height - 42
    draw_rounded_rect(draw, (160, top, WIDTH - 160, HEIGHT - 42), "#07110f", "#21483f", radius=28)
    draw.text((198, top + 22), "CAPTION", font=font(18, bold=True), fill="#31f1c5")
    y = top + 50
    for line in caption_lines:
        draw.text((198, y), line, font=caption_font, fill="#ffffff")
        y += line_height


def render_scene(scene: Scene, output: Path, *, captioned: bool = False) -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), "#030706")
    draw = ImageDraw.Draw(img)

    # Background grid and glow.
    for x in range(0, WIDTH, 96):
        draw.line((x, 0, x, HEIGHT), fill="#0b1513", width=1)
    for y in range(0, HEIGHT, 96):
        draw.line((0, y, WIDTH, y), fill="#0b1513", width=1)
    for r, color in [(420, "#06231d"), (300, "#08332a"), (160, "#0a4b3c")]:
        draw.ellipse((WIDTH // 2 - r, HEIGHT // 2 - r, WIDTH // 2 + r, HEIGHT // 2 + r), outline=color, width=2)

    # Top nav.
    draw_rounded_rect(draw, (110, 56, WIDTH - 110, 132), "#111817", "#33413d", radius=32)
    draw_rounded_rect(draw, (136, 76, 178, 116), "#1d2926", "#a8fff1", radius=10)
    draw.ellipse((150, 88, 162, 100), fill="#29e0bb")
    draw.text((196, 72), "Synapse", font=FONT_SMALL, fill="#ffffff")
    draw.text((196, 102), "NETWORK", font=font(16, bold=True), fill="#8fa19b")
    draw_rounded_rect(draw, (365, 78, 640, 114), "#301d20", "#6b3a3e", radius=18)
    draw.ellipse((386, 91, 400, 105), fill="#ff6b6b")
    draw.text((418, 85), "GATEWAY NODE / DEMO", font=font(18, bold=True), fill="#e7c7c7")

    # Main card.
    draw.text((180, 220), scene.eyebrow, font=FONT_EYEBROW, fill="#31f1c5")
    title_lines = wrap(draw, scene.title, 800, FONT_TITLE)
    y = 270
    for line in title_lines:
        draw.text((180, y), line, font=FONT_TITLE, fill="#ffffff")
        y += 78

    body_lines = wrap(draw, scene.narration, 800, FONT_BODY)
    y += 20
    for line in body_lines[:2]:
        draw.text((180, y), line, font=FONT_BODY, fill="#d7e2dd")
        y += 48

    # Bullet panel.
    draw_rounded_rect(draw, (180, 650, 980, 930), "#0b1110", "#1f3730", radius=28)
    draw.text((220, 690), "Workflow notes", font=font(28, bold=True), fill="#ffffff")
    by = 745
    for bullet in scene.bullets:
        draw.ellipse((224, by + 12, 238, by + 26), fill="#2de0b8")
        for line in wrap(draw, bullet, 660, font(28)):
            draw.text((260, by), line, font=font(28), fill="#c9d5d0")
            by += 38
        by += 8

    # Terminal panel.
    draw_rounded_rect(draw, (1040, 230, 1740, 930), "#060a09", "#2a3c37", radius=28)
    draw_rounded_rect(draw, (1070, 260, 1710, 310), "#121b19", "#20322e", radius=18)
    draw.ellipse((1094, 278, 1110, 294), fill="#ff6b6b")
    draw.ellipse((1122, 278, 1138, 294), fill="#f5c65b")
    draw.ellipse((1150, 278, 1166, 294), fill="#31e08f")
    draw.text((1192, 272), "synapse-demo terminal", font=font(22, bold=True), fill="#8ca49d")
    ty = 350
    for line in scene.terminal:
        draw.text((1088, ty), "$", font=FONT_MONO, fill="#2de0b8")
        for wrapped in wrap(draw, line, 560, FONT_MONO):
            draw.text((1128, ty), wrapped, font=FONT_MONO, fill="#e6fff8")
            ty += 42
        ty += 12
    draw.text((1088, 875), "No real secrets are shown in this demo.", font=FONT_SMALL, fill="#6d837b")

    # Footer.
    draw.text((180, 980), "SynapseNetwork · agent API gateway · MCP/provider workflow", font=FONT_SMALL, fill="#7a918a")
    if captioned:
        render_caption(draw, scene)
    img.save(output)


def make_audio(scene: Scene, output: Path) -> None:
    txt = WORK_DIR / f"{scene.key}.txt"
    txt.write_text(scene.narration, encoding="utf-8")
    run(["say", "-v", "Samantha", "-r", "178", "-f", str(txt), "-o", str(output)])


def duration(path: Path) -> float:
    raw = run_text([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    return float(raw)


def fmt_srt(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    h = millis // 3_600_000
    millis %= 3_600_000
    m = millis // 60_000
    millis %= 60_000
    s = millis // 1000
    ms = millis % 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def subtitle_text(scene: Scene) -> str:
    return f"{scene.title}. {scene.narration}"


def build() -> None:
    for directory in (RAW_DIR, EDITED_DIR, FINAL_DIR, WORK_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    concat_file = WORK_DIR / "segments.txt"
    captioned_concat_file = WORK_DIR / "segments-captioned.txt"
    srt_entries: list[str] = []
    concat_lines: list[str] = []
    captioned_concat_lines: list[str] = []
    current = 0.0

    for index, scene in enumerate(SCENES, start=1):
        frame = WORK_DIR / f"{index:02d}-{scene.key}.png"
        captioned_frame = WORK_DIR / f"{index:02d}-{scene.key}-captioned.png"
        audio = WORK_DIR / f"{index:02d}-{scene.key}.aiff"
        segment = WORK_DIR / f"{index:02d}-{scene.key}.mp4"
        captioned_segment = WORK_DIR / f"{index:02d}-{scene.key}-captioned.mp4"
        render_scene(scene, frame)
        render_scene(scene, captioned_frame, captioned=True)
        make_audio(scene, audio)
        scene_duration = max(duration(audio) + 0.6, 5.0)
        run([
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            str(frame),
            "-i",
            str(audio),
            "-t",
            f"{scene_duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            str(segment),
        ])
        run([
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            str(captioned_frame),
            "-i",
            str(audio),
            "-t",
            f"{scene_duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            str(captioned_segment),
        ])
        concat_lines.append(f"file '{segment}'")
        captioned_concat_lines.append(f"file '{captioned_segment}'")
        start = current
        end = current + scene_duration
        srt_entries.append(
            f"{index}\n{fmt_srt(start)} --> {fmt_srt(end)}\n{subtitle_text(scene)}\n"
        )
        current = end

    concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    captioned_concat_file.write_text("\n".join(captioned_concat_lines) + "\n", encoding="utf-8")
    raw_mov = RAW_DIR / "synapse-workflow-demo-raw.mov"
    edited_mp4 = EDITED_DIR / "synapse-workflow-demo.mp4"
    final_mp4 = FINAL_DIR / "synapse-workflow-demo.mp4"
    final_srt = FINAL_DIR / "synapse-workflow.en.srt"
    hard_sub = FINAL_DIR / "synapse-workflow-demo-subtitled.mp4"

    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(raw_mov)])
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mov),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "20",
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        str(edited_mp4),
    ])
    run(["cp", str(edited_mp4), str(final_mp4)])
    final_srt.write_text("\n".join(srt_entries), encoding="utf-8")

    # Create a burned-caption version for platforms that do not support
    # external SRT. The local ffmpeg build may not include the subtitles
    # filter, so captions are rendered into the scene frames above.
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(captioned_concat_file), "-c", "copy", str(hard_sub)])

    manifest = {
        "raw": str(raw_mov.relative_to(ROOT)),
        "edited": str(edited_mp4.relative_to(ROOT)),
        "final": str(final_mp4.relative_to(ROOT)),
        "subtitles": str(final_srt.relative_to(ROOT)),
        "burned_subtitles": str(hard_sub.relative_to(ROOT)),
        "duration_seconds": round(duration(final_mp4), 2),
        "scene_count": len(SCENES),
        "mode": "safe synthetic screen-demo with TTS narration",
    }
    (FINAL_DIR / "synapse-workflow-demo-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    build()
