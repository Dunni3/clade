"""Tests for the human-friendly timestamp formatter."""

from datetime import datetime

from clade.utils.timestamp import format_timestamp


class TestFormatTimestamp:

    def _now(self, iso: str) -> datetime:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))

    def test_just_now(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:30:30Z")
        )
        assert "just now" in result
        assert "EST" in result

    def test_minutes_ago(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:45:00Z")
        )
        assert "15 min ago" in result

    def test_hours_ago(self):
        result = format_timestamp(
            "2026-02-08T15:00:00Z", now=self._now("2026-02-08T18:00:00Z")
        )
        assert "3 hr ago" in result

    def test_days_ago(self):
        result = format_timestamp(
            "2026-02-06T12:00:00Z", now=self._now("2026-02-08T12:00:00Z")
        )
        assert "2 days ago" in result

    def test_one_day_ago(self):
        result = format_timestamp(
            "2026-02-07T12:00:00Z", now=self._now("2026-02-08T12:00:00Z")
        )
        assert "1 day ago" in result

    def test_old_message_no_relative(self):
        """Messages older than 7 days don't show relative time."""
        result = format_timestamp(
            "2026-01-20T12:00:00Z", now=self._now("2026-02-08T12:00:00Z")
        )
        assert "ago" not in result
        assert "EST" in result

    def test_utc_to_est_conversion(self):
        # 15:30 UTC = 10:30 AM EST
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:30:00Z")
        )
        assert "10:30 AM" in result
        assert "EST" in result

    def test_custom_timezone(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z",
            tz_name="US/Pacific",
            now=self._now("2026-02-08T15:30:00Z"),
        )
        assert "7:30 AM" in result
        assert "PST" in result

    def test_future_timestamp(self):
        result = format_timestamp(
            "2026-02-08T16:00:00Z", now=self._now("2026-02-08T15:00:00Z")
        )
        assert "in the future" in result

    def test_format_includes_date(self):
        result = format_timestamp(
            "2026-02-08T15:30:00Z", now=self._now("2026-02-08T15:30:00Z")
        )
        assert "Feb 8" in result
