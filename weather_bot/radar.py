from __future__ import annotations

import hashlib
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta

from weather_bot.timeutil import floor_minutes, timestamp_token, to_singapore


PALETTE = [
    (1, (102, 204, 255)),
    (2, (0, 176, 80)),
    (3, (255, 242, 0)),
    (4, (255, 153, 0)),
    (5, (255, 0, 0)),
]


@dataclass(frozen=True)
class RadarCandidate:
    index: int
    timestamp_token: str
    url: str


@dataclass(frozen=True)
class RadarFrame:
    index: int
    timestamp_token: str
    url: str
    png_bytes: bytes
    content_hash: str


@dataclass(frozen=True)
class RadarImage:
    width: int
    height: int
    rgba: bytes

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        idx = (y * self.width + x) * 4
        return (
            self.rgba[idx],
            self.rgba[idx + 1],
            self.rgba[idx + 2],
            self.rgba[idx + 3],
        )


def generate_radar_candidates(config, now: datetime | None = None) -> list[RadarCandidate]:
    now = now or datetime.utcnow()
    sg_now = to_singapore(now)
    rounded = floor_minutes(sg_now, config.poll_interval_minutes)

    candidates: list[RadarCandidate] = []
    for index in range(config.frame_count):
        frame_dt = rounded - timedelta(minutes=index * config.poll_interval_minutes)
        token = timestamp_token(frame_dt)
        filename = f"{config.radar_prefix}{token}{config.radar_suffix}"
        candidates.append(
            RadarCandidate(
                index=index,
                timestamp_token=token,
                url=f"{config.radar_base_url}/{filename}",
            )
        )
    return candidates


def fetch_radar_frames(candidates: list[RadarCandidate], timeout_seconds: float = 6.0) -> list[RadarFrame]:
    frames: list[RadarFrame] = []

    for candidate in candidates:
        request = urllib.request.Request(
            candidate.url,
            headers={"User-Agent": "rain-radar-telegram-bot/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    continue

                content_type = response.headers.get("Content-Type", "")
                if "png" not in content_type.lower():
                    continue

                payload = response.read()
                if not payload:
                    continue

                frames.append(
                    RadarFrame(
                        index=candidate.index,
                        timestamp_token=candidate.timestamp_token,
                        url=candidate.url,
                        png_bytes=payload,
                        content_hash=hashlib.sha1(payload).hexdigest()[:16],
                    )
                )
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue

    return frames


def decode_png(png_bytes: bytes) -> RadarImage:
    try:
        import png
    except ImportError as error:
        raise RuntimeError("pypng is required for radar PNG decoding") from error

    try:
        width, height, rows, _ = png.Reader(bytes=png_bytes).asRGBA8()
    except Exception as error:
        raise RuntimeError("Failed to decode radar PNG payload") from error

    rgba = b"".join(rows)
    return RadarImage(width=width, height=height, rgba=rgba)


def pixel_to_intensity(r: int, g: int, b: int, a: int) -> int:
    if a < 15:
        return 0

    brightness = (r + g + b) / 3
    if brightness < 12:
        return 0

    nearest_level = 0
    nearest_distance = float("inf")
    for level, (pr, pg, pb) in PALETTE:
        distance = math.sqrt((r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_level = level

    if nearest_distance > 170:
        return 0
    return nearest_level


def _clamp(value: int | float, low: int | float, high: int | float) -> int | float:
    return max(low, min(high, value))


def sample_average_intensity(image, x: float, y: float, radius: int) -> float:
    width, height = image.width, image.height
    total = 0.0
    count = 0

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            px = int(_clamp(round(x + dx), 0, width - 1))
            py = int(_clamp(round(y + dy), 0, height - 1))
            r, g, b, a = image.pixel(px, py)
            total += pixel_to_intensity(r, g, b, a)
            count += 1

    return (total / count) if count else 0.0


def lat_lng_to_pixel(lat: float, lng: float, image_width: int, image_height: int, bounds: dict[str, float]) -> tuple[float, float]:
    x_fraction = (lng - bounds["min_lng"]) / (bounds["max_lng"] - bounds["min_lng"])
    y_fraction = (bounds["max_lat"] - lat) / (bounds["max_lat"] - bounds["min_lat"])

    x = _clamp(x_fraction * (image_width - 1), 0, image_width - 1)
    y = _clamp(y_fraction * (image_height - 1), 0, image_height - 1)
    return float(x), float(y)
