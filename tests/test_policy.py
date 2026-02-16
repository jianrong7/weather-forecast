from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from weather_bot.policy import should_send_alert


SG = timezone(timedelta(hours=8))


class PolicyTests(unittest.TestCase):
    def test_send_on_upward_transition(self) -> None:
        risk = SimpleNamespace(level="medium", score=56, eta_minutes=20)
        decision = should_send_alert(
            risk=risk,
            previous_state={"lastLevel": "low"},
            now_sg=datetime(2026, 2, 16, 14, 0, tzinfo=SG),
            quiet_start="23:00",
            quiet_end="07:00",
            cooldown_minutes=30,
        )
        self.assertTrue(decision.notify)

    def test_suppress_in_quiet_hours_for_non_high(self) -> None:
        risk = SimpleNamespace(level="medium", score=56, eta_minutes=20)
        decision = should_send_alert(
            risk=risk,
            previous_state={"lastLevel": "low"},
            now_sg=datetime(2026, 2, 16, 23, 30, tzinfo=SG),
            quiet_start="23:00",
            quiet_end="07:00",
            cooldown_minutes=30,
        )
        self.assertFalse(decision.notify)
        self.assertEqual("quiet_hours", decision.reason)

    def test_suppress_duplicate_in_cooldown(self) -> None:
        risk = SimpleNamespace(level="high", score=73, eta_minutes=10)
        decision = should_send_alert(
            risk=risk,
            previous_state={
                "lastLevel": "medium",
                "lastSignalHash": "high:7:1",
                "lastSentAt": "2026-02-16T13:45:00+08:00",
            },
            now_sg=datetime(2026, 2, 16, 14, 0, tzinfo=SG),
            quiet_start="23:00",
            quiet_end="07:00",
            cooldown_minutes=30,
        )
        self.assertFalse(decision.notify)
        self.assertEqual("duplicate_within_cooldown", decision.reason)


if __name__ == "__main__":
    unittest.main()
