"""Business-day deadline arithmetic for the (slow, human) reply timeout."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import Config


def add_business_days(start: datetime, n: float) -> datetime:
    """Return ``start`` advanced by ``n`` business days, skipping Sat/Sun.

    The current day is never counted: the result is the datetime ``n`` business
    days *after* ``start``, with time-of-day preserved. A fractional ``n`` adds
    its remainder as raw calendar time.
    """
    whole = int(n)
    step = 1 if whole >= 0 else -1
    current = start
    for _ in range(abs(whole)):
        current += timedelta(days=step)
        while current.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            current += timedelta(days=step)
    frac = n - whole
    if frac:
        current += timedelta(days=frac)
    return current


def deadline_ts_from_config(config: Config, now_ts: float) -> float:
    """Compute the absolute wall-clock deadline (epoch seconds) for a reply."""
    if config.reply_timeout_seconds is not None:
        return now_ts + config.reply_timeout_seconds
    start = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    return add_business_days(start, config.reply_timeout_business_days).timestamp()
