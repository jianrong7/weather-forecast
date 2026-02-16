from __future__ import annotations

from dataclasses import dataclass

from weather_bot.radar import sample_annulus_intensity, sample_average_intensity


@dataclass(frozen=True)
class RiskResult:
    level: str
    score: int
    eta_minutes: int
    confidence: float
    reasons: tuple[str, ...]
    debug: dict[str, float]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_intensity(value: float) -> float:
    return _clamp(value / 5.0, 0.0, 1.0)


def compute_risk_from_signals(
    local_series: list[float],
    ring_series: list[float],
    medium_threshold: int,
    high_threshold: int,
) -> RiskResult:
    if not local_series or not ring_series:
        return RiskResult("low", 0, 30, 0.0, ("no_signal",), {})

    now_local = local_series[0]
    oldest_local = local_series[-1]
    now_ring = ring_series[0]
    oldest_ring = ring_series[-1]

    local_trend = _clamp((now_local - oldest_local) / 3.0, -1.0, 1.0)
    ring_trend = _clamp((now_ring - oldest_ring) / 3.0, -1.0, 1.0)
    approaching = _clamp(_normalize_intensity(now_ring) * 0.7 + max(ring_trend, 0.0) * 0.3, 0.0, 1.0)
    pre_arrival_boost = _clamp(_normalize_intensity(now_ring) * (1 - _normalize_intensity(now_local)), 0.0, 1.0)
    persistence = sum(1 for value in local_series if value >= 0.8) / len(local_series)

    score = round(
        _normalize_intensity(now_local) * 45
        + max(local_trend, 0.0) * 20
        + approaching * 25
        + pre_arrival_boost * 30
        + persistence * 10
    )

    if score >= high_threshold:
        level = "high"
    elif score >= medium_threshold:
        level = "medium"
    else:
        level = "low"

    if now_local >= 1.2:
        eta_minutes = 0
    elif approaching > 0.7:
        eta_minutes = 10
    elif approaching > 0.45 or local_trend > 0.2:
        eta_minutes = 20
    else:
        eta_minutes = 30

    confidence = _clamp(0.4 + _normalize_intensity(now_local) * 0.2 + approaching * 0.2 + persistence * 0.2, 0.0, 1.0)

    reasons: list[str] = []
    if now_local >= 1.2:
        reasons.append("rain_now")
    if local_trend > 0.2:
        reasons.append("local_intensity_rising")
    if approaching > 0.55:
        reasons.append("rain_cells_nearby")
    if pre_arrival_boost > 0.6:
        reasons.append("rain_cells_moving_in")
    if not reasons:
        reasons.append("weak_signal")

    return RiskResult(
        level=level,
        score=score,
        eta_minutes=eta_minutes,
        confidence=confidence,
        reasons=tuple(reasons),
        debug={
            "now_local": now_local,
            "now_ring": now_ring,
            "local_trend": local_trend,
            "ring_trend": ring_trend,
            "approaching": approaching,
            "pre_arrival_boost": pre_arrival_boost,
            "persistence": persistence,
        },
    )


def evaluate_risk_from_frames(frames: list[dict], target_pixel: tuple[float, float], config) -> RiskResult:
    x, y = target_pixel
    local_series: list[float] = []
    ring_series: list[float] = []

    for frame in frames:
        image = frame["image"]
        local_series.append(sample_average_intensity(image, x, y, config.sample_radius))
        ring_series.append(sample_annulus_intensity(image, x, y, config.ring_inner_radius, config.ring_outer_radius))

    return compute_risk_from_signals(local_series, ring_series, config.medium_threshold, config.high_threshold)
