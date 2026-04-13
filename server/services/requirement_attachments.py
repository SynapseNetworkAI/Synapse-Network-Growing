from __future__ import annotations

import base64
import binascii
import mimetypes
import re
from pathlib import Path
from typing import Any

import server.config as config
from server.database import RequirementAttachmentRow

_MAX_ATTACHMENT_COUNT = 12
_MAX_ATTACHMENT_SIZE_BYTES = 3 * 1024 * 1024
_SAFE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def attachments_storage_root(project_root: Path | None = None) -> Path:
    return (project_root or config.PROJECT_ROOT) / "runtime" / "requirement_attachments"


def normalize_attachment_payloads(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    normalized: list[dict[str, Any]] = []
    for raw in items[:_MAX_ATTACHMENT_COUNT]:
        if not isinstance(raw, dict):
            continue
        file_name = str(raw.get("file_name") or "").strip()
        content_base64 = str(raw.get("content_base64") or "").strip()
        if not file_name or not content_base64:
            continue
        content_type = str(raw.get("content_type") or "").strip() or "application/octet-stream"
        source = str(raw.get("source") or "upload").strip() or "upload"
        normalized.append(
            {
                "file_name": file_name,
                "content_base64": content_base64,
                "content_type": content_type,
                "source": source,
            }
        )
    return normalized


def _safe_file_stem(file_name: str) -> str:
    stem = Path(file_name).stem.strip() or "attachment"
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-.") or "attachment"


def _safe_extension(file_name: str, content_type: str) -> str:
    guessed = Path(file_name).suffix.lower()
    if guessed:
        return guessed
    mime_guess = mimetypes.guess_extension(content_type or "")
    if mime_guess:
        return mime_guess.lower()
    return ".bin"


def _safe_output_name(file_name: str, content_type: str, index: int) -> str:
    return f"{index:02d}-{_safe_file_stem(file_name)}{_safe_extension(file_name, content_type)}"


def _decode_attachment_bytes(content_base64: str) -> bytes:
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid attachment content_base64 payload.") from exc
    if not payload:
        raise ValueError("Attachment content cannot be empty.")
    if len(payload) > _MAX_ATTACHMENT_SIZE_BYTES:
        raise ValueError(f"Attachment exceeds {_MAX_ATTACHMENT_SIZE_BYTES} byte limit.")
    return payload


def _attachment_kind(content_type: str, file_name: str) -> str:
    if str(content_type or "").lower().startswith("image/"):
        return "image"
    if Path(file_name).suffix.lower() in _SAFE_IMAGE_EXTENSIONS:
        return "image"
    return "file"


def _relative_to_project_root(path: Path, project_root: Path | None = None) -> str:
    root = (project_root or config.PROJECT_ROOT).resolve()
    return str(path.resolve().relative_to(root))


def persist_requirement_attachments(
    requirement_id: int,
    attachments: list[dict[str, Any]] | None,
    *,
    project_root: Path | None = None,
) -> list[RequirementAttachmentRow]:
    normalized = normalize_attachment_payloads(attachments)
    if not normalized:
        return []
    root = attachments_storage_root(project_root)
    output_dir = root / f"req-{int(requirement_id)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[RequirementAttachmentRow] = []
    for index, item in enumerate(normalized, start=1):
        payload = _decode_attachment_bytes(str(item["content_base64"]))
        file_name = str(item["file_name"])
        content_type = str(item["content_type"])
        source = str(item["source"])
        output_name = _safe_output_name(file_name, content_type, index)
        output_path = output_dir / output_name
        output_path.write_bytes(payload)
        rows.append(
            RequirementAttachmentRow(
                requirement_id=int(requirement_id),
                file_name=file_name,
                stored_path=_relative_to_project_root(output_path, project_root),
                content_type=content_type,
                attachment_kind=_attachment_kind(content_type, file_name),
                source=source,
                size_bytes=len(payload),
            )
        )
    manifest_lines = [
        "# Requirement Intake Attachments",
        "",
        f"Requirement ID: {int(requirement_id)}",
        "",
        "These files were attached during requirement intake and should be treated as execution context.",
        "",
    ]
    for row in rows:
        manifest_lines.extend(
            [
                f"## {row.file_name}",
                f"- kind: `{row.attachment_kind}`",
                f"- source: `{row.source}`",
                f"- content_type: `{row.content_type}`",
                f"- size_bytes: `{row.size_bytes}`",
                f"- path: `{row.stored_path}`",
                "",
            ]
        )
    (output_dir / "context-manifest.md").write_text("\n".join(manifest_lines).strip() + "\n", encoding="utf-8")
    return rows


def requirement_attachment_context_files(
    requirement_id: int,
    attachments: list[RequirementAttachmentRow],
    *,
    project_root: Path | None = None,
) -> list[str]:
    if not attachments:
        return []
    root = attachments_storage_root(project_root) / f"req-{int(requirement_id)}"
    files = []
    manifest_path = root / "context-manifest.md"
    if manifest_path.exists():
        files.append(_relative_to_project_root(manifest_path, project_root))
    files.extend(
        str(row.stored_path)
        for row in attachments
        if str(row.stored_path or "").strip()
    )
    deduped: list[str] = []
    seen: set[str] = set()
    for item in files:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def serialize_requirement_attachment(row: RequirementAttachmentRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "requirement_id": int(row.requirement_id),
        "file_name": str(row.file_name),
        "stored_path": str(row.stored_path),
        "content_type": str(row.content_type),
        "attachment_kind": str(row.attachment_kind),
        "source": str(row.source),
        "size_bytes": int(row.size_bytes or 0),
        "created_at": row.created_at,
    }
