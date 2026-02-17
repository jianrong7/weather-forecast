from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from weather_bot.radar import pixel_to_intensity, sample_average_intensity
from weather_bot.timeutil import SG_TZ

MIN_POINTS_FOR_REGRESSION = 3
MIN_SPAN_MINUTES_FOR_REGRESSION = 10.0
MIN_APPROACH_SLOPE_PX_PER_MINUTE = 0.25
RAIN_NOW_DISTANCE_PX = 3.0
HEAVY_RAIN_INTENSITY = 2.5


@dataclass(frozen=True)
class RadarFramePayload:
    index: int
    timestamp_token: str
    url: str
    content_hash: str
    image: Any


@dataclass(frozen=True)
class MotionEstimate:
    eta_minutes: int | None
    eta_bucket: str
    intercept_px: float | None
    slope_px_per_min: float | None
    r2: float | None
    confidence: float
    proximity: float
    valid_ratio: float
    valid_points: int
    valid_span_minutes: float
    valid_approach: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "eta_intercept": self.intercept_px,
            "eta_slope": self.slope_px_per_min,
            "eta_r2": self.r2,
            "eta_bucket": self.eta_bucket,
            "valid_ratio": self.valid_ratio,
            "valid_points": self.valid_points,
            "valid_span_minutes": self.valid_span_minutes,
            "proximity": self.proximity,
            "confidence": self.confidence,
            "valid_approach": self.valid_approach,
        }


@dataclass(frozen=True)
class RiskDebug:
    now_local: float
    rain_now: bool
    nearby_signal: bool
    distance_series_px: tuple[float | None, ...]
    minutes_series: tuple[float, ...]
    motion: MotionEstimate

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "now_local": self.now_local,
            "rain_now": self.rain_now,
            "nearby_signal": self.nearby_signal,
            "distance_series_px": list(self.distance_series_px),
            "minutes_series": list(self.minutes_series),
        }
        payload.update(self.motion.to_dict())
        return payload


@dataclass(frozen=True)
class RiskResult:
    level: str
    score: int
    eta_minutes: int
    eta_bucket: str
    rain_now: bool
    confidence: float
    reasons: tuple[str, ...]
    debug: RiskDebug

    def debug_dict(self) -> dict[str, Any]:
        return self.debug.to_dict()


@dataclass(frozen=True)
class _MotionInputs:
    now_local: float
    now_distance: float
    rain_now: bool
    heavy_now: bool
    nearby_signal: bool
    valid_points: tuple[tuple[float, float], ...]
    valid_span_minutes: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _bucket_eta(eta_minutes: int | None) -> str:
    if eta_minutes is None:
        return "unknown"
    if eta_minutes <= 0:
        return "now"
    if eta_minutes <= 5:
        return "5_1"
    if eta_minutes <= 15:
        return "15_6"
    if eta_minutes <= 30:
        return "30_16"
    return "30_plus"


def _parse_token(token: str) -> datetime | None:
    try:
        parsed = datetime.strptime(token, "%Y%m%d%H%M")
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=SG_TZ)


def _empty_motion_estimate() -> MotionEstimate:
    return MotionEstimate(
        eta_minutes=None,
        eta_bucket="unknown",
        intercept_px=None,
        slope_px_per_min=None,
        r2=None,
        confidence=0.0,
        proximity=0.0,
        valid_ratio=0.0,
        valid_points=0,
        valid_span_minutes=0.0,
        valid_approach=False,
    )


def _no_signal_result() -> RiskResult:
    return RiskResult(
        level="low",
        score=0,
        eta_minutes=30,
        eta_bucket="unknown",
        rain_now=False,
        confidence=0.0,
        reasons=("no_signal",),
        debug=RiskDebug(
            now_local=0.0,
            rain_now=False,
            nearby_signal=False,
            distance_series_px=tuple(),
            minutes_series=tuple(),
            motion=_empty_motion_estimate(),
        ),
    )


