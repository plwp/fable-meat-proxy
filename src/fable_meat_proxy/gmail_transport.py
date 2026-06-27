"""Gmail API transport: OAuth, sending, and polling a thread for the reply."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from email.mime.text import MIMEText

from .errors import FableReplyTimeout
from .parsing import extract_message_text, strip_quoted_reply

logger = logging.getLogger("fable_meat_proxy")

# gmail.modify covers both send and read of the authenticated account.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}


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
            logger.info("Refreshing expired Gmail credentials")
            creds.refresh(Request())
        else:
            if not os.path.exists(config.credentials_path):
                raise RuntimeError(
                    f"Gmail OAuth client secret not found at {config.credentials_path!r}. "
                    "Download a Desktop-app OAuth client from Google Cloud Console."
                )
            logger.info("Running Gmail OAuth flow")
            flow = InstalledAppFlow.from_client_secrets_file(config.credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(config.token_path, "w") as fh:
            fh.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _is_transient(exc: Exception) -> bool:
    """Whether a Gmail call failure is worth retrying."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status is not None:
        try:
            return int(status) in _TRANSIENT_HTTP_STATUS
        except (TypeError, ValueError):
            return False
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def execute_with_retry(thunk, *, retries: int = 4, base_delay: float = 1.0, sleep=time.sleep):
    """Run ``thunk`` (a Gmail request `.execute()`), retrying transient errors."""
    attempt = 0
    while True:
        try:
            return thunk()
        except Exception as exc:  # noqa: BLE001 - we re-raise non-transient below
            attempt += 1
            if attempt > retries or not _is_transient(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Transient Gmail error (attempt %d/%d): %s; retrying in %.1fs",
                attempt,
                retries,
                exc,
                delay,
            )
            sleep(delay)


def send_message(service, to: str, subject: str, body: str, sender: str = "me") -> dict:
    """Send a plain-text email; returns the sent message resource (with threadId)."""
    msg = MIMEText(body)
    msg["to"] = to
    msg["from"] = sender
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = execute_with_retry(
        lambda: service.users().messages().send(userId="me", body={"raw": raw}).execute()
    )
    logger.info("Sent Fable prompt to %s (thread %s)", to, result.get("threadId"))
    return result


def get_thread_messages(service, thread_id: str) -> list[dict]:
    thread = execute_with_retry(
        lambda: service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    )
    return thread.get("messages", [])


def get_header(message: dict, name: str) -> str:
    headers = message.get("payload", {}).get("headers", [])
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def find_reply(messages: list[dict], exclude_id: str | None, friend_email: str) -> str | None:
    """Return the friend's reply text from a thread, or None if not present yet."""
    for message in messages:
        if message.get("id") == exclude_id:
            continue
        if friend_email.lower() in get_header(message, "From").lower():
            return strip_quoted_reply(extract_message_text(message))
    return None


def _timeout_error(friend_email: str, thread_id: str) -> FableReplyTimeout:
    return FableReplyTimeout(
        f"No Fable reply from {friend_email} before the deadline (thread {thread_id})."
    )


def wait_for_reply(
    service,
    thread_id: str,
    *,
    exclude_id: str | None,
    friend_email: str,
    deadline_ts: float,
    poll_interval: float,
    sleep=time.sleep,
    now=time.time,
) -> str:
    """Block until the friend replies in the thread, then return their text."""
    while True:
        text = find_reply(get_thread_messages(service, thread_id), exclude_id, friend_email)
        if text is not None:
            logger.info("Received Fable reply on thread %s", thread_id)
            return text
        if now() >= deadline_ts:
            raise _timeout_error(friend_email, thread_id)
        logger.debug("No reply yet on thread %s; sleeping %.0fs", thread_id, poll_interval)
        sleep(poll_interval)


async def wait_for_reply_async(
    service,
    thread_id: str,
    *,
    exclude_id: str | None,
    friend_email: str,
    deadline_ts: float,
    poll_interval: float,
    sleep=asyncio.sleep,
    now=time.time,
) -> str:
    """Async variant of :func:`wait_for_reply`; blocking Gmail calls run in a thread."""
    while True:
        messages = await asyncio.to_thread(get_thread_messages, service, thread_id)
        text = find_reply(messages, exclude_id, friend_email)
        if text is not None:
            logger.info("Received Fable reply on thread %s", thread_id)
            return text
        if now() >= deadline_ts:
            raise _timeout_error(friend_email, thread_id)
        logger.debug("No reply yet on thread %s; sleeping %.0fs", thread_id, poll_interval)
        await sleep(poll_interval)
