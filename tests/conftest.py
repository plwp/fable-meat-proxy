"""Shared fakes for exercising the Gmail transport without real Google APIs."""

from __future__ import annotations

import base64
import email as _email


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def encode_part(text: str) -> dict:
    return {"mimeType": "text/plain", "body": {"data": b64(text)}}


def make_message(msg_id: str, sender: str, text: str, *, headers: dict | None = None) -> dict:
    hdrs = [{"name": "From", "value": sender}]
    for name, value in (headers or {}).items():
        hdrs.append({"name": name, "value": value})
    return {
        "id": msg_id,
        "payload": {
            "headers": hdrs,
            **encode_part(text),
        },
    }


class _Execute:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _MessagesEndpoint:
    def __init__(self, service):
        self._service = service

    def send(self, userId, body):  # noqa: N803 - mirror Gmail API kwarg
        self._service.sent.append(body)
        return _Execute({"id": "sent-1", "threadId": "thread-1"})

    def getProfile(self, userId):  # noqa: N803
        return _Execute({"emailAddress": "me@example.com"})


class _ThreadsEndpoint:
    def __init__(self, service):
        self._service = service

    def get(self, userId, id, format):  # noqa: A002, N803 - mirror Gmail API
        # Reveal messages progressively so polling logic gets exercised.
        self._service.poll_count += 1
        visible = self._service.thread_timeline[
            min(self._service.poll_count - 1, len(self._service.thread_timeline) - 1)
        ]
        return _Execute({"messages": visible})


class _Users:
    def __init__(self, service):
        self._service = service

    def messages(self):
        return _MessagesEndpoint(self._service)

    def threads(self):
        return _ThreadsEndpoint(self._service)

    def getProfile(self, userId):  # noqa: N803
        return _MessagesEndpoint(self._service).getProfile(userId)


class FakeGmailService:
    """Minimal stand-in for the googleapiclient Gmail service.

    ``thread_timeline`` is a list of message-lists, one per poll: the Nth poll
    sees ``thread_timeline[N]``, letting tests simulate a reply arriving late.
    """

    def __init__(self, thread_timeline):
        self.sent: list[dict] = []
        self.thread_timeline = thread_timeline
        self.poll_count = 0

    def users(self):
        return _Users(self)


class _AutoReplyMessages:
    def __init__(self, service):
        self._service = service

    def send(self, userId, body):  # noqa: N803 - mirror Gmail API kwarg
        self._service._on_send(body)
        return _Execute({"id": "sent-1", "threadId": "thread-1"})

    def getProfile(self, userId):  # noqa: N803
        return _Execute({"emailAddress": "me@example.com"})


class _AutoReplyThreads:
    def __init__(self, service):
        self._service = service

    def get(self, userId, id, format):  # noqa: A002, N803 - mirror Gmail API
        self._service.poll_count += 1
        return _Execute({"messages": self._service._visible()})


class _AutoReplyUsers:
    def __init__(self, service):
        self._service = service

    def messages(self):
        return _AutoReplyMessages(self._service)

    def threads(self):
        return _AutoReplyThreads(self._service)


class AutoReplyGmailService:
    """Models a friend who replies by quoting the original email, as a real client would.

    On send() it decodes the outgoing message, then prepares a reply that places the
    answer above the quoted original (which carries the verification token) and sets
    In-Reply-To/References to the sent Message-ID. The reply appears on the second
    poll. This exercises the transport's reply-authentication path end to end without
    the token having to be known in advance.
    """

    def __init__(self, answer: str = "the meaty answer", friend: str = "hank@example.com"):
        self.answer = answer
        self.friend = friend
        self.sent: list[dict] = []
        self.poll_count = 0
        self._sent_msg: dict | None = None
        self._reply_msg: dict | None = None

    def users(self):
        return _AutoReplyUsers(self)

    def _on_send(self, body: dict) -> None:
        self.sent.append(body)
        parsed = _email.message_from_bytes(base64.urlsafe_b64decode(body["raw"]))
        original = parsed.get_payload(decode=True).decode()
        message_id = parsed.get("Message-ID", "")
        self._sent_msg = make_message("sent-1", "me@example.com", original)
        quoted = "\n".join("> " + line for line in original.splitlines())
        reply_body = f"{self.answer}\n\nOn Mon Jan 1 2026, me@example.com wrote:\n{quoted}"
        self._reply_msg = make_message(
            "reply-1",
            f"Hank <{self.friend}>",
            reply_body,
            headers={"In-Reply-To": message_id, "References": message_id},
        )

    def _visible(self) -> list[dict]:
        if self._sent_msg is None:
            return []
        if self.poll_count <= 1:
            return [self._sent_msg]
        return [self._sent_msg, self._reply_msg]
