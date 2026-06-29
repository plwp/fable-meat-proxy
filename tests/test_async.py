import asyncio

from conftest import AutoReplyGmailService

from fable_meat_proxy import AsyncAnthropic, Config


class FakeAsyncRealClient:
    def __init__(self):
        self.calls = []
        outer = self

        class _Messages:
            async def create(self, **kwargs):
                outer.calls.append(kwargs)
                return {"sentinel": "real-async", "model": kwargs.get("model")}

        self.messages = _Messages()


def _config():
    return Config(friend_email="hank@example.com", poll_interval=0, reply_timeout_seconds=100)


def test_async_non_fable_passes_through():
    real = FakeAsyncRealClient()
    client = AsyncAnthropic(real_client=real, config=_config())
    result = asyncio.run(client.messages.create(model="claude-opus-4-8", messages=[]))
    assert result["sentinel"] == "real-async"
    assert len(real.calls) == 1


def test_async_fable_routes_to_meat():
    service = AutoReplyGmailService(answer="async meaty answer")
    real = FakeAsyncRealClient()

    client = AsyncAnthropic(real_client=real, config=_config(), gmail_service=service)
    msg = asyncio.run(
        client.messages.create(
            model="claude-fable-5",
            max_tokens=100,
            messages=[{"role": "user", "content": "hello"}],
        )
    )

    assert msg.content[0].text == "async meaty answer"
    assert msg.model == "claude-fable-5"
    assert real.calls == []
    assert len(service.sent) == 1


def test_async_fable_stream_rejected():
    client = AsyncAnthropic(real_client=FakeAsyncRealClient(), config=_config())
    try:
        client.messages.stream(model="claude-fable-5", messages=[])
    except NotImplementedError:
        return
    raise AssertionError("expected NotImplementedError")
