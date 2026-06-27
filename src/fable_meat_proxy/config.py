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


def is_fable_model(model: str | None) -> bool:
    """A model is served by the meat proxy iff its name mentions Fable."""
    return bool(model) and "fable" in model.lower()


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
            poll_interval=_env_float("FABLE_POLL_INTERVAL", 120.0),
        )
