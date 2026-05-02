"""Signal helpers for the social asset planner."""

from __future__ import annotations

import re
from dataclasses import dataclass

from server import schemas_social_distribution as dist_schema


@dataclass(frozen=True)
class AssetSignal:
    signal_type: str
    source_ref: str
    title: str
    summary: str
    score: float = 0.0


def _dedupe_signals(signals: list[AssetSignal]) -> list[AssetSignal]:
    seen: set[str] = set()
    result: list[AssetSignal] = []
    for signal in sorted(signals, key=lambda item: item.score, reverse=True):
        if signal.source_ref in seen:
            continue
        seen.add(signal.source_ref)
        result.append(
            AssetSignal(
                signal_type=signal.signal_type,
                source_ref=signal.source_ref,
                title=_public_safe(signal.title),
                summary=_public_safe(signal.summary),
                score=float(signal.score),
            )
        )
    return result


def _signal_out(signal: AssetSignal) -> dist_schema.SocialAssetPlannerSignalOut:
    return dist_schema.SocialAssetPlannerSignalOut(
        signal_type=signal.signal_type,
        source_ref=signal.source_ref,
        title=signal.title,
        summary=signal.summary,
        score=signal.score,
    )


def _public_safe(value: str | None) -> str:
    text = str(value or "").strip()
    text = re.sub(r"/Users/[A-Za-z0-9._/\\-]+", "[path]", text)
    text = re.sub(
        r"(?i)(authorization|api[-_ ]?key|secret|token)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"(?is)workflow json.*", "workflow details omitted", text)
    text = re.sub(r"(?is)traceback.*", "traceback omitted", text)
    text = re.sub(r"\s+", " ", text)
    return text
