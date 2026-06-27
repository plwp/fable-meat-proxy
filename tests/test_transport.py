from conftest import FakeGmailService, make_message

from fable_meat_proxy.gmail_transport import (
    extract_message_text,
    get_header,
    send_message,
    wait_for_reply,
)


def test_send_message_builds_raw_payload():
    service = FakeGmailService([[]])
    result = send_message(service, "hank@example.com", "subject", "body", sender="me")
    assert result["threadId"] == "thread-1"
    assert len(service.sent) == 1
    assert "raw" in service.sent[0]


def test_extract_and_header():
    msg = make_message("m1", "Hank <hank@example.com>", "hello world")
    assert extract_message_text(msg) == "hello world"
    assert "hank@example.com" in get_header(msg, "From")


def test_wait_for_reply_skips_own_message_and_returns_friend_reply():
    own = make_message("sent-1", "Me <me@example.com>", "the prompt")
    reply = make_message("r1", "Hank <hank@example.com>", "Fable says hi")
    # Poll 1: only our sent message. Poll 2: the reply has arrived.
    service = FakeGmailService([[own], [own, reply]])

    sleeps = []
    text = wait_for_reply(
        service,
        "thread-1",
        exclude_id="sent-1",
        friend_email="hank@example.com",
        timeout=100,
        poll_interval=5,
        sleep=lambda s: sleeps.append(s),
        clock=lambda: 0.0,
    )
    assert text == "Fable says hi"
    assert sleeps == [5]  # polled once, slept once, found it on the second poll


def test_wait_for_reply_times_out():
    own = make_message("sent-1", "Me <me@example.com>", "the prompt")
    service = FakeGmailService([[own]])
    clock = iter([0.0, 0.0, 200.0])

    try:
        wait_for_reply(
            service,
            "thread-1",
            exclude_id="sent-1",
            friend_email="hank@example.com",
            timeout=100,
            poll_interval=5,
            sleep=lambda s: None,
            clock=lambda: next(clock),
        )
    except TimeoutError as exc:
        assert "within 100" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected TimeoutError")
