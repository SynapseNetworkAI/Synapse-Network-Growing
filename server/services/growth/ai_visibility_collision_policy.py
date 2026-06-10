from __future__ import annotations

KNOWN_BRAND_COLLISION_COMPETITORS = {
    "docs.synapse.sh",
    "getdrio.com",
    "mcp.synapse.sh",
    "python-docs.synapse.org",
    "mcp.synapse.org",
    "synapse.org",
    "synapseproto.com",
    "synapsenetwork.xyz",
    "synapse.network",
    "forbes.com/digital-assets/assets/synapse-network-zksnp",
}


def known_collision_mentions(values: list[str]) -> list[str]:
    collisions: set[str] = set()
    for value in values:
        normalized = str(value or "").strip().lower()
        for collision in KNOWN_BRAND_COLLISION_COMPETITORS:
            if collision in normalized:
                collisions.add(collision)
    return sorted(collisions)
