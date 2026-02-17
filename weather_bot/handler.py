from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from weather_bot.config import load_config
from weather_bot.policy import AlertDecision, should_send_alert
from weather_bot.radar import (
    decode_png,
    fetch_radar_frames,
    generate_radar_candidates,
    lat_lng_to_pixel,
)
from weather_bot.risk import RadarFramePayload, evaluate_risk_from_frames, filter_recent_frames
from weather_bot.state_store import StateStore
from weather_bot.telegram import send_telegram_message
from weather_bot.timeutil import to_singapore


@dataclass(frozen=True)
class UserContext:
    lat: float
    lng: float
    chat_id: str
    quiet_start: str
    quiet_end: str


@dataclass(frozen=True)
class FrameFetchResult:
    frames: tuple[RadarFramePayload, ...]
    inspected_candidates: int
    reason: str | None


def _format_alert_message(risk, timestamp_token: str) -> str:
    confidence_pct = round(risk.confidence * 100)
    if risk.eta_bucket == "unknown":
        eta_label = "unknown"
    elif risk.eta_minutes <= 0:
        eta_label = "now"
    else:
        eta_label = f"~{risk.eta_minutes} min"
    reasons = ", ".join(risk.reasons)
    return "\n".join(
        [
            f"Rain alert: {risk.level.upper()}",
            f"Likely rain {eta_label}.",
            f"Confidence: {confidence_pct}%",
            f"Radar slot: {timestamp_token}",
            f"Signals: {reasons}",
        ]
    )


def _resolve_now(event: dict | None) -> datetime:
    now = datetime.now(timezone.utc)
    if isinstance(event, dict) and event.get("now"):
        now = datetime.fromisoformat(event["now"].replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    return now


def load_user_context(config, store: StateStore) -> UserContext:
    profile = store.get_profile(config.user_id)
    if not profile:
        raise ValueError(f"Profile missing for {config.user_id}; seed PROFILE first")

    try:
        lat = float(profile["lat"])
        lng = float(profile["lng"])
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("Profile missing valid lat/lng") from error

    # Allow deployment-level override via env without requiring profile reseed.
    chat_id = config.telegram_chat_id or profile.get("chatId")
    if not chat_id:
        raise ValueError("Missing Telegram chat id")

    quiet_start = profile.get("quietStart") or config.quiet_start
    quiet_end = profile.get("quietEnd") or config.quiet_end
    return UserContext(
        lat=lat,
        lng=lng,
        chat_id=str(chat_id),
        quiet_start=quiet_start,
        quiet_end=quiet_end,
    )


def fetch_and_decode_recent_frames(config, now: datetime) -> FrameFetchResult:
    candidates = generate_radar_candidates(config, now)
    fetched = fetch_radar_frames(candidates)
    if not fetched:
        return FrameFetchResult(
            frames=tuple(),
            inspected_candidates=len(candidates),
            reason="no_radar_frames",
        )

    decoded = [
        RadarFramePayload(
            index=frame.index,
            timestamp_token=frame.timestamp_token,
            url=frame.url,
            content_hash=frame.content_hash,
            image=decode_png(frame.png_bytes),
        )
        for frame in fetched
    ]
    recent = filter_recent_frames(decoded, config.history_window_minutes)
    if not recent:
        return FrameFetchResult(
            frames=tuple(),
            inspected_candidates=len(candidates),
            reason="no_recent_radar_frames",
        )

    return FrameFetchResult(
        frames=tuple(recent),
        inspected_candidates=len(candidates),
        reason=None,
    )


def build_target_pixel(
    user: UserContext,
    frame: RadarFramePayload,
    config,
) -> tuple[float, float]:
    width, height = frame.image.width, frame.image.height
    return lat_lng_to_pixel(
        user.lat,
        user.lng,
        width,
        height,
        {
            "min_lat": config.radar_min_lat,
            "max_lat": config.radar_max_lat,
            "min_lng": config.radar_min_lng,
            "max_lng": config.radar_max_lng,
        },
    )


def persist_alert_state(
    store: StateStore,
    config,
    decision: AlertDecision,
    risk,
    now: datetime,
    newest_frame: RadarFramePayload,
) -> None:
    store.put_alert_state(
        config.user_id,
        {
            **decision.next_state,
            "updatedAt": now.isoformat(),
            "lastScore": risk.score,
            "lastEtaMinutes": risk.eta_minutes,
            "lastEtaBucket": risk.eta_bucket,
            "lastConfidence": risk.confidence,
            "lastRadarToken": newest_frame.timestamp_token,
            "lastEtaSlope": risk.debug.motion.slope_px_per_min,
            "lastEtaR2": risk.debug.motion.r2,
        },
    )


def build_handler_response(
    decision: AlertDecision,
    risk,
    newest_frame: RadarFramePayload,
) -> dict:
    return {
        "ok": True,
        "notify": decision.notify,
        "reason": decision.reason,
        "risk": {
            "level": risk.level,
            "score": risk.score,
            "eta_minutes": risk.eta_minutes,
            "eta_bucket": risk.eta_bucket,
            "rain_now": risk.rain_now,
            "confidence": risk.confidence,
            "reasons": list(risk.reasons),
            "debug": risk.debug_dict(),
        },
        "frame_timestamp": newest_frame.timestamp_token,
    }


def lambda_handler(event, _context):
    config = load_config()
    store = StateStore(config.table_name)
    user = load_user_context(config, store)

    now = _resolve_now(event)
    now_sg = to_singapore(now)

    frame_result = fetch_and_decode_recent_frames(config, now)
    if frame_result.reason == "no_radar_frames":
        return {
            "ok": True,
            "skipped": True,
            "reason": frame_result.reason,
            "inspected_candidates": frame_result.inspected_candidates,
        }
    if frame_result.reason is not None:
        return {
            "ok": True,
            "skipped": True,
            "reason": frame_result.reason,
        }

    newest_frame = frame_result.frames[0]
    target_pixel = build_target_pixel(user, newest_frame, config)
    risk = evaluate_risk_from_frames(frame_result.frames, target_pixel, config)
    previous_state = store.get_alert_state(config.user_id)
    decision = should_send_alert(
        risk=risk,
        previous_state=previous_state,
        now_sg=now_sg,
        quiet_start=user.quiet_start,
        quiet_end=user.quiet_end,
        cooldown_minutes=config.cooldown_minutes,
    )

    if decision.notify:
        send_telegram_message(
            bot_token=config.telegram_bot_token,
            chat_id=user.chat_id,
            text=_format_alert_message(risk, newest_frame.timestamp_token),
            disable_notification=False,
        )

    persist_alert_state(store, config, decision, risk, now, newest_frame)
    return build_handler_response(decision, risk, newest_frame)


def main() -> None:
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
