"""Shared fakes for exercising the Gmail transport without real Google APIs."""

from __future__ import annotations

import base64


def encode_part(text: str) -> dict:
    data = base64.urlsafe_b64encode(text.encode()).decode()
    return {"mimeType": "text/plain", "body": {"data": data}}


def make_message(msg_id: str, sender: str, text: str) -> dict:
    return {
        "id": msg_id,
        "payload": {
            "headers": [{"name": "From", "value": sender}],
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
