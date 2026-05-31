"""Lightweight schema migrations for MCP server release records."""

from sqlalchemy import text


def migrate_mcp_server_release_schema(engine_, insp, tables: list[str]) -> None:
    if "mcp_server_surfaces" not in tables:
        return
    existing = {c["name"] for c in insp.get_columns("mcp_server_surfaces")}
    if "category" in existing:
        return
    with engine_.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE mcp_server_surfaces "
                "ADD COLUMN category TEXT DEFAULT 'directory' NOT NULL"
            )
        )
        conn.commit()
