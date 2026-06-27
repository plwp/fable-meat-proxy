"""Environment-driven configuration for the meat proxy."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # .env is convenient but optional
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a declared dep
    pass


def is_fable_model(model: str | None) -> bool:
    """A model is served by the meat proxy iff its name mentions Fable."""
    return bool(model) and "fable" in model.lower()


@dataclass
class Config:
    """Settings for the human-in-the-loop Fable backend."""

    friend_email: str
    sender_email: str = "me"
    credentials_path: str = "credentials.json"
    token_path: str = "token.json"
    subject_prefix: str = "fable-meat"
    reply_timeout: float = 3600.0
    poll_interval: float = 15.0

    @classmethod
    def from_env(cls) -> "Config":
        friend = os.environ.get("FABLE_FRIEND_EMAIL")
        if not friend:
            raise RuntimeError(
                "FABLE_FRIEND_EMAIL is not set. Point it at your American friend's "
                "inbox (see .env.example)."
            )
        return cls(
            friend_email=friend,
            sender_email=os.environ.get("FABLE_SENDER_EMAIL", "me"),
            credentials_path=os.environ.get("FABLE_GMAIL_CREDENTIALS", "credentials.json"),
            token_path=os.environ.get("FABLE_GMAIL_TOKEN", "token.json"),
            subject_prefix=os.environ.get("FABLE_SUBJECT_PREFIX", "fable-meat"),
            reply_timeout=float(os.environ.get("FABLE_REPLY_TIMEOUT", "3600")),
            poll_interval=float(os.environ.get("FABLE_POLL_INTERVAL", "15")),
        )
