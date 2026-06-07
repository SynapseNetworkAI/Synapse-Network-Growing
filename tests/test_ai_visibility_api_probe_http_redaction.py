import urllib.error

from scripts.growth import run_ai_visibility_api_probe as api_probe


def test_post_json_redacts_secret_values_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai-value")

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                "https://api.openai.com/v1/responses",
                401,
                "Unauthorized",
                hdrs=None,
                fp=None,
            )

        def read(self):
            return b'{"error":"bad key secret-openai-value"}'

    def fake_urlopen(*_args, **_kwargs):
        raise FakeError()

    monkeypatch.setattr(
        api_probe.probe_adapters.urllib.request, "urlopen", fake_urlopen
    )

    try:
        api_probe.post_json(
            api_probe.OPENAI_RESPONSES_URL,
            {"model": "test"},
            {"Authorization": "Bearer secret-openai-value"},
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("HTTPError should raise RuntimeError")

    assert "secret-openai-value" not in message
    assert "[REDACTED]" in message
