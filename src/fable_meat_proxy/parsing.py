"""Render outgoing prompts and parse incoming human replies."""

from __future__ import annotations

import re


def _content_to_text(content) -> str:
    """Flatten Anthropic message content (str or list of blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                else:
                    parts.append(f"[{block.get('type', 'block')}]")
            else:
                text = getattr(block, "text", None)
                parts.append(text if text is not None else str(block))
    else:
        return str(content)
    return "\n".join(parts)


def _role_of(message) -> str:
    if isinstance(message, dict):
        return str(message.get("role", "?")).upper()
    return str(getattr(message, "role", "?")).upper()


def _content_of(message):
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def first_user_snippet(messages, limit: int = 60) -> str:
    """A short subject-line snippet drawn from the first user turn."""
    for message in messages or []:
        if _role_of(message) == "USER":
            text = _content_to_text(_content_of(message)).strip().replace("\n", " ")
            if text:
                return text[:limit]
    return "(no prompt)"


def format_prompt_email(*, model, messages, system=None, max_tokens=None, corr_id) -> str:
    """Build the human-readable email body the friend pastes into Fable."""
    lines: list[str] = [
        "You are serving as a human proxy for the Fable model. 🥩",
        "",
        "1. Paste the conversation below into Fable.",
        "2. REPLY to this email with Fable's response as the plain-text body.",
        "   (Anything you write above the quoted original is taken as the answer.)",
        "",
        f"Correlation ID: {corr_id}",
        f"Model requested: {model}",
    ]
    if max_tokens:
        lines.append(f"Max tokens: {max_tokens}")
    lines.append("")

    system_text = _content_to_text(system)
    if system_text.strip():
        lines += ["===== SYSTEM =====", system_text, ""]

    lines.append("===== CONVERSATION =====")
    for message in messages or []:
        lines.append(f"--- {_role_of(message)} ---")
        lines.append(_content_to_text(_content_of(message)))
        lines.append("")
    lines.append("===== END OF PROMPT — reply with Fable's answer above the quote =====")
    return "\n".join(lines)


_REPLY_MARKERS = (
    re.compile(r"^On .*wrote:\s*$"),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE),
    re.compile(r"^_{5,}\s*$"),
    re.compile(r"^From:\s.+", re.IGNORECASE),
)


def strip_quoted_reply(body: str) -> str:
    """Drop quoted original text and trailing reply chrome from an email body."""
    out: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if any(marker.match(stripped) for marker in _REPLY_MARKERS):
            break
        if stripped.startswith(">"):
            continue
        out.append(line)
    return "\n".join(out).strip()
