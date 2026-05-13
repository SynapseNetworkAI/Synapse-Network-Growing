import pytest

from server.services.social import distribution_content_strategy as strategy
from server.services.social.distribution_documents import _source_plan_metadata


def test_platform_length_strategy_covers_channel_shapes():
    assert strategy.x_weighted_character_count("A https://example.com/abc 超") == 28
    assert strategy.platform_format_kind("x") == "single_x_post"
    assert strategy.platform_format_kind("hacker_news") == "hn_submission"
    assert strategy.platform_format_kind("reddit") == "discussion_post"
    assert strategy.platform_format_kind("hashnode") == "long_article"
    assert "1200-3000" in strategy.platform_target_length("reddit")
    assert "800-2000" in strategy.platform_target_length("v2ex")
    assert strategy.text_length_metadata("x", "Hello")["weighted_counts"] == [5]
    assert strategy.text_length_metadata("hashnode", "one two")["word_count"] == 2


def test_normalize_x_payload_infers_single_and_thread_shapes():
    title, body, metadata = strategy.normalize_x_payload(
        {"tweets": ["single tweet"], "rationale": "short update"},
        fallback_title="Fallback",
    )
    assert title == "Fallback"
    assert body == "single tweet"
    assert metadata["x_format"] == "single"
    assert metadata["rationale"] == "short update"

    thread_title, thread_body, thread_metadata = strategy.normalize_x_payload(
        {"tweets": ["first", "second"]},
        fallback_title="Deep article",
    )
    assert thread_title == "X thread: Deep article"
    assert "1/2" in thread_body
    assert thread_metadata["format_kind"] == "x_thread"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"x_format": "bad", "tweets": ["one"]}, "x_format"),
        ({"x_format": "single", "tweets": []}, "tweets must not be empty"),
        ({"x_format": "single", "tweets": ["one", "two"]}, "single format"),
        ({"x_format": "thread", "tweets": ["one"]}, "thread format"),
    ],
)
def test_normalize_x_payload_fails_closed_for_invalid_shapes(payload, message):
    with pytest.raises(ValueError, match=message):
        strategy.normalize_x_payload(payload, fallback_title="Fallback")


def test_source_plan_metadata_reads_structured_plan():
    class Doc:
        document_kind = "source_plan"
        metadata_json = '{"structured_plan":{"core_angle":"control plane"}}'

    class Asset:
        documents = [Doc()]

    assert _source_plan_metadata(Asset()) == {"core_angle": "control plane"}
