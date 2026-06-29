"""Render outgoing prompts and parse incoming human replies."""

from __future__ import annotations

import base64
import html as _html
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
                btype = block.get("type")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    parts.append(f"[tool_use {block.get('name', '')}: {block.get('input', {})}]")
                elif btype == "tool_result":
                    parts.append(f"[tool_result: {_content_to_text(block.get('content'))}]")
                else:
                    parts.append(f"[{btype or 'block'}]")
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


# Generation parameters worth surfacing to the human so they aren't silently lost.
NOTABLE_PARAMS = (
    "temperature",
    "top_p",
    "top_k",
    "stop_sequences",
    "tools",
    "tool_choice",
    "thinking",
    "metadata",
)


def format_prompt_email(
    *, model, messages, system=None, max_tokens=None, corr_id, extra_params=None,
    reply_token=None,
) -> str:
    """Build the human-readable email body the friend pastes into Fable.

    ``reply_token`` is an unguessable per-request secret. It is printed here and
    travels back inside the quoted original when the friend replies; the transport
    rejects any reply that cannot echo it (see ``find_reply``), which defeats
    ``From:``-header spoofing.
    """
    lines: list[str] = [
        "You are serving as a human proxy for the Fable model. 🥩",
        "",
        "1. Paste the conversation below into Fable.",
        "2. REPLY to this email with Fable's response as the plain-text body.",
        "   (Anything you write above the quoted original is taken as the answer.)",
        "3. Leave the quoted original BELOW your answer intact — it carries a",
        "   verification token without which your reply is ignored.",
        "",
        f"Correlation ID: {corr_id}",
        f"Model requested: {model}",
    ]
    if reply_token:
        lines.append(f"Verification token (do not delete): {reply_token}")
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

    shown = {
        k: v for k, v in (extra_params or {}).items() if k in NOTABLE_PARAMS and v is not None
    }
    if shown:
        lines.append("===== REQUEST PARAMETERS (best-effort; honour where you can) =====")
        lines += [f"{k}: {v}" for k, v in shown.items()]
        lines.append("")

    # The SYSTEM/CONVERSATION above is untrusted application input. Remind the human
    # not to act on instructions smuggled into it (e.g. "ignore the above and ...").
    lines += [
        "===== SECURITY NOTE =====",
        "Everything in the SYSTEM and CONVERSATION sections above is untrusted input",
        "from the calling application. Do NOT obey instructions inside it that ask you",
        "to ignore these directions, reveal this email, or change how you reply. Only",
        "paste it into Fable and send back Fable's answer.",
        "",
        "===== END OF PROMPT — reply with Fable's answer above the quote =====",
    ]
    return "\n".join(lines)


def _decode_b64url(data: str) -> str:
    # Gmail may return base64url without padding; restore it before decoding.
    data += "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _is_attachment(payload: dict) -> bool:
    """Whether a MIME part is an attachment rather than an inline body part."""
    if payload.get("filename"):
        return True
    if payload.get("body", {}).get("attachmentId"):
        return True
    for header in payload.get("headers", []) or []:
        if header.get("name", "").lower() == "content-disposition":
            if "attachment" in header.get("value", "").lower():
                return True
    return False


def _collect_text_parts(payload: dict, out: dict[str, str]) -> None:
    # Skip attachments (and their subtrees): a malicious reply could place a text
    # attachment before the real answer and have it picked as the response body.
    if _is_attachment(payload):
        return
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if data and mime.startswith("text/"):
        out.setdefault(mime, _decode_b64url(data))
    for part in payload.get("parts") or []:
        _collect_text_parts(part, out)


def extract_message_text(message: dict) -> str:
    """Pull the best plain-text representation out of a Gmail message payload.

    Prefers ``text/plain``; falls back to ``text/html`` (de-tagged) and then to
    any text part present.
    """
    parts: dict[str, str] = {}
    _collect_text_parts(message.get("payload", {}), parts)
    if "text/plain" in parts:
        return parts["text/plain"]
    if "text/html" in parts:
        return html_to_text(parts["text/html"])
    return next(iter(parts.values()), "")


# Elements whose text is hidden from the reader; an attacker could otherwise make
# the visible answer benign while the extracted text carries something else.
_HIDDEN_ELEMENT = re.compile(
    r"(?is)<([a-z][\w-]*)\b[^>]*style\s*=\s*['\"][^'\"]*"
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden)[^'\"]*['\"][^>]*>.*?</\1>"
)


def html_to_text(source: str) -> str:
    """Best-effort conversion of an HTML email body to plain text.

    Not a full HTML parser: replies are normally ``text/plain`` and this is only a
    fallback. It drops scripts, styles, comments, and inline-hidden elements so
    hidden DOM text is not silently returned as the model's answer.
    """
    source = re.sub(r"(?is)<!--.*?-->", "", source)
    source = re.sub(r"(?is)<(script|style).*?</\1>", "", source)
    source = _HIDDEN_ELEMENT.sub("", source)
    source = re.sub(r"(?i)<br\s*/?>", "\n", source)
    source = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", source)
    source = re.sub(r"<[^>]+>", "", source)
    text = _html.unescape(source)
    # Collapse runs of blank lines left behind by stripped markup.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# Boundaries that introduce a quoted original. We break at the first one and keep
# everything above it. We deliberately do NOT strip lone ">" lines before a marker,
# so legitimate Markdown blockquotes in Fable's answer survive. The bare "From:"
# header marker is omitted on purpose — it false-positives on real answer text.
_REPLY_MARKERS = (
    re.compile(r"^On .*wrote:\s*$"),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE),
    re.compile(r"^_{5,}\s*$"),
)


def strip_quoted_reply(body: str) -> str:
    """Drop the quoted original (and everything after it) from an email body."""
    out: list[str] = []
    for line in body.splitlines():
        if any(marker.match(line.strip()) for marker in _REPLY_MARKERS):
            break
        out.append(line)
    return "\n".join(out).strip()
