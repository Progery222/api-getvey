from datetime import datetime, timedelta


class SmartScheduler:
    BASE_DELAY_MINUTES = 60
    WARMUP_THRESHOLD_DAYS = 14
    WARMUP_DELAY_MINUTES = 180
    ERROR_MULTIPLIER = 15

    def compute_delay_minutes(self, phone: dict, last_post_at: datetime | None) -> int:
        delay = self.BASE_DELAY_MINUTES

        if phone.get("warmup_days", 0) < self.WARMUP_THRESHOLD_DAYS:
            delay = self.WARMUP_DELAY_MINUTES

        error_count = phone.get("error_count", 0)
        delay += error_count * self.ERROR_MULTIPLIER

        return delay

    def next_scheduled_at(self, phone: dict, last_post_at: datetime | None) -> datetime:
        delay = self.compute_delay_minutes(phone, last_post_at)
        base = last_post_at or datetime.utcnow()
        return base + timedelta(minutes=delay)
