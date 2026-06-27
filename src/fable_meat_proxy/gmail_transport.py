"""Gmail API transport: OAuth, sending, and polling a thread for the reply."""

from __future__ import annotations

import base64
import os
import time
from email.mime.text import MIMEText

# gmail.modify covers both send and read of the authenticated account.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def build_service(config):
    """Build an authenticated Gmail API service, minting/refreshing token.json."""
    # Imported lazily so the routing/parsing logic can be tested without google libs.
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(config.token_path):
        creds = Credentials.from_authorized_user_file(config.token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(config.credentials_path):
                raise RuntimeError(
                    f"Gmail OAuth client secret not found at {config.credentials_path!r}. "
                    "Download a Desktop-app OAuth client from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(config.credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(config.token_path, "w") as fh:
            fh.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_message(service, to: str, subject: str, body: str, sender: str = "me") -> dict:
    """Send a plain-text email; returns the sent message resource (with threadId)."""
    msg = MIMEText(body)
    msg["to"] = to
    msg["from"] = sender
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )


def get_thread_messages(service, thread_id: str) -> list[dict]:
    thread = (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )
    return thread.get("messages", [])


def get_header(message: dict, name: str) -> str:
    headers = message.get("payload", {}).get("headers", [])
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def extract_message_text(message: dict) -> str:
    """Pull the text/plain body out of a Gmail message payload."""
    return _walk_parts(message.get("payload", {}))


def _walk_parts(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if mime == "text/plain" and data:
        return _decode(data)
    parts = payload.get("parts") or []
    for part in parts:  # prefer text/plain anywhere in the tree
        if part.get("mimeType") == "text/plain":
            text = _walk_parts(part)
            if text:
                return text
    for part in parts:  # fall back to the first part that yields anything
        text = _walk_parts(part)
        if text:
            return text
    if data:
        return _decode(data)
    return ""


def wait_for_reply(
    service,
    thread_id: str,
    *,
    exclude_id: str | None,
    friend_email: str,
    timeout: float,
    poll_interval: float,
    sleep=time.sleep,
    clock=time.monotonic,
) -> str:
    """Block until the friend replies in the thread, then return their text."""
    from .parsing import strip_quoted_reply

    deadline = clock() + timeout
    while True:
        for message in get_thread_messages(service, thread_id):
            if message.get("id") == exclude_id:
                continue
            if friend_email.lower() in get_header(message, "From").lower():
                return strip_quoted_reply(extract_message_text(message))
        if clock() >= deadline:
            raise TimeoutError(
                f"No Fable reply from {friend_email} within {timeout}s (thread {thread_id})."
            )
        sleep(poll_interval)
