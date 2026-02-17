from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    table_name: str
    user_id: str
    timezone: str
    cooldown_minutes: int
    poll_interval_minutes: int
    quiet_start: str
    quiet_end: str
    sample_radius: int
    frame_count: int
    history_window_minutes: int
    motion_search_radius: int
    nearby_distance_px: int
    rain_now_intensity_threshold: float
    radar_base_url: str
    radar_prefix: str
    radar_suffix: str
    radar_min_lat: float
    radar_max_lat: float
    radar_min_lng: float
    radar_max_lng: float
    telegram_bot_token: str | None
    telegram_chat_id: str | None


def _get_number(
    name: str, default: float, cast_type: type[int] | type[float]
) -> int | float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return cast_type(default)
    try:
        return cast_type(raw)
    except ValueError as error:
        raise ValueError(f"Invalid value for {name}: {raw}") from error


def load_config(require_telegram_token: bool = True) -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if require_telegram_token and not token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable")

    config = Config(
        table_name=os.getenv("TABLE_NAME", "rain_alert_state"),
        user_id=os.getenv("USER_ID", "me"),
        timezone=os.getenv("TIMEZONE", "Asia/Singapore"),
        cooldown_minutes=int(_get_number("COOLDOWN_MINUTES", 30, int)),
        poll_interval_minutes=int(_get_number("POLL_INTERVAL_MINUTES", 5, int)),
        quiet_start=os.getenv("QUIET_START", "23:00"),
        quiet_end=os.getenv("QUIET_END", "07:00"),
        sample_radius=int(_get_number("SAMPLE_RADIUS", 4, int)),
        frame_count=int(_get_number("FRAME_COUNT", 7, int)),
        history_window_minutes=int(_get_number("HISTORY_WINDOW_MINUTES", 30, int)),
        motion_search_radius=int(_get_number("MOTION_SEARCH_RADIUS", 80, int)),
        nearby_distance_px=int(_get_number("NEARBY_DISTANCE_PX", 25, int)),
        rain_now_intensity_threshold=float(
            _get_number("RAIN_NOW_INTENSITY_THRESHOLD", 0.8, float)
        ),
        radar_base_url=os.getenv(
            "RADAR_BASE_URL", "https://www.weather.gov.sg/files/rainarea/50km/v2"
        ),
        radar_prefix=os.getenv("RADAR_PREFIX", "dpsri_70km_"),
        radar_suffix=os.getenv("RADAR_SUFFIX", "0000dBR.dpsri.png"),
        radar_min_lat=float(_get_number("RADAR_MIN_LAT", 1.163, float)),
        radar_max_lat=float(_get_number("RADAR_MAX_LAT", 1.493, float)),
        radar_min_lng=float(_get_number("RADAR_MIN_LNG", 103.577, float)),
        radar_max_lng=float(_get_number("RADAR_MAX_LNG", 104.077, float)),
        telegram_bot_token=token,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
    )

    if (
        config.radar_min_lat >= config.radar_max_lat
        or config.radar_min_lng >= config.radar_max_lng
    ):
        raise ValueError("Invalid radar bounds")

    if config.history_window_minutes <= 0:
        raise ValueError("HISTORY_WINDOW_MINUTES must be positive")
    if config.motion_search_radius <= 0:
        raise ValueError("MOTION_SEARCH_RADIUS must be positive")
    if config.nearby_distance_px <= 0:
        raise ValueError("NEARBY_DISTANCE_PX must be positive")
    if config.rain_now_intensity_threshold < 0:
        raise ValueError("RAIN_NOW_INTENSITY_THRESHOLD must be >= 0")

    return config
