import pytest
from conftest import FakeGmailService, make_message

from fable_meat_proxy.errors import FableReplyTimeout
from fable_meat_proxy.gmail_transport import (
    execute_with_retry,
    find_reply,
    get_header,
    send_message,
    wait_for_reply,
)


class FakeHttpError(Exception):
    def __init__(self, status):
        super().__init__(f"http {status}")
        self.resp = type("R", (), {"status": status})()


def test_send_message_builds_raw_payload():
    service = FakeGmailService([[]])
    result = send_message(service, "hank@example.com", "subject", "body", sender="me")
    assert result["threadId"] == "thread-1"
    assert len(service.sent) == 1
    assert "raw" in service.sent[0]


def test_find_reply_skips_own_message():
    own = make_message("sent-1", "Me <me@example.com>", "prompt")
    reply = make_message("r1", "Hank <hank@example.com>", "answer")
    assert find_reply([own], "sent-1", "hank@example.com") is None
    assert find_reply([own, reply], "sent-1", "hank@example.com") == "answer"
    assert "hank@example.com" in get_header(reply, "From")


def test_wait_for_reply_returns_friend_reply_after_polling():
    own = make_message("sent-1", "Me <me@example.com>", "the prompt")
    reply = make_message("r1", "Hank <hank@example.com>", "Fable says hi")
    service = FakeGmailService([[own], [own, reply]])

    sleeps = []
    text = wait_for_reply(
        service,
        "thread-1",
        exclude_id="sent-1",
        friend_email="hank@example.com",
        deadline_ts=1e12,
        poll_interval=5,
        sleep=lambda s: sleeps.append(s),
        now=lambda: 0.0,
    )
    assert text == "Fable says hi"
    assert sleeps == [5]  # polled, slept once, found it on the second poll


def test_wait_for_reply_times_out():
    own = make_message("sent-1", "Me <me@example.com>", "the prompt")
    service = FakeGmailService([[own]])
    nows = iter([50.0, 150.0])

    with pytest.raises(FableReplyTimeout) as exc:
        wait_for_reply(
            service,
            "thread-1",
            exclude_id="sent-1",
            friend_email="hank@example.com",
            deadline_ts=100.0,
            poll_interval=5,
            sleep=lambda s: None,
            now=lambda: next(nows),
        )
    assert isinstance(exc.value, TimeoutError)


def test_retry_transient_then_success():
    calls = {"n": 0}
    sleeps = []

    def thunk():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("flaky")
        return "ok"

    assert execute_with_retry(thunk, base_delay=1, sleep=lambda s: sleeps.append(s)) == "ok"
    assert calls["n"] == 3
    assert sleeps == [1, 2]  # exponential backoff


def test_retry_transient_http_status():
    calls = {"n": 0}

    def thunk():
        calls["n"] += 1
        if calls["n"] < 2:
            raise FakeHttpError(503)
        return "ok"

    assert execute_with_retry(thunk, sleep=lambda s: None) == "ok"
    assert calls["n"] == 2


def test_retry_non_transient_http_status_raises_immediately():
    calls = {"n": 0}

    def thunk():
        calls["n"] += 1
        raise FakeHttpError(404)

    with pytest.raises(FakeHttpError):
        execute_with_retry(thunk, sleep=lambda s: None)
    assert calls["n"] == 1


def test_retry_gives_up_after_max():
    def thunk():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        execute_with_retry(thunk, retries=2, sleep=lambda s: None)


def test_retry_non_transient_immediate():
    def thunk():
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        execute_with_retry(thunk, sleep=lambda s: None)
