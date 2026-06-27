"""Gmail API transport: OAuth, sending, and polling a thread for the reply."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from email.mime.text import MIMEText
from email.utils import parseaddr

from .errors import FableReplyTimeout
from .parsing import extract_message_text, strip_quoted_reply

logger = logging.getLogger("fable_meat_proxy")

# Least privilege: send mail + read the reply thread. No modify/label/delete.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

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
        # token.json is a secret (refresh token); keep it owner-only.
        try:
            os.chmod(config.token_path, 0o600)
        except OSError:  # pragma: no cover - non-POSIX filesystems
            logger.warning("Could not restrict permissions on %s", config.token_path)

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
    # "me" is a Gmail API placeholder, not a valid address — let Gmail fill From.
    if sender and sender != "me":
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
    """Return the friend's latest reply text from a thread, or None if none yet.

    Matches the friend by *exact* parsed address (display names and substrings do
    not count) and returns the most recent qualifying message, since Gmail returns
    thread messages in chronological order.
    """
    target = friend_email.strip().lower()
    latest = None
    for message in messages:
        if message.get("id") == exclude_id:
            continue
        if parseaddr(get_header(message, "From"))[1].lower() == target:
            latest = message
    if latest is None:
        return None
    return strip_quoted_reply(extract_message_text(latest))


def _timeout_error(friend_email: str, thread_id: str) -> FableReplyTimeout:
    return FableReplyTimeout(
        f"No Fable reply from {friend_email} before the deadline (thread {thread_id})."
    )


def _next_sleep(poll_interval: float, deadline_ts: float, now_ts: float) -> float:
    """Sleep no longer than the remaining time so we never overshoot the deadline."""
    return min(poll_interval, max(0.0, deadline_ts - now_ts))


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
        now_ts = now()
        if now_ts >= deadline_ts:
            raise _timeout_error(friend_email, thread_id)
        logger.debug("No reply yet on thread %s; polling again", thread_id)
        sleep(_next_sleep(poll_interval, deadline_ts, now_ts))


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
    lock=None,
) -> str:
    """Async variant of :func:`wait_for_reply`; blocking Gmail calls run in a thread.

    ``lock`` (an ``asyncio.Lock``) serializes access to the shared, not-thread-safe
    googleapiclient service when multiple Fable requests run concurrently.
    """

    async def _poll():
        if lock is None:
            return await asyncio.to_thread(get_thread_messages, service, thread_id)
        async with lock:
            return await asyncio.to_thread(get_thread_messages, service, thread_id)

    while True:
        text = find_reply(await _poll(), exclude_id, friend_email)
        if text is not None:
            logger.info("Received Fable reply on thread %s", thread_id)
            return text
        now_ts = now()
        if now_ts >= deadline_ts:
            raise _timeout_error(friend_email, thread_id)
        logger.debug("No reply yet on thread %s; polling again", thread_id)
        await sleep(_next_sleep(poll_interval, deadline_ts, now_ts))
