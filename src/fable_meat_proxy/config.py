"""Environment-driven configuration for the meat proxy."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from .errors import FableConfigError

try:  # .env is convenient but optional
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a declared dep
    pass

logger = logging.getLogger("fable_meat_proxy")

# Models routed to the human backend. An *exact* (case-insensitive) allowlist —
# never a substring test: "claude-opus-4-fable-debug" or a caller-supplied
# "not-fable" must NOT divert a private prompt to your friend's inbox.
DEFAULT_FABLE_MODELS = frozenset({"claude-fable-5"})

# Polling faster than this in production just burns Gmail quota for no benefit —
# a human reply takes minutes at best. Direct Config(...) construction may still
# pass a smaller value (tests inject a fake sleep); only from_env() clamps.
MIN_POLL_INTERVAL_SECONDS = 5.0


def fable_models_from_env() -> frozenset[str]:
    """Resolve the Fable model allowlist from ``FABLE_MODELS`` (comma-separated)."""
    raw = os.environ.get("FABLE_MODELS")
    if not raw:
        return DEFAULT_FABLE_MODELS
    models = frozenset(m.strip().lower() for m in raw.split(",") if m.strip())
    return models or DEFAULT_FABLE_MODELS


def is_fable_model(model: str | None, models: frozenset[str] | None = None) -> bool:
    """A model is served by the meat proxy iff it is in the exact allowlist.

    ``models`` defaults to :data:`DEFAULT_FABLE_MODELS`. Matching is exact and
    case-insensitive — substring matches are deliberately rejected so an
    untrusted model string cannot reroute traffic to the human/email backend.
    """
    if not model:
        return False
    allow = DEFAULT_FABLE_MODELS if models is None else models
    return model.lower() in {m.lower() for m in allow}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise FableConfigError(f"{name} must be a number, got {raw!r}") from exc


@dataclass
class Config:
    """Settings for the human-in-the-loop Fable backend.

    The reply timeout defaults to ``reply_timeout_business_days`` (weekends are
    skipped, computed against the wall clock) because a human needs days to
    respond. ``reply_timeout_seconds`` overrides that with a raw seconds budget
    when set — primarily useful for tests and short-lived demos.
    """

    friend_email: str
    sender_email: str = "me"
    credentials_path: str = "credentials.json"
    token_path: str = "token.json"
    subject_prefix: str = "fable-meat"
    reply_timeout_business_days: float = 7.0
    reply_timeout_seconds: float | None = None
    poll_interval: float = 120.0
    fable_models: frozenset[str] = DEFAULT_FABLE_MODELS

    def __post_init__(self) -> None:
        if not self.friend_email or "@" not in self.friend_email:
            raise FableConfigError(
                f"friend_email must be a valid address, got {self.friend_email!r}"
            )
        if self.poll_interval < 0:
            raise FableConfigError("poll_interval must be non-negative")
        if self.reply_timeout_business_days < 0:
            raise FableConfigError("reply_timeout_business_days must be non-negative")
        if self.reply_timeout_seconds is not None and self.reply_timeout_seconds < 0:
            raise FableConfigError("reply_timeout_seconds must be non-negative")

    @classmethod
    def from_env(cls) -> "Config":
        friend = os.environ.get("FABLE_FRIEND_EMAIL")
        if not friend:
            raise FableConfigError(
                "FABLE_FRIEND_EMAIL is not set. Point it at your American friend's "
                "inbox (see .env.example)."
            )
        seconds_override = os.environ.get("FABLE_REPLY_TIMEOUT_SECONDS")
        poll_interval = _env_float("FABLE_POLL_INTERVAL", 120.0)
        if 0 <= poll_interval < MIN_POLL_INTERVAL_SECONDS:
            logger.warning(
                "FABLE_POLL_INTERVAL=%s is below the %ss minimum; clamping to avoid "
                "busy-polling Gmail.",
                poll_interval,
                MIN_POLL_INTERVAL_SECONDS,
            )
            poll_interval = MIN_POLL_INTERVAL_SECONDS
        return cls(
            friend_email=friend,
            sender_email=os.environ.get("FABLE_SENDER_EMAIL", "me"),
            credentials_path=os.environ.get("FABLE_GMAIL_CREDENTIALS", "credentials.json"),
            token_path=os.environ.get("FABLE_GMAIL_TOKEN", "token.json"),
            subject_prefix=os.environ.get("FABLE_SUBJECT_PREFIX", "fable-meat"),
            reply_timeout_business_days=_env_float("FABLE_REPLY_TIMEOUT_BUSINESS_DAYS", 7.0),
            reply_timeout_seconds=(
                _env_float("FABLE_REPLY_TIMEOUT_SECONDS", 0.0)
                if seconds_override not in (None, "")
                else None
            ),
            poll_interval=poll_interval,
            fable_models=fable_models_from_env(),
        )