def filter_recent_frames(
    frames: Sequence[RadarFramePayload], history_window_minutes: int
) -> list[RadarFramePayload]:
    stamped: list[tuple[datetime, RadarFramePayload]] = []
    for frame in frames:
        frame_dt = _parse_token(frame.timestamp_token)
        if frame_dt is None:
            continue
        stamped.append((frame_dt, frame))

    if not stamped:
        return list(frames)

    newest = max(stamped, key=lambda item: item[0])[0]
    lower_bound_minutes = max(0, history_window_minutes)
    recent = [
        (frame_dt, frame)
        for frame_dt, frame in stamped
        if 0.0 <= (newest - frame_dt).total_seconds() / 60.0 <= lower_bound_minutes
    ]
    recent.sort(key=lambda item: item[0], reverse=True)
    return [frame for _, frame in recent]


def _nearest_rain_distance(image, x: float, y: float, search_radius: int) -> float:
    width, height = image.width, image.height
    target_x = int(_clamp(round(x), 0, width - 1))
    target_y = int(_clamp(round(y), 0, height - 1))

    min_sq = float("inf")
    search_sq = search_radius * search_radius

    for dy in range(-search_radius, search_radius + 1):
        py = target_y + dy
        if py < 0 or py >= height:
            continue
        for dx in range(-search_radius, search_radius + 1):
            dist_sq = dx * dx + dy * dy
            if dist_sq > search_sq:
                continue
            px = target_x + dx
            if px < 0 or px >= width:
                continue
            r, g, b, a = image.pixel(px, py)
            if pixel_to_intensity(r, g, b, a) >= 1 and dist_sq < min_sq:
                min_sq = dist_sq
                if dist_sq == 0:
                    return 0.0

    if math.isinf(min_sq):
        return float("inf")
    return math.sqrt(min_sq)


