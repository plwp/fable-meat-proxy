"""The human-in-the-loop Fable backend: email out, block, return the reply."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid

from .config import Config
from .gmail_transport import (
    send_message,
    wait_for_reply,
    wait_for_reply_async,
)
from .parsing import first_user_snippet, format_prompt_email
from .timing import deadline_ts_from_config

logger = logging.getLogger("fable_meat_proxy")


def build_message(model: str, text: str, corr: str, *, input_tokens: int = 0, output_tokens: int = 0):
    """Construct a genuine Anthropic Message so callers see a normal response."""
    from anthropic.types import Message, TextBlock, Usage

    try:
        return Message(
            id=f"msg_meat_{corr}",
            type="message",
            role="assistant",
            model=model,
            content=[TextBlock(type="text", text=text)],
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        )
    except Exception:  # pragma: no cover - version-compat fallback if schema changes
        block = TextBlock.model_construct(type="text", text=text, citations=None)
        usage = Usage.model_construct(input_tokens=input_tokens, output_tokens=output_tokens)
        return Message.model_construct(
            id=f"msg_meat_{corr}",
            type="message",
            role="assistant",
            model=model,
            content=[block],
            stop_reason="end_turn",
            stop_sequence=None,
            usage=usage,
        )


def _prepare(
    config: Config, model, messages, system, max_tokens, corr_id, now_ts, extra_params,
    reply_token=None,
):
    """Shared setup for the sync and async paths."""
    corr = corr_id or uuid.uuid4().hex[:8]
    # Unguessable per-request secret used to authenticate the human's reply.
    token = reply_token or secrets.token_urlsafe(18)
    subject = f"[{config.subject_prefix} {corr}] {first_user_snippet(messages)}"
    body = format_prompt_email(
        model=model,
        messages=messages,
        system=system,
        max_tokens=max_tokens,
        corr_id=corr,
        extra_params=extra_params,
        reply_token=token,
    )
    # The token also rides in the Message-ID so a properly-threaded reply echoes it
    # via In-Reply-To/References even if the human strips the quoted body.
    message_id = f"<fable.{token}@fable-meat-proxy.invalid>"
    deadline_ts = deadline_ts_from_config(config, now_ts)
    logger.info("Routing model %r to meat proxy (corr %s)", model, corr)
    return corr, subject, body, deadline_ts, token, message_id


def complete_via_meat(
    config: Config,
    service,
    *,
    model,
    messages,
    system=None,
    max_tokens=None,
    corr_id: str | None = None,
    reply_token: str | None = None,
    sleep=time.sleep,
    now=time.time,
    **extra_params,
):
    """Email the prompt to the friend, block for their reply, return a Message."""
    corr, subject, body, deadline_ts, token, message_id = _prepare(
        config, model, messages, system, max_tokens, corr_id, now(), extra_params,
        reply_token=reply_token,
    )
    sent = send_message(
        service, config.friend_email, subject, body,
        sender=config.sender_email, message_id=message_id,
    )
    reply = wait_for_reply(
        service,
        sent["threadId"],
        exclude_id=sent.get("id"),
        friend_email=config.friend_email,
        deadline_ts=deadline_ts,
        poll_interval=config.poll_interval,
        reply_token=token,
        sleep=sleep,
        now=now,
    )
    return build_message(model, reply, corr)


async def complete_via_meat_async(
    config: Config,
    service,
    *,
    model,
    messages,
    system=None,
    max_tokens=None,
    corr_id: str | None = None,
    reply_token: str | None = None,
    sleep=asyncio.sleep,
    now=time.time,
    lock=None,
    **extra_params,
):
    """Async variant of :func:`complete_via_meat`."""
    corr, subject, body, deadline_ts, token, message_id = _prepare(
        config, model, messages, system, max_tokens, corr_id, now(), extra_params,
        reply_token=reply_token,
    )

    def _send():
        return send_message(
            service, config.friend_email, subject, body,
            config.sender_email, message_id,
        )

    if lock is not None:
        async with lock:
            sent = await asyncio.to_thread(_send)
    else:
        sent = await asyncio.to_thread(_send)
    reply = await wait_for_reply_async(
        service,
        sent["threadId"],
        exclude_id=sent.get("id"),
        friend_email=config.friend_email,
        deadline_ts=deadline_ts,
        poll_interval=config.poll_interval,
        reply_token=token,
        sleep=sleep,
        now=now,
        lock=lock,
    )
    return build_message(model, reply, corr)
