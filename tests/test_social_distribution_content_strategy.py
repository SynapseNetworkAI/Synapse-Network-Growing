import pytest

from server.services.social import distribution_content_strategy as strategy
from server.services.social.distribution_documents import _source_plan_metadata


def test_platform_length_strategy_covers_channel_shapes():
    assert strategy.x_weighted_character_count("A https://example.com/abc 超") == 28
    assert strategy.platform_format_kind("x") == "x_long_post"
    assert strategy.platform_format_kind("hacker_news") == "hn_submission"
    assert strategy.platform_format_kind("reddit") == "discussion_post"
    assert strategy.platform_format_kind("hashnode") == "long_article"
    assert "1200-3000" in strategy.platform_target_length("reddit")
    assert "800-2000" in strategy.platform_target_length("v2ex")
    assert strategy.text_length_metadata("x", "Hello")["weighted_counts"] == [5]
    assert strategy.text_length_metadata("hashnode", "one two")["word_count"] == 2


def test_normalize_x_payload_accepts_long_post():
    text = "A one-person company needs a control plane before it needs more features."

    title, body, metadata = strategy.normalize_x_payload(
        {
            "x_format": "long_post",
            "post_text": text,
            "rationale": "Premium long-form technical note",
        },
        fallback_title="Solo company system",
    )

    assert title == "Solo company system"
    assert body == text
    assert metadata["x_format"] == "long_post"
    assert metadata["format_kind"] == "x_long_post"
    assert metadata["long_post_text"] == text
    assert metadata["premium_required"] is True
    assert metadata["soft_max_chars"] == 4000
    assert metadata["rationale"] == "Premium long-form technical note"


def test_x_long_post_soft_limit_fails_closed():
    with pytest.raises(ValueError, match="long post exceeds 4000"):
        strategy.normalize_x_payload(
            {"x_format": "long_post", "post_text": "a" * 4001},
            fallback_title="Too long",
        )


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

    assert (
        strategy.x_format_from_metadata({"format_kind": "x_long_post"}, ["body"])
        == "long_post"
    )


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
