from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from weather_bot.timeutil import is_within_quiet_hours, minutes_between

LEVEL_WEIGHT = {"none": 0, "low": 1, "medium": 2, "high": 3}
ETA_BUCKET_WEIGHT = {
    "unknown": 99,
    "30_plus": 50,
    "30_16": 40,
    "15_6": 30,
    "5_1": 20,
    "now": 10,
}


class PolicyRisk(Protocol):
    level: str
    score: int
    eta_bucket: str


@dataclass(frozen=True)
class AlertDecision:
    notify: bool
    reason: str
    signal_hash: str
    next_state: dict


def _signal_hash(level: str, score: int, eta_bucket: str) -> str:
    return f"{level}:{score // 10}:{eta_bucket}"


def _is_tighter_eta(previous_bucket: str, next_bucket: str) -> bool:
    previous_weight = ETA_BUCKET_WEIGHT.get(previous_bucket, ETA_BUCKET_WEIGHT["unknown"])
    next_weight = ETA_BUCKET_WEIGHT.get(next_bucket, ETA_BUCKET_WEIGHT["unknown"])
    return next_weight < previous_weight


def _is_upward_transition(previous_level: str, next_level: str) -> bool:
    return LEVEL_WEIGHT.get(next_level, 0) > LEVEL_WEIGHT.get(previous_level, 0)


def _is_eta_tightening_transition(
    *,
    previous_level: str,
    previous_eta_bucket: str,
    next_level: str,
    next_eta_bucket: str,
) -> bool:
    if LEVEL_WEIGHT.get(next_level, 0) < LEVEL_WEIGHT["medium"]:
        return False
    if LEVEL_WEIGHT.get(next_level, 0) != LEVEL_WEIGHT.get(previous_level, 0):
        return False
    return _is_tighter_eta(previous_eta_bucket, next_eta_bucket)


def _is_duplicate_within_cooldown(
    *,
    previous_state: dict,
    signal_hash: str,
    now_sg: datetime,
    cooldown_minutes: int,
) -> bool:
    if previous_state.get("lastSignalHash") != signal_hash:
        return False
    since_minutes = minutes_between(previous_state.get("lastSentAt"), now_sg)
    return since_minutes < cooldown_minutes


def _build_next_state(
    *,
    level: str,
    eta_bucket: str,
    signal_hash: str,
    sent_at_iso: str | None = None,
) -> dict:
    state = {
        "lastLevel": level,
        "lastEtaBucket": eta_bucket,
        "lastSignalHash": signal_hash,
    }
    if sent_at_iso is not None:
        state["lastSentAt"] = sent_at_iso
    return state


def should_send_alert(
    risk: PolicyRisk,
    previous_state: dict | None,
    now_sg: datetime,
    quiet_start: str,
    quiet_end: str,
    cooldown_minutes: int,
) -> AlertDecision:
    previous_state = previous_state or {}
    previous_level = previous_state.get("lastLevel", "none")
    previous_eta_bucket = previous_state.get("lastEtaBucket", "unknown")
    next_level = risk.level
    next_eta_bucket = risk.eta_bucket
    signal_hash = _signal_hash(next_level, risk.score, next_eta_bucket)

    if LEVEL_WEIGHT.get(next_level, 0) < LEVEL_WEIGHT["medium"]:
        return AlertDecision(
            False,
            "below_notification_level",
            signal_hash,
            _build_next_state(
                level=next_level,
                eta_bucket=next_eta_bucket,
                signal_hash=signal_hash,
            ),
        )

    if is_within_quiet_hours(now_sg, quiet_start, quiet_end) and next_level != "high":
        return AlertDecision(
            False,
            "quiet_hours",
            signal_hash,
            _build_next_state(
                level=next_level,
                eta_bucket=next_eta_bucket,
                signal_hash=signal_hash,
            ),
        )

    is_upward = _is_upward_transition(previous_level, next_level)
    is_eta_tightening = _is_eta_tightening_transition(
        previous_level=previous_level,
        previous_eta_bucket=previous_eta_bucket,
        next_level=next_level,
        next_eta_bucket=next_eta_bucket,
    )
    if not is_upward and not is_eta_tightening:
        return AlertDecision(
            False,
            "not_upward_or_eta_tightening",
            signal_hash,
            _build_next_state(
                level=next_level,
                eta_bucket=next_eta_bucket,
                signal_hash=signal_hash,
            ),
        )

    if _is_duplicate_within_cooldown(
        previous_state=previous_state,
        signal_hash=signal_hash,
        now_sg=now_sg,
        cooldown_minutes=cooldown_minutes,
    ):
        return AlertDecision(
            False,
            "duplicate_within_cooldown",
            signal_hash,
            _build_next_state(
                level=next_level,
                eta_bucket=next_eta_bucket,
                signal_hash=signal_hash,
            ),
        )

    reason = "upward_transition" if is_upward else "eta_tightening"
    return AlertDecision(
        True,
        reason,
        signal_hash,
        _build_next_state(
            level=next_level,
            eta_bucket=next_eta_bucket,
            signal_hash=signal_hash,
            sent_at_iso=now_sg.isoformat(),
        ),
    )
