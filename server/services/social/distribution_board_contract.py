"""Board projection contract for social distribution."""

from __future__ import annotations


BOARD_COLUMNS = (
    ("backlog", "待计划", "还没有方案或渠道选择不足。"),
    ("needs_review", "待审核", "已有方案，等待人类确认方向。"),
    ("ready_to_publish", "待发布", "已有平台文档，等待发布或人工回填。"),
    ("live", "已发布", "至少一个平台已有 live 记录。"),
    ("blocked", "异常", "生成、发布、removed 或策略失败需要处理。"),
)


def board_next_action(column_key: str, *, task_kind_code: str = "content_distribution") -> str:
    if task_kind_code == "x_reply_block":
        return {
            "backlog": "补齐真实 X source posts 后生成回复候选。",
            "needs_review": "生成 5 条 X 回复候选；不生成多平台文章。",
            "ready_to_publish": "审核 X 回复候选，通过 Human Gate 逐条发布。",
            "live": "打开回复链接，检查排版、重复和效果数据。",
            "blocked": "修复 source posts、登录权限或生成超时后重试。",
        }.get(column_key, "Inspect reply block history.")
    return {
        "backlog": "创建内容任务并生成方案。",
        "needs_review": "审核方案方向，通过后生成平台文档。",
        "ready_to_publish": "发布 X 或手动发布非 X，并回填链接。",
        "live": "检查发布链接、事件和效果数据。",
        "blocked": "打开详情修复失败、removed 或策略阻断。",
    }.get(column_key, "Inspect task history.")


def document_status_for_task(status: str | None) -> str:
    normalized = str(status or "").strip()
    if normalized in {"draft_ready", "planned"}:
        return "generated"
    if normalized == "needs_review":
        return "needs_review"
    if normalized in {"approved", "submitted"}:
        return "approved"
    if normalized == "live":
        return "published"
    if normalized in {"failed", "removed", "skipped", "rejected"}:
        return "failed"
    return "generated"
