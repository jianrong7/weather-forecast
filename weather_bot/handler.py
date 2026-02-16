from __future__ import annotations

import json
from datetime import datetime, timezone

from weather_bot.config import load_config
from weather_bot.policy import should_send_alert
from weather_bot.radar import (
    decode_png,
    fetch_radar_frames,
    generate_radar_candidates,
    lat_lng_to_pixel,
)
from weather_bot.risk import evaluate_risk_from_frames
from weather_bot.state_store import StateStore
from weather_bot.telegram import send_telegram_message
from weather_bot.timeutil import is_within_quiet_hours, to_singapore


def _format_alert_message(risk, timestamp_token: str) -> str:
    confidence_pct = round(risk.confidence * 100)
    eta_label = "now" if risk.eta_minutes <= 0 else f"~{risk.eta_minutes} min"
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


def _require_profile_location(profile: dict, fallback_chat_id: str | None) -> dict:
    try:
        lat = float(profile["lat"])
        lng = float(profile["lng"])
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("Profile missing valid lat/lng") from error

    chat_id = profile.get("chatId") or fallback_chat_id
    if not chat_id:
        raise ValueError("Missing Telegram chat id")

    return {
        "lat": lat,
        "lng": lng,
        "chat_id": str(chat_id),
        "quiet_start": profile.get("quietStart"),
        "quiet_end": profile.get("quietEnd"),
    }


def lambda_handler(event, _context):
    config = load_config()
    store = StateStore(config.table_name)

    profile = store.get_profile(config.user_id)
    if not profile:
        raise ValueError(f"Profile missing for {config.user_id}; seed PROFILE first")

    user = _require_profile_location(profile, config.telegram_chat_id)

    now = datetime.now(timezone.utc)
    if isinstance(event, dict) and event.get("now"):
        now = datetime.fromisoformat(event["now"].replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

    now_sg = to_singapore(now)
    if is_within_quiet_hours(
        now_sg,
        user.get("quiet_start") or config.quiet_start,
        user.get("quiet_end") or config.quiet_end,
    ):
        return {
            "ok": True,
            "skipped": True,
            "reason": "quiet_hours",
        }

    candidates = generate_radar_candidates(config, now)
    fetched = fetch_radar_frames(candidates)
    if not fetched:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_radar_frames",
            "inspected_candidates": len(candidates),
        }

    frames = []
    for frame in fetched:
        frames.append(
            {
                "index": frame.index,
                "timestamp_token": frame.timestamp_token,
                "url": frame.url,
                "hash": frame.content_hash,
                "image": decode_png(frame.png_bytes),
            }
        )

    newest = frames[0]
    width, height = newest["image"].width, newest["image"].height
    target_x, target_y = lat_lng_to_pixel(
        user["lat"],
        user["lng"],
        width,
        height,
        {
            "min_lat": config.radar_min_lat,
            "max_lat": config.radar_max_lat,
            "min_lng": config.radar_min_lng,
            "max_lng": config.radar_max_lng,
        },
    )

    risk = evaluate_risk_from_frames(frames, (target_x, target_y), config)
    previous_state = store.get_alert_state(config.user_id)
    decision = should_send_alert(
        risk=risk,
        previous_state=previous_state,
        now_sg=now_sg,
        quiet_start=user.get("quiet_start") or config.quiet_start,
        quiet_end=user.get("quiet_end") or config.quiet_end,
        cooldown_minutes=config.cooldown_minutes,
    )

    if decision.notify:
        send_telegram_message(
            bot_token=config.telegram_bot_token,
            chat_id=user["chat_id"],
            text=_format_alert_message(risk, newest["timestamp_token"]),
            disable_notification=False,
        )

    store.put_alert_state(
        config.user_id,
        {
            **decision.next_state,
            "updatedAt": now.isoformat(),
            "lastScore": risk.score,
            "lastEtaMinutes": risk.eta_minutes,
            "lastConfidence": risk.confidence,
            "lastRadarToken": newest["timestamp_token"],
        },
    )

    return {
        "ok": True,
        "notify": decision.notify,
        "reason": decision.reason,
        "risk": {
            "level": risk.level,
            "score": risk.score,
            "eta_minutes": risk.eta_minutes,
            "confidence": risk.confidence,
            "reasons": list(risk.reasons),
        },
        "frame_timestamp": newest["timestamp_token"],
    }


def main() -> None:
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
