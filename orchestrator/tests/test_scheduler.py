import pytest
from app.scheduler import SmartScheduler
from datetime import datetime, timedelta


def test_new_account_warmup_delay():
    scheduler = SmartScheduler()
    phone = {"warmup_days": 2, "error_count": 0, "timezone": "UTC"}
    delay = scheduler.compute_delay_minutes(phone, last_post_at=None)
    assert delay >= 120


def test_active_account_normal_delay():
    scheduler = SmartScheduler()
    phone = {"warmup_days": 30, "error_count": 0, "timezone": "UTC"}
    delay = scheduler.compute_delay_minutes(phone, last_post_at=None)
    assert 30 <= delay <= 120


def test_high_error_count_increases_delay():
    scheduler = SmartScheduler()
    phone_normal = {"warmup_days": 30, "error_count": 0, "timezone": "UTC"}
    phone_risky = {"warmup_days": 30, "error_count": 10, "timezone": "UTC"}
    normal_delay = scheduler.compute_delay_minutes(phone_normal, last_post_at=None)
    risky_delay = scheduler.compute_delay_minutes(phone_risky, last_post_at=None)
    assert risky_delay > normal_delay
