from __future__ import annotations

"""Default planning seed data kept out of the lifecycle service."""

DEFAULT_GOAL_SPECS: list[dict[str, object]] = [
    {
        "goal_key": "gateway_reliability",
        "title": "Gateway reliability",
        "domain": "reliability",
        "intent_markdown": "Keep the gateway, workflow runner and agent self-repair loop healthy.",
        "success_metric": "critical runtime incidents remain at 0 and failed workflows are triaged.",
        "workflow_key": "gateway_reliability_repair",
        "project_key": "synapse-network-growing",
        "priority": "normal",
        "risk_level": "normal",
        "weight": 0.6,
    },
    {
        "goal_key": "operator_growth",
        "title": "Operator growth",
        "domain": "growth",
        "intent_markdown": "Continuously discover practical growth and DevRel work for Synapse Network.",
        "success_metric": "approved candidate throughput increases without operator overload.",
        "workflow_key": "agent_self_repair",
        "project_key": "synapse-network-growing",
        "priority": "normal",
        "risk_level": "normal",
        "weight": 0.4,
    },
]
