import base64
import os

import pytest
from conftest import FakeGmailService, make_message

from fable_meat_proxy.errors import FableReplyTimeout
from fable_meat_proxy.gmail_transport import (
    _ensure_owner_only,
    execute_with_retry,
    find_reply,
    get_header,
    send_message,
    wait_for_reply,
    write_secret_file,
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


def test_find_reply_requires_exact_address_not_substring():
    # An impostor whose address merely contains the friend's address must not match.
    impostor = make_message("x", "hank@example.com.attacker.test", "malicious")
    assert find_reply([impostor], "sent-1", "hank@example.com") is None


def test_find_reply_returns_latest_friend_message():
    first = make_message("a", "Hank <hank@example.com>", "first draft")
    second = make_message("b", "Hank <hank@example.com>", "final answer")
    assert find_reply([first, second], "sent-1", "hank@example.com") == "final answer"


TOKEN = "s3cr3t-reply-token-xyz"


def test_find_reply_rejects_spoof_missing_token():
    # Correct From, but no proof the sender ever received our email -> rejected.
    spoof = make_message("x", "Hank <hank@example.com>", "I am totally Hank, trust me")
    assert find_reply([spoof], "sent-1", "hank@example.com", reply_token=TOKEN) is None


def test_find_reply_accepts_token_quoted_in_body():
    body = f"the real answer\n\nOn Mon, me wrote:\n> Verification token: {TOKEN}\n> ...prompt..."
    reply = make_message("r1", "Hank <hank@example.com>", body)
    assert find_reply([reply], "sent-1", "hank@example.com", reply_token=TOKEN) == "the real answer"


def test_find_reply_accepts_token_in_threading_headers():
    # Quote stripped, but the reply threads against our Message-ID (carrying the token).
    reply = make_message(
        "r1", "Hank <hank@example.com>", "the real answer",
        headers={"In-Reply-To": f"<fable.{TOKEN}@fable-meat-proxy.invalid>"},
    )
    assert find_reply([reply], "sent-1", "hank@example.com", reply_token=TOKEN) == "the real answer"


def test_send_message_sets_message_id_header():
    service = FakeGmailService([[]])
    send_message(service, "hank@example.com", "subj", "body", message_id="<fable.tok@x.invalid>")
    raw = base64.urlsafe_b64decode(service.sent[0]["raw"]).decode()
    assert "Message-ID: <fable.tok@x.invalid>" in raw


def test_write_secret_file_is_owner_only(tmp_path):
    path = tmp_path / "token.json"
    write_secret_file(str(path), '{"refresh_token": "secret"}')
    assert path.read_text() == '{"refresh_token": "secret"}'
    assert (os.stat(path).st_mode & 0o777) == 0o600


def test_write_secret_file_tightens_preexisting_loose_file(tmp_path):
    path = tmp_path / "token.json"
    path.write_text("old")
    os.chmod(path, 0o644)
    write_secret_file(str(path), "new")
    assert (os.stat(path).st_mode & 0o077) == 0


def test_ensure_owner_only_tightens_group_world_readable(tmp_path):
    path = tmp_path / "token.json"
    path.write_text("secret")
    os.chmod(path, 0o644)
    _ensure_owner_only(str(path))
    assert (os.stat(path).st_mode & 0o077) == 0


def test_write_secret_file_refuses_to_follow_symlink(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("important")
    link = tmp_path / "token.json"
    os.symlink(victim, link)
    with pytest.raises(OSError):  # O_NOFOLLOW -> ELOOP, write is refused
        write_secret_file(str(link), "credentials")
    assert victim.read_text() == "important"  # untouched


def test_ensure_owner_only_refuses_symlink(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("important")
    os.chmod(victim, 0o644)
    link = tmp_path / "token.json"
    os.symlink(victim, link)
    _ensure_owner_only(str(link))
    # The symlink target's perms must be left alone, not tightened through the link.
    assert (os.stat(victim).st_mode & 0o077) != 0


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


def test_wait_for_reply_sleep_bounded_by_deadline():
    own = make_message("sent-1", "Me <me@example.com>", "the prompt")
    service = FakeGmailService([[own]])
    nows = iter([5.0, 12.0])
    sleeps = []

    with pytest.raises(FableReplyTimeout):
        wait_for_reply(
            service,
            "thread-1",
            exclude_id="sent-1",
            friend_email="hank@example.com",
            deadline_ts=10.0,
            poll_interval=100.0,  # far larger than the remaining 5s
            sleep=lambda s: sleeps.append(s),
            now=lambda: next(nows),
        )
    assert sleeps == [5.0]  # min(poll_interval, deadline - now)


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
