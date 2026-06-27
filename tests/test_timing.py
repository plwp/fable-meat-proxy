from datetime import datetime, timezone

from fable_meat_proxy import Config
from fable_meat_proxy.timing import add_business_days, deadline_ts_from_config


def _utc(y, m, d, hh=12):
    return datetime(y, m, d, hh, 0, tzinfo=timezone.utc)


def test_add_business_days_skips_weekend():
    # Friday 2026-06-26 + 1 business day -> Monday 2026-06-29
    assert add_business_days(_utc(2026, 6, 26), 1).date().isoformat() == "2026-06-29"


def test_add_business_days_seven_from_wednesday():
    # Wednesday 2026-06-24 + 7 business days -> Friday 2026-07-03
    assert add_business_days(_utc(2026, 6, 24), 7).date().isoformat() == "2026-07-03"


def test_add_business_days_preserves_time_of_day():
    result = add_business_days(_utc(2026, 6, 24, hh=9), 2)
    assert result.hour == 9


def test_deadline_seconds_override():
    cfg = Config(friend_email="a@b.com", reply_timeout_seconds=50)
    assert deadline_ts_from_config(cfg, 1000.0) == 1050.0


def test_deadline_business_days_is_days_in_future():
    cfg = Config(friend_email="a@b.com")  # default 7 business days
    now_ts = _utc(2026, 6, 24).timestamp()
    # 7 business days spans at least 9 calendar days (one weekend).
    assert deadline_ts_from_config(cfg, now_ts) >= now_ts + 9 * 86400
