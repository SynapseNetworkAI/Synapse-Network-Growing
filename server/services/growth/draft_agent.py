from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from server import config
from server.services.agents.llm_adapter import get_provider
from server.services.social.agent_json_output import parse_agent_json_output


class GrowthDraftError(ValueError):
    pass


class GrowthDraftResult(BaseModel):
    subject: str
    body: str
    personalization_evidence: list[dict[str, object]] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


def generate_outreach_draft(
    *,
    lead: dict[str, Any],
    channel: str,
    notes: str = "",
) -> GrowthDraftResult:
    if config.E2E_MODE:
        return _e2e_draft(lead=lead, channel=channel)
    system_prompt, user_prompt = _build_prompt(lead=lead, channel=channel, notes=notes)
    provider = get_provider(config.SOCIAL_CONTENT_LLM_PROVIDER)
    raw_text, tokens = provider.call(
        system_prompt,
        user_prompt,
        config.SOCIAL_CONTENT_LLM_MODEL,
        0.4,
        min(max(int(config.SOCIAL_CONTENT_LLM_TIMEOUT or 90), 30), 240),
    )
    parsed = parse_agent_json_output(raw_text)
    payload = parsed.data
    subject = _clean(payload.get("subject"))
    body = _clean(payload.get("body"))
    evidence = payload.get("personalization_evidence")
    if not subject or not body:
        raise GrowthDraftError("draft agent returned empty subject or body")
    if not isinstance(evidence, list) or not evidence:
        raise GrowthDraftError("draft agent returned no personalization evidence")
    return GrowthDraftResult(
        subject=subject,
        body=body,
        personalization_evidence=evidence,
        metadata={
            "generated_by": "growth_outreach_draft_agent_v1",
            "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
            "model": config.SOCIAL_CONTENT_LLM_MODEL,
            "tokens": int(tokens or 0),
            "parser_excerpt": parsed.excerpt,
            "rationale": _clean(payload.get("rationale")) or "",
        },
    )


def _build_prompt(*, lead: dict[str, Any], channel: str, notes: str) -> tuple[str, str]:
    product_context = _read_bounded(".agents/product-marketing-context.md", 5000)
    persona = _read_bounded("roles/growth_lead/prompts/persona.md", 1800)
    cold_email = _read_bounded(".agents/skills/cold-email/SKILL.md", 2200)
    community = _read_bounded(".agents/skills/community-marketing/SKILL.md", 1600)
    system = (
        "You are a growth lead for Synapse Network. Draft one concise, "
        "truthful outreach message. Do not claim guaranteed revenue, "
        "investment, rankings, or partnerships. Do not output markdown fences. "
        "Return only JSON with subject, body, personalization_evidence, rationale."
    )
    user = (
        "# Product context\n"
        f"{product_context}\n\n"
        "# Growth persona\n"
        f"{persona}\n\n"
        "# Skill excerpts\n"
        f"{cold_email}\n\n{community}\n\n"
        "# Lead\n"
        f"{lead}\n\n"
        "# Channel\n"
        f"{channel}\n\n"
        "# Operator notes\n"
        f"{notes or '-'}\n\n"
        "# Output contract\n"
        "{\n"
        '  "subject": "short subject line",\n'
        '  "body": "message body",\n'
        '  "personalization_evidence": [{"source":"...","reason":"..."}],\n'
        '  "rationale": "why this message fits this lead"\n'
        "}\n"
    )
    return system, user


def _read_bounded(relative_path: str, max_chars: int) -> str:
    path = Path(config.PROJECT_ROOT) / relative_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text.strip()[:max_chars]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _e2e_draft(*, lead: dict[str, Any], channel: str) -> GrowthDraftResult:
    name = _clean(lead.get("name")) or "there"
    lead_type = _clean(lead.get("lead_type")) or "lead"
    subject = (
        "Synapse provider onboarding"
        if lead_type == "provider"
        else "Synapse agent settlement layer"
    )
    return GrowthDraftResult(
        subject=subject,
        body=(
            f"{name}, Synapse helps AI agents discover, invoke, and pay for "
            "APIs with budget isolation and USDC settlement. Would this be "
            "worth a quick look?"
        ),
        personalization_evidence=[
            {"source": "e2e_fixture", "reason": f"{lead_type} growth workflow"}
        ],
        metadata={
            "generated_by": "growth_outreach_draft_agent_v1",
            "provider": "e2e_stub",
            "model": "deterministic",
            "channel": channel,
        },
    )
