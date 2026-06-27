from conftest import FakeGmailService, make_message

from fable_meat_proxy import Anthropic, Config, is_fable_model


class FakeRealClient:
    """Records that a real API call was made, returns a sentinel."""

    def __init__(self):
        self.calls = []

        class _Messages:
            def __init__(self, outer):
                self._outer = outer

            def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                return {"sentinel": "real-api", "model": kwargs.get("model")}

        self.messages = _Messages(self)
        self.other_attr = "delegated"


def _config():
    return Config(friend_email="hank@example.com", poll_interval=0, reply_timeout=100)


def test_is_fable_model():
    assert is_fable_model("claude-fable-5")
    assert is_fable_model("Fable")
    assert not is_fable_model("claude-opus-4-8")
    assert not is_fable_model(None)


def test_non_fable_passes_through_to_real_client():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    result = client.messages.create(model="claude-opus-4-8", max_tokens=10, messages=[])
    assert result["sentinel"] == "real-api"
    assert len(real.calls) == 1


def test_unknown_attrs_delegate_to_real_client():
    real = FakeRealClient()
    client = Anthropic(real_client=real, config=_config())
    assert client.other_attr == "delegated"


def test_fable_routes_to_meat_and_returns_message():
    own = make_message("sent-1", "Me <me@example.com>", "prompt")
    reply = make_message("r1", "Hank <hank@example.com>", "the meaty answer")
    service = FakeGmailService([[own], [own, reply]])
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
