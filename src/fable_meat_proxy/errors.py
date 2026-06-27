"""Exception types raised by the meat proxy."""

from __future__ import annotations


class FableMeatError(Exception):
    """Base class for all fable-meat-proxy errors."""


class FableReplyTimeout(FableMeatError, TimeoutError):
    """Raised when the human proxy does not reply within the configured timeout.

    Subclasses :class:`TimeoutError` so existing ``except TimeoutError`` handlers
    keep working.
    """


class FableConfigError(FableMeatError):
    """Raised when required configuration is missing or invalid."""
