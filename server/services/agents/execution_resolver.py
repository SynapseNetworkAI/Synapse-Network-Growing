"""Resolve the most suitable agent + skill pair for a task description."""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from server.database import AgentRow
from server.schemas import TaskExecutionCandidate, TaskExecutionSuggestion
from server.services.agents.loader import ensure_agents_loaded, sync_agents_to_db
from server.services.agents.skills import list_skills, load_skill_metadata

AUTO_SELECTION_THRESHOLD = 0.72
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ENGINEERING_HINTS = {
    "bug", "bugfix", "fix", "traceback", "exception", "error", "failure", "failed", "backend",
    "server", "python", "fastapi", "api", "endpoint", "sqlite", "sqlalchemy", "runtime",
    "incident", "log", "logs", "stack", "stacktrace", "test", "tests", "pytest", "code",
    "implementation", "validate", "validation",
    "修复", "报错", "异常", "接口", "后端", "代码", "日志", "堆栈", "测试",
}
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "need", "make",
    "give", "work", "plan", "task", "user", "page", "write", "build", "create", "help",
    "me", "my", "you", "yourself", "someone", "something", "anything", "later", "soon", "important",
    "负责", "进行", "一个", "需要", "可以", "任务", "方案", "输出", "根据", "现在",
}


def _parse_json_list(raw: str | list | None) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _read_persona_body(path: str | None) -> str:
    if not path:
        return ""
    persona_path = Path(path)
    if not persona_path.exists():
        return ""

    text = persona_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens: set[str] = set()

    for token in _WORD_RE.findall(lowered):
        if token in _STOPWORDS:
            continue
        tokens.add(token)
        for part in token.replace("_", "-").split("-"):
            if len(part) >= 2 and part not in _STOPWORDS:
                tokens.add(part)

    for match in _CJK_RE.findall(text):
        cleaned = match.strip()
        if not cleaned:
            continue
        if cleaned not in _STOPWORDS:
            tokens.add(cleaned)
        if len(cleaned) <= 8:
            for size in (2, 3):
                for index in range(len(cleaned) - size + 1):
                    token = cleaned[index:index + size]
                    if token not in _STOPWORDS:
                        tokens.add(token)

    return tokens


def _candidate_reason(agent: AgentRow, skill_name: str, matched_terms: list[str]) -> str:
    terms = ", ".join(matched_terms[:5]) if matched_terms else "语义最接近"
    return f"{agent.display_name} / {skill_name} 命中任务语义: {terms}"


def _is_engineering_request(description_tokens: set[str], description: str) -> bool:
    lowered = description.lower()
    if any(token in description_tokens for token in _ENGINEERING_HINTS):
        return True
    return any(token in lowered for token in _ENGINEERING_HINTS)


def _candidate_score(
    description_tokens: set[str],
    description: str,
    agent: AgentRow,
    skill_name: str,
    preferred_agent_id: str | None,
) -> tuple[float, list[str]]:
    if skill_name == "__direct_execution__":
        skill_name_tokens = _tokenize("direct execution engineering bugfix code validation")
        skill_desc_tokens = _tokenize(
            "direct engineering execution minimal code change bugfix runtime traceback api backend validation"
        )
    else:
        skill_meta = load_skill_metadata(skill_name)
        skill_name_tokens = _tokenize(skill_name)
        skill_desc_tokens = _tokenize(f"{skill_meta.description} {skill_meta.body[:1200]}")
    agent_tokens = _tokenize(f"{agent.display_name} {agent.goal} {_read_persona_body(agent.persona_path)[:1200]}")

    name_overlap = description_tokens & skill_name_tokens
    skill_overlap = description_tokens & skill_desc_tokens
    agent_overlap = description_tokens & agent_tokens
    matched_terms = sorted(name_overlap | skill_overlap | agent_overlap)

    score = 0.0
    score += len(name_overlap) * 4.0
    score += len(skill_overlap) * 2.5
    score += len(agent_overlap) * 1.5

    description_text = " ".join(sorted(description_tokens))
    if skill_name.lower() in description_text:
        score += 3.0
    if preferred_agent_id and preferred_agent_id == agent.id:
        score += 2.0
    if skill_name == "__direct_execution__" and str(agent.group or "") == "engineering" and _is_engineering_request(description_tokens, description):
        score += 12.0
        matched_terms = sorted(set(matched_terms) | {"engineering", "bugfix", "direct_execution"})

    return score, matched_terms


