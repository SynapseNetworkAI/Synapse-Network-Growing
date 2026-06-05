from sqlalchemy import create_engine, inspect, text

from server.database_growth_ai_visibility import migrate_growth_ai_visibility_schema
from server.services.growth.ai_visibility_comparison_helpers import (
    _is_external_visibility_platform,
    _json_list,
)


def test_migrate_growth_ai_visibility_schema_adds_missing_columns():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE growth_ai_visibility_checks (
                    id INTEGER PRIMARY KEY,
                    query TEXT NOT NULL
                )
                """
            )
        )
        conn.commit()

    insp = inspect(engine)
    migrate_growth_ai_visibility_schema(engine, insp, {"growth_ai_visibility_checks"})

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("growth_ai_visibility_checks")
    }
    assert {
        "feed_key",
        "run_group",
        "result_rank",
        "evidence_url",
        "metadata_json",
    } <= columns


def test_migrate_growth_ai_visibility_schema_noops_without_table():
    engine = create_engine("sqlite:///:memory:")

    migrate_growth_ai_visibility_schema(engine, inspect(engine), set())

    assert inspect(engine).get_table_names() == []


def test_visibility_comparison_helpers_fail_closed_for_validation_and_bad_json():
    assert not _is_external_visibility_platform("")
    assert not _is_external_visibility_platform(None)
    assert not _is_external_visibility_platform("www_live_validation")
    assert not _is_external_visibility_platform("docs_local")
    assert _is_external_visibility_platform("chatgpt")
    assert _json_list("{bad json") == []
    assert _json_list('{"not": "a list"}') == []
    assert _json_list('["Synapse", "", 42]') == ["Synapse", "42"]
