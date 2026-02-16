from __future__ import annotations

from datetime import datetime, timedelta, timezone

SG_TZ = timezone(timedelta(hours=8))


def to_singapore(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SG_TZ)


def floor_minutes(dt: datetime, step_minutes: int) -> datetime:
    minute = (dt.minute // step_minutes) * step_minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


def timestamp_token(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def minutes_between(older_iso: str | None, newer: datetime) -> float:
    if not older_iso:
        return float("inf")
    try:
        older = datetime.fromisoformat(older_iso.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    if older.tzinfo is None:
        older = older.replace(tzinfo=timezone.utc)
    return (newer - older).total_seconds() / 60.0


def _parse_hhmm(value: str) -> tuple[int, int]:
    pieces = value.split(":")
    if len(pieces) != 2:
        raise ValueError(f"Invalid HH:MM value: {value}")
    hours, minutes = int(pieces[0]), int(pieces[1])
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError(f"Invalid HH:MM value: {value}")
    return hours, minutes


def is_within_quiet_hours(now_sg: datetime, quiet_start: str, quiet_end: str) -> bool:
    start_h, start_m = _parse_hhmm(quiet_start)
    end_h, end_m = _parse_hhmm(quiet_end)
    now_minutes = now_sg.hour * 60 + now_sg.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes
    return now_minutes >= start_minutes or now_minutes < end_minutes