def _linear_fit(points: Iterable[tuple[float, float]]) -> tuple[float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for x, y in points:
        xs.append(float(x))
        ys.append(float(y))

    count = len(xs)
    if count < 2:
        return None

    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    ssxx = sum((x - mean_x) ** 2 for x in xs)
    if ssxx <= 0:
        return None

    ssxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = ssxy / ssxx
    intercept = mean_y - slope * mean_x

    sst = sum((y - mean_y) ** 2 for y in ys)
    if sst <= 0:
        r2 = 1.0
    else:
        sse = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
        r2 = _clamp(1.0 - (sse / sst), 0.0, 1.0)

    return intercept, slope, r2


def _build_motion_inputs(
    local_series: Sequence[float],
    distance_series_px: Sequence[float],
    minutes_series: Sequence[float],
    nearby_distance_px: int,
    rain_now_intensity_threshold: float,
) -> _MotionInputs:
    now_local = local_series[0]
    now_distance = distance_series_px[0]
    rain_now = now_local >= rain_now_intensity_threshold or now_distance <= RAIN_NOW_DISTANCE_PX
    heavy_now = now_local >= HEAVY_RAIN_INTENSITY
    nearby_signal = now_distance <= nearby_distance_px

    valid_points = tuple(
        (minutes, distance)
        for minutes, distance in zip(minutes_series, distance_series_px)
        if math.isfinite(distance)
    )
    valid_span_minutes = 0.0
    if valid_points:
        valid_span_minutes = (
            max(point[0] for point in valid_points)
            - min(point[0] for point in valid_points)
        )

    return _MotionInputs(
        now_local=now_local,
        now_distance=now_distance,
        rain_now=rain_now,
        heavy_now=heavy_now,
        nearby_signal=nearby_signal,
        valid_points=valid_points,
        valid_span_minutes=valid_span_minutes,
    )


def _estimate_motion(
    *,
    inputs: _MotionInputs,
    total_points: int,
    motion_search_radius: int,
) -> MotionEstimate:
    eta_intercept = None
    eta_slope = None
    eta_r2 = None
    regression = None

    if (
        len(inputs.valid_points) >= MIN_POINTS_FOR_REGRESSION
        and inputs.valid_span_minutes >= MIN_SPAN_MINUTES_FOR_REGRESSION
    ):
        regression = _linear_fit(inputs.valid_points)
    if regression is not None:
        eta_intercept, eta_slope, eta_r2 = regression

    valid_approach = (
        eta_slope is not None and eta_slope >= MIN_APPROACH_SLOPE_PX_PER_MINUTE
    )
    eta_minutes: int | None = None
    if inputs.rain_now:
        eta_minutes = 0
    elif valid_approach and eta_intercept is not None:
        eta_minutes = int(round(_clamp(eta_intercept / eta_slope, 1.0, 60.0)))

    if eta_intercept is not None and math.isfinite(eta_intercept):
        distance_for_proximity = eta_intercept
    elif math.isfinite(inputs.now_distance):
        distance_for_proximity = inputs.now_distance
    else:
        distance_for_proximity = float(motion_search_radius)

    proximity = 1.0 - min(distance_for_proximity, float(motion_search_radius)) / max(
        1.0, float(motion_search_radius)
    )
    valid_ratio = len(inputs.valid_points) / max(1, total_points)
    confidence = _clamp(
        0.25
        + 0.35 * (eta_r2 if eta_r2 is not None else 0.0)
        + 0.2 * valid_ratio
        + 0.2 * proximity,
        0.0,
        1.0,
    )
    return MotionEstimate(
        eta_minutes=eta_minutes,
        eta_bucket=_bucket_eta(eta_minutes),
        intercept_px=eta_intercept,
        slope_px_per_min=eta_slope,
        r2=eta_r2,
        confidence=confidence,
        proximity=proximity,
        valid_ratio=valid_ratio,
        valid_points=len(inputs.valid_points),
        valid_span_minutes=inputs.valid_span_minutes,
        valid_approach=valid_approach,
    )


def _classify_risk(
    *,
    heavy_now: bool,
    rain_now: bool,
    nearby_signal: bool,
    motion: MotionEstimate,
) -> tuple[str, int, str]:
    if heavy_now:
        return "high", 0, "now"
    if rain_now:
        return "medium", 0, "now"
    if motion.eta_minutes is not None and motion.eta_minutes <= 10 and motion.confidence >= 0.45:
        return "high", motion.eta_minutes, motion.eta_bucket
    if motion.eta_minutes is not None and motion.eta_minutes <= 30 and motion.confidence >= 0.35:
        return "medium", motion.eta_minutes, motion.eta_bucket
    if motion.eta_minutes is None and nearby_signal:
        return "medium", 30, "unknown"
    return "low", 30, _bucket_eta(motion.eta_minutes)


def _score_risk(
    *,
    level: str,
    now_local: float,
    eta_minutes: int | None,
    confidence: float,
) -> int:
    eta_bonus = 0
    if eta_minutes is not None:
        if eta_minutes <= 10:
            eta_bonus = 10
        elif eta_minutes <= 20:
            eta_bonus = 5

    base_score = {"low": 20, "medium": 55, "high": 75}[level]
    return int(
        _clamp(
            round(
                base_score
                + min(now_local, 5.0) * 4.0
                + eta_bonus
                + round(confidence * 10.0)
            ),
            0.0,
            100.0,
        )
    )


def _collect_reasons(
    *,
    rain_now: bool,
    heavy_now: bool,
    nearby_signal: bool,
    motion: MotionEstimate,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if rain_now:
        reasons.append("rain_now")
    if heavy_now:
        reasons.append("heavy_rain_now")
    if motion.eta_minutes is not None and not rain_now:
        reasons.append("eta_estimated")
    if motion.valid_approach:
        reasons.append("approaching_fast")
    if nearby_signal:
        reasons.append("nearby_cells")
    if motion.eta_minutes is None and nearby_signal:
        reasons.append("eta_unknown_conservative")
    if not reasons:
        reasons.append("weak_signal")
    return tuple(reasons)


def _build_risk_debug(
    *,
    now_local: float,
    rain_now: bool,
    nearby_signal: bool,
    distance_series_px: Sequence[float],
    minutes_series: Sequence[float],
    motion: MotionEstimate,
) -> RiskDebug:
    distance_series = tuple(
        None if not math.isfinite(value) else round(float(value), 3)
        for value in distance_series_px
    )
    minute_series = tuple(round(float(value), 3) for value in minutes_series)
    return RiskDebug(
        now_local=now_local,
        rain_now=rain_now,
        nearby_signal=nearby_signal,
        distance_series_px=distance_series,
        minutes_series=minute_series,
        motion=motion,
    )


def compute_risk_from_signals(
    local_series: list[float],
    distance_series_px: list[float],
    minutes_series: list[float],
    motion_search_radius: int,
    nearby_distance_px: int,
    rain_now_intensity_threshold: float,
) -> RiskResult:
    if not local_series or not distance_series_px:
        return _no_signal_result()

    inputs = _build_motion_inputs(
        local_series=local_series,
        distance_series_px=distance_series_px,
        minutes_series=minutes_series,
        nearby_distance_px=nearby_distance_px,
        rain_now_intensity_threshold=rain_now_intensity_threshold,
    )
    motion = _estimate_motion(
        inputs=inputs,
        total_points=len(distance_series_px),
        motion_search_radius=motion_search_radius,
    )
    level, eta_minutes, eta_bucket = _classify_risk(
        heavy_now=inputs.heavy_now,
        rain_now=inputs.rain_now,
        nearby_signal=inputs.nearby_signal,
        motion=motion,
    )
    score = _score_risk(
        level=level,
        now_local=inputs.now_local,
        eta_minutes=motion.eta_minutes,
        confidence=motion.confidence,
    )
    reasons = _collect_reasons(
        rain_now=inputs.rain_now,
        heavy_now=inputs.heavy_now,
        nearby_signal=inputs.nearby_signal,
        motion=motion,
    )
    debug = _build_risk_debug(
        now_local=inputs.now_local,
        rain_now=inputs.rain_now,
        nearby_signal=inputs.nearby_signal,
        distance_series_px=distance_series_px,
        minutes_series=minutes_series,
        motion=motion,
    )
    return RiskResult(
        level=level,
        score=score,
        eta_minutes=eta_minutes,
        eta_bucket=eta_bucket,
        rain_now=inputs.rain_now,
        confidence=motion.confidence,
        reasons=reasons,
        debug=debug,
    )


def evaluate_risk_from_frames(
    frames: Sequence[RadarFramePayload],
    target_pixel: tuple[float, float],
    config,
) -> RiskResult:
    if not frames:
        return _no_signal_result()

    x, y = target_pixel
    local_series: list[float] = []
    distance_series_px: list[float] = []
    minutes_series: list[float] = []

    newest_dt = _parse_token(frames[0].timestamp_token)
    for index, frame in enumerate(frames):
        image = frame.image
        local_series.append(sample_average_intensity(image, x, y, config.sample_radius))
        distance_series_px.append(
            _nearest_rain_distance(image, x, y, config.motion_search_radius)
        )

        frame_dt = _parse_token(frame.timestamp_token)
        if newest_dt is not None and frame_dt is not None:
            minutes_from_now = max(0.0, (newest_dt - frame_dt).total_seconds() / 60.0)
        else:
            minutes_from_now = float(index * config.poll_interval_minutes)
        minutes_series.append(minutes_from_now)

    return compute_risk_from_signals(
        local_series=local_series,
        distance_series_px=distance_series_px,
        minutes_series=minutes_series,
        motion_search_radius=config.motion_search_radius,
        nearby_distance_px=config.nearby_distance_px,
        rain_now_intensity_threshold=config.rain_now_intensity_threshold,
    )
