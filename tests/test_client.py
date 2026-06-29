import pytest
from conftest import AutoReplyGmailService, FakeGmailService, make_message

from fable_meat_proxy import Anthropic, Config, is_fable_model
from fable_meat_proxy.errors import FableMeatError, FableReplyTimeout


class FakeRawResponse:
    def __init__(self, outer):
        self._outer = outer

    def create(self, **kwargs):
        self._outer.calls.append(("raw", kwargs))
        return {"sentinel": "raw"}


class FakeRealClient:
    """Records real API calls and exposes the messages surface we delegate to."""

    def __init__(self):
        self.calls = []
        self.options = None
        outer = self

        class _Messages:
            with_raw_response = FakeRawResponse(outer)
            with_streaming_response = FakeRawResponse(outer)

            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return {"sentinel": "real-api", "model": kwargs.get("model")}

            def stream(self, **kwargs):
                return "real-stream"

            def count_tokens(self, **kwargs):
                return "counted"

        class _BetaMessages:
            def create(self, **kwargs):
                outer.calls.append(("beta", kwargs))
                return {"sentinel": "beta-real", "model": kwargs.get("model")}

            def count_tokens(self, **kwargs):
                return "beta-counted"

        class _Beta:
            messages = _BetaMessages()

        self.messages = _Messages()
        self.beta = _Beta()
        self.other_attr = "delegated"

    def with_options(self, **kwargs):
        self.options = kwargs
        return self


def _config():
    return Config(friend_email="hank@example.com", poll_interval=0, reply_timeout_seconds=100)


def test_is_fable_model_is_exact_not_substring():
    assert is_fable_model("claude-fable-5")
    assert is_fable_model("CLAUDE-FABLE-5")  # case-insensitive
    assert not is_fable_model("claude-opus-4-8")
    assert not is_fable_model(None)
    # Substring matches must NOT route to the human backend (prompt-exfil guard).
    assert not is_fable_model("Fable")
    assert not is_fable_model("not-fable")
    assert not is_fable_model("claude-opus-4-fable-debug")


def test_is_fable_model_custom_allowlist():
    allow = frozenset({"my-fable", "claude-fable-5"})
    assert is_fable_model("my-fable", allow)
    assert not is_fable_model("claude-fable-5x", allow)


def test_fable_count_tokens_rejected():
    client = Anthropic(real_client=FakeRealClient(), config=_config())
    with pytest.raises(FableMeatError):
        client.messages.count_tokens(model="claude-fable-5", messages=[])


def test_fable_beta_create_rejected_but_real_delegates():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    # Fable must not slip through the beta surface to the real API.
    with pytest.raises(FableMeatError):
        client.beta.messages.create(model="claude-fable-5", messages=[])
    assert real.calls == []
    # Non-Fable beta calls delegate unchanged.
    out = client.beta.messages.create(model="claude-opus-4-8", messages=[])
    assert out["sentinel"] == "beta-real"


def test_fable_beta_count_tokens_rejected():
    client = Anthropic(real_client=FakeRealClient(), config=_config())
    with pytest.raises(FableMeatError):
        client.beta.messages.count_tokens(model="claude-fable-5", messages=[])


def test_raw_response_count_tokens_rejects_fable():
    client = Anthropic(real_client=FakeRealClient(), config=_config())
    with pytest.raises(NotImplementedError):
        client.messages.with_raw_response.count_tokens(model="claude-fable-5")


def test_caller_supplied_reply_token_is_ignored():
    # A caller passing a weak reply_token through messages.create must not weaken
    # auth: the client strips it, a strong token is generated, and a spoofed reply
    # echoing only the weak token is rejected (surfacing as a timeout).
    own = make_message("sent-1", "Me <me@example.com>", "prompt")
    spoof = make_message("evil", "Hank <hank@example.com>", "answer\n> token: weak")
    service = FakeGmailService([[own], [own, spoof]])
    cfg = Config(friend_email="hank@example.com", poll_interval=0, reply_timeout_seconds=0)
    client = Anthropic(real_client=FakeRealClient(), config=cfg, gmail_service=service)
    with pytest.raises(FableReplyTimeout):
        client.messages.create(
            model="claude-fable-5", reply_token="weak",
            messages=[{"role": "user", "content": "hi"}],
        )


def test_non_fable_passes_through_to_real_client():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    result = client.messages.create(model="claude-opus-4-8", max_tokens=10, messages=[])
    assert result["sentinel"] == "real-api"
    assert len(real.calls) == 1


def test_unknown_client_attrs_delegate():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    assert client.other_attr == "delegated"


def test_unknown_messages_attrs_delegate():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    assert client.messages.count_tokens(model="x") == "counted"


def test_non_fable_stream_delegates():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    assert client.messages.stream(model="claude-opus-4-8") == "real-stream"


def test_fable_stream_rejected():
    client = Anthropic(real_client=FakeRealClient(), config=_config())
    with pytest.raises(NotImplementedError):
        client.messages.stream(model="claude-fable-5", messages=[])


def test_fable_create_stream_true_rejected():
    client = Anthropic(real_client=FakeRealClient(), config=_config())
    with pytest.raises(NotImplementedError):
        client.messages.create(model="claude-fable-5", stream=True, messages=[])


def test_with_options_preserves_proxy_and_routing():
    service = AutoReplyGmailService(answer="options answer")
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config(), gmail_service=service)

    scoped = client.with_options(timeout=5)
    assert isinstance(scoped, Anthropic)
    assert real.options == {"timeout": 5}

    # Fable routing must survive the with_options() chaining.
    msg = scoped.messages.create(
        model="claude-fable-5", messages=[{"role": "user", "content": "hi"}]
    )
    assert msg.content[0].text == "options answer"
    assert real.calls == []


def test_raw_response_rejects_fable_but_delegates_others():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    with pytest.raises(NotImplementedError):
        client.messages.with_raw_response.create(model="claude-fable-5", messages=[])
    assert client.messages.with_raw_response.create(model="claude-opus-4-8")["sentinel"] == "raw"


def test_fable_routes_to_meat_and_returns_message():
    service = AutoReplyGmailService(answer="the meaty answer")
    real = FakeRealClient()

    client = Anthropic(real_client=real, config=_config(), gmail_service=service)
    msg = client.messages.create(
        model="claude-fable-5",
        max_tokens=100,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert msg.content[0].text == "the meaty answer"
    assert msg.role == "assistant"
    assert msg.model == "claude-fable-5"
    assert real.calls == []  # never hit the real API
    assert len(service.sent) == 1  # emailed the friend exactly once
