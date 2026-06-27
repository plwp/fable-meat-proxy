"""The human-in-the-loop Fable backend: email out, block, return the reply."""

from __future__ import annotations

import time
import uuid

from .config import Config
from .gmail_transport import send_message, wait_for_reply
from .parsing import first_user_snippet, format_prompt_email


def build_message(model: str, text: str, corr: str, *, input_tokens: int = 0, output_tokens: int = 0):
    """Construct a genuine Anthropic Message so callers see a normal response."""
    from anthropic.types import Message, TextBlock, Usage

    # model_construct skips validation so we stay compatible across SDK versions
    # without having to supply every field the current schema happens to require.
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


def complete_via_meat(
    config: Config,
    service,
    *,
    model,
    messages,
    system=None,
    max_tokens=None,
    corr_id: str | None = None,
    sleep=time.sleep,
    clock=time.monotonic,
    **_ignored,
):
    """Email the prompt to the friend, block for their reply, return a Message."""
    corr = corr_id or uuid.uuid4().hex[:8]
    subject = f"[{config.subject_prefix} {corr}] {first_user_snippet(messages)}"
    body = format_prompt_email(
        model=model, messages=messages, system=system, max_tokens=max_tokens, corr_id=corr
    )

    sent = send_message(service, config.friend_email, subject, body, sender=config.sender_email)
    reply = wait_for_reply(
        service,
        sent["threadId"],
        exclude_id=sent.get("id"),
        friend_email=config.friend_email,
        timeout=config.reply_timeout,
        poll_interval=config.poll_interval,
        sleep=sleep,
        clock=clock,
    )
    return build_message(model, reply, corr)
