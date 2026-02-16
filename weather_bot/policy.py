from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from weather_bot.timeutil import is_within_quiet_hours, minutes_between

LEVEL_WEIGHT = {"none": 0, "low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class AlertDecision:
    notify: bool
    reason: str
    signal_hash: str
    next_state: dict


def _signal_hash(level: str, score: int, eta_minutes: int) -> str:
    return f"{level}:{score // 10}:{eta_minutes // 10}"


def should_send_alert(
    risk,
    previous_state: dict | None,
    now_sg: datetime,
    quiet_start: str,
    quiet_end: str,
    cooldown_minutes: int,
) -> AlertDecision:
    previous_state = previous_state or {}
    prev_level = previous_state.get("lastLevel", "none")
    next_level = risk.level
    signal_hash = _signal_hash(next_level, risk.score, risk.eta_minutes)

    if LEVEL_WEIGHT.get(next_level, 0) < LEVEL_WEIGHT["medium"]:
        return AlertDecision(False, "below_notification_level", signal_hash, {"lastLevel": next_level, "lastSignalHash": signal_hash})

    if is_within_quiet_hours(now_sg, quiet_start, quiet_end) and next_level != "high":
        return AlertDecision(False, "quiet_hours", signal_hash, {"lastLevel": next_level, "lastSignalHash": signal_hash})

    if LEVEL_WEIGHT.get(next_level, 0) <= LEVEL_WEIGHT.get(prev_level, 0):
        return AlertDecision(False, "not_upward_transition", signal_hash, {"lastLevel": next_level, "lastSignalHash": signal_hash})

    if previous_state.get("lastSignalHash") == signal_hash:
        since_minutes = minutes_between(previous_state.get("lastSentAt"), now_sg)
        if since_minutes < cooldown_minutes:
            return AlertDecision(False, "duplicate_within_cooldown", signal_hash, {"lastLevel": next_level, "lastSignalHash": signal_hash})

    return AlertDecision(
        True,
        "upward_transition",
        signal_hash,
        {
            "lastLevel": next_level,
            "lastSignalHash": signal_hash,
            "lastSentAt": now_sg.isoformat(),
        },
    )
