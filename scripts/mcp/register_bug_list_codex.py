#!/usr/bin/env python3
"""Register the repo Bug List skill and MCP server with local Codex."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.mcp.bug_list_env import _read_dotenv_values  # noqa: E402

SKILL_NAME = "bug-list-agent"
MCP_NAME = "synapse-bug-list"
MCP_SCRIPT = REPO_ROOT / "scripts" / "mcp" / "bug_list_server.py"
REPO_SKILL_DIR = REPO_ROOT / ".agents" / "skills" / SKILL_NAME
CODEX_SKILLS_DIR = Path.home() / ".codex" / "skills"
DOTENV_PATH = REPO_ROOT / ".env"


def _append_dotenv_token(path: Path, key: str, value: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    path.write_text(f"{existing}{prefix}{key}={value}\n", encoding="utf-8")


def _resolve_token(token_env: str, *, dry_run: bool) -> tuple[str, bool]:
    token = os.environ.get(token_env, "").strip() or _read_dotenv_values(
        DOTENV_PATH
    ).get(token_env, "")
    if token:
        return token, False
    generated = secrets.token_urlsafe(32)
    if not dry_run:
        _append_dotenv_token(DOTENV_PATH, token_env, generated)
    return generated, True


def _remove_existing_skill_path(destination: Path) -> None:
    if destination.is_dir() and not destination.is_symlink():
        shutil.rmtree(destination)
        return
    destination.unlink()


def _prepare_skill_destination(
    destination: Path, *, force: bool, dry_run: bool
) -> str | None:
    if not (destination.exists() or destination.is_symlink()):
        return None
    if destination.is_symlink() and destination.resolve() == REPO_SKILL_DIR.resolve():
        return f"skill already linked: {destination}"
    if not force:
        raise SystemExit(
            f"Codex skill path exists and differs: {destination}. Re-run with --force."
        )
    if dry_run:
        return f"would replace existing skill path: {destination}"
    _remove_existing_skill_path(destination)
    return None


def _ensure_skill_symlink(*, force: bool, dry_run: bool) -> str:
    skill_file = REPO_SKILL_DIR / "SKILL.md"
    if not skill_file.exists():
        raise SystemExit(f"Missing repo skill: {skill_file}")
    CODEX_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    destination = CODEX_SKILLS_DIR / SKILL_NAME
    prepared = _prepare_skill_destination(destination, force=force, dry_run=dry_run)
    if prepared:
        return prepared
    if dry_run:
        return f"would link {destination} -> {REPO_SKILL_DIR}"
    destination.symlink_to(REPO_SKILL_DIR, target_is_directory=True)
    return f"linked {destination} -> {REPO_SKILL_DIR}"


def _run_codex(
    args: list[str], *, dry_run: bool
) -> subprocess.CompletedProcess[str] | None:
    if dry_run:
        redacted = [
            item.split("=", 1)[0] + "=<redacted>"
            if "=" in item
            and item.split("=", 1)[0].upper().endswith(("TOKEN", "KEY", "SECRET"))
            else item
            for item in args
        ]
        print("dry-run:", " ".join(redacted))
        return None
    return subprocess.run(  # nosec B603  # noqa: S603
        args,
        check=True,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
    )


def _mcp_exists() -> bool:
    completed = subprocess.run(  # nosec B603 B607  # noqa: S603
        ["codex", "mcp", "get", MCP_NAME],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _register_mcp(
    base_url: str, token_env: str, token: str, *, force: bool, dry_run: bool
) -> None:
    exists = False if dry_run else _mcp_exists()
    if exists and force:
        _run_codex(["codex", "mcp", "remove", MCP_NAME], dry_run=dry_run)
        exists = False
    if exists:
        print(f"MCP server already registered: {MCP_NAME}")
        return
    command = [
        "codex",
        "mcp",
        "add",
        MCP_NAME,
        "--env",
        f"OPS_BASE_URL={base_url.rstrip('/')}",
        "--env",
        f"{token_env}={token}",
        "--",
        "python3",
        str(MCP_SCRIPT),
    ]
    _run_codex(command, dry_run=dry_run)


def _verify_registration(dry_run: bool) -> None:
    if dry_run:
        return
    completed = _run_codex(["codex", "mcp", "get", MCP_NAME], dry_run=False)
    if completed is None:
        raise RuntimeError("Codex MCP verification did not execute")
    if str(MCP_SCRIPT) not in completed.stdout:
        raise SystemExit(f"Codex MCP registration does not point at {MCP_SCRIPT}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=os.environ.get("OPS_BASE_URL", "http://127.0.0.1:9700")
    )
    parser.add_argument("--token-env", default="OPS_AGENT_BUG_API_TOKEN")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token, generated = _resolve_token(args.token_env, dry_run=args.dry_run)
    skill_status = _ensure_skill_symlink(force=args.force, dry_run=args.dry_run)
    _register_mcp(
        args.base_url, args.token_env, token, force=args.force, dry_run=args.dry_run
    )
    _verify_registration(args.dry_run)
    print(skill_status)
    print(f"Codex MCP server ready: {MCP_NAME}")
    if generated:
        action = "would create" if args.dry_run else "created"
        print(f"{action} local {args.token_env} in {DOTENV_PATH}; value redacted")


if __name__ == "__main__":
    main()