def suggest_task_execution(
    db: Session,
    description: str,
    preferred_agent_id: str | None = None,
    preferred_skill_name: str | None = None,
    limit: int = 3,
) -> TaskExecutionSuggestion:
    description_tokens = _tokenize(description)
    engineering_request = _is_engineering_request(description_tokens, description)
    agents = ensure_agents_loaded(db)
    if engineering_request and not any(str(agent.group or "") == "engineering" for agent in agents):
        agents = sync_agents_to_db(db)
        db.commit()
        for row in agents:
            db.refresh(row)
    available_skills = set(list_skills())
    candidates: list[tuple[float, TaskExecutionCandidate]] = []

    for agent in agents:
        if preferred_agent_id and agent.id != preferred_agent_id:
            continue

        agent_skills = [skill for skill in _parse_json_list(agent.skills) if skill in available_skills]
        if engineering_request and str(agent.group or "") == "engineering":
            agent_skills = ["__direct_execution__", *agent_skills]
        if preferred_skill_name:
            if preferred_skill_name not in agent_skills:
                continue
            agent_skills = [preferred_skill_name]

        for skill_name in agent_skills:
            score, matched_terms = _candidate_score(description_tokens, description, agent, skill_name, preferred_agent_id)
            if score <= 0 and not preferred_agent_id and not preferred_skill_name:
                continue

            candidates.append((
                score,
                TaskExecutionCandidate(
                    agent_id=agent.id,
                    display_name=agent.display_name,
                    agent_group=agent.group or "",
                    skill_name=skill_name,
                    confidence=0.0,
                    reason=_candidate_reason(agent, skill_name, matched_terms),
                ),
            ))

    if not candidates:
        fallback_candidates: list[TaskExecutionCandidate] = []
        for agent in agents:
            skills = [skill for skill in _parse_json_list(agent.skills) if skill in available_skills]
            for skill_name in skills[:1]:
                fallback_candidates.append(TaskExecutionCandidate(
                    agent_id=agent.id,
                    display_name=agent.display_name,
                    agent_group=agent.group or "",
                    skill_name=skill_name,
                    confidence=0.25,
                    reason=f"{agent.display_name} / {skill_name} 缺少明确语义命中，需要人工确认",
                ))
        fallback_candidates = fallback_candidates[:limit]
        first = fallback_candidates[0] if fallback_candidates else None
        return TaskExecutionSuggestion(
            agent_id=first.agent_id if first else None,
            skill_name=first.skill_name if first else None,
            confidence=first.confidence if first else 0.0,
            reason=first.reason if first else "未找到可执行候选",
            requires_confirmation=True,
            candidates=fallback_candidates,
        )

    candidates.sort(key=lambda item: (-item[0], item[1].agent_id, item[1].skill_name))
    top_score = candidates[0][0]
    second_score = candidates[1][0] if len(candidates) > 1 else 0.0
    spread = max(0.0, top_score - second_score)

    ranked: list[TaskExecutionCandidate] = []
    for score, candidate in candidates[:limit]:
        relative = score / max(top_score, 1.0)
        signal_strength = min(score, 10.0) / 10.0
        confidence = min(0.98, 0.15 + signal_strength * 0.45 + relative * 0.25 + min(spread, 4.0) * 0.05)
        if preferred_agent_id:
            confidence = max(confidence, 0.55)
        if preferred_skill_name:
            confidence = max(confidence, 0.9)
        candidate.confidence = round(confidence, 2)
        ranked.append(candidate)

    first = ranked[0]
    return TaskExecutionSuggestion(
        agent_id=first.agent_id,
        skill_name=first.skill_name,
        confidence=first.confidence,
        reason=first.reason,
        requires_confirmation=first.confidence < AUTO_SELECTION_THRESHOLD,
        candidates=ranked,
    )
