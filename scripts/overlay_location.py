#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weather_bot.config import load_config
from weather_bot.radar import (
    decode_png,
    fetch_radar_frames,
    generate_radar_candidates,
    lat_lng_to_pixel,
)

DEFAULT_BACKGROUND_URL = "https://www.weather.gov.sg/wp-content/themes/wiptheme/assets/img/base-853.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Overlay a red dot on the latest radar image at a given lat/lng.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "radar-overlay.png"))
    parser.add_argument("--frame-count", type=int, default=None)
    parser.add_argument("--url", help="Optional direct radar PNG URL")
    parser.add_argument("--image-file", help="Optional local radar PNG file path")
    parser.add_argument("--background-url", default=DEFAULT_BACKGROUND_URL, help="Background PNG URL")
    parser.add_argument("--background-file", help="Optional local background PNG file path")
    parser.add_argument("--dot-radius", type=int, default=2, help="Red dot radius in output pixels")
    parser.add_argument("--dot-ring", type=int, default=1, help="White ring thickness in output pixels")
    return parser.parse_args()


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def draw_dot(rgba: bytearray, width: int, height: int, x: int, y: int, radius: int = 2, ring: int = 1) -> None:
    for dy in range(-(radius + ring), radius + ring + 1):
        for dx in range(-(radius + ring), radius + ring + 1):
            px = x + dx
            py = y + dy
            if px < 0 or py < 0 or px >= width or py >= height:
                continue

            distance_sq = dx * dx + dy * dy
            idx = (py * width + px) * 4

            if distance_sq <= radius * radius:
                rgba[idx : idx + 4] = bytes((255, 0, 0, 255))
            elif distance_sq <= (radius + ring) * (radius + ring):
                rgba[idx : idx + 4] = bytes((255, 255, 255, 255))


def write_png(path: Path, rgba: bytearray, width: int, height: int) -> None:
    try:
        import png
    except ImportError as error:
        raise RuntimeError("pypng is required to write overlay image") from error

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [list(rgba[row * width * 4 : (row + 1) * width * 4]) for row in range(height)]
    with path.open("wb") as handle:
        writer = png.Writer(width=width, height=height, alpha=True, greyscale=False)
        writer.write(handle, rows)


def _fetch_url_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "rain-radar-telegram-bot/0.1"})
    with urllib.request.urlopen(request, timeout=8.0) as response:
        return response.read()


def _resize_rgba(src_rgba: bytes | bytearray, src_w: int, src_h: int, dst_w: int, dst_h: int) -> bytearray:
    if src_w == dst_w and src_h == dst_h:
        return bytearray(src_rgba)

    try:
        from PIL import Image

        source = Image.frombytes("RGBA", (src_w, src_h), bytes(src_rgba))
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        resized = source.resize((dst_w, dst_h), resample=resampling)
        return bytearray(resized.tobytes())
    except Exception:
        pass

    out = bytearray(dst_w * dst_h * 4)
    for y in range(dst_h):
        src_y = min(src_h - 1, (y * src_h) // dst_h)
        for x in range(dst_w):
            src_x = min(src_w - 1, (x * src_w) // dst_w)
            src_idx = (src_y * src_w + src_x) * 4
            dst_idx = (y * dst_w + x) * 4
            out[dst_idx : dst_idx + 4] = src_rgba[src_idx : src_idx + 4]
    return out


def _alpha_composite(bg_rgba: bytes | bytearray, fg_rgba: bytes | bytearray, width: int, height: int) -> bytearray:
    out = bytearray(width * height * 4)
    for i in range(0, width * height * 4, 4):
        br, bg, bb, ba = bg_rgba[i], bg_rgba[i + 1], bg_rgba[i + 2], bg_rgba[i + 3]
        fr, fg, fb, fa = fg_rgba[i], fg_rgba[i + 1], fg_rgba[i + 2], fg_rgba[i + 3]

        ba_n = ba / 255.0
        fa_n = fa / 255.0
        out_a = fa_n + ba_n * (1.0 - fa_n)

        if out_a <= 0:
            out[i : i + 4] = b"\x00\x00\x00\x00"
            continue

        out_r = (fr * fa_n + br * ba_n * (1.0 - fa_n)) / out_a
        out_g = (fg * fa_n + bg * ba_n * (1.0 - fa_n)) / out_a
        out_b = (fb * fa_n + bb * ba_n * (1.0 - fa_n)) / out_a

        out[i] = int(round(out_r))
        out[i + 1] = int(round(out_g))
        out[i + 2] = int(round(out_b))
        out[i + 3] = int(round(out_a * 255.0))

    return out


def main() -> None:
    args = parse_args()
    if args.url and args.image_file:
        raise ValueError("Use only one of --url or --image-file.")

    base_config = load_config(require_telegram_token=False)
    frame_count = args.frame_count if args.frame_count is not None else base_config.frame_count
    config = argparse.Namespace(
        poll_interval_minutes=base_config.poll_interval_minutes,
        frame_count=frame_count,
        radar_base_url=base_config.radar_base_url,
        radar_prefix=base_config.radar_prefix,
        radar_suffix=base_config.radar_suffix,
    )
    bounds = {
        "min_lat": base_config.radar_min_lat,
        "max_lat": base_config.radar_max_lat,
        "min_lng": base_config.radar_min_lng,
        "max_lng": base_config.radar_max_lng,
    }

    frame_label = ""
    frame_url = ""

    if args.image_file:
        image_path = Path(args.image_file).expanduser().resolve()
        payload = image_path.read_bytes()
        frame_label = image_path.name
        frame_url = str(image_path)
    elif args.url:
        try:
            payload = _fetch_url_bytes(args.url)
        except urllib.error.URLError as error:
            raise RuntimeError(f"Failed to fetch --url frame: {error}") from error
        frame_label = "manual_url"
        frame_url = args.url
    else:
        candidates = generate_radar_candidates(config)
        frames = fetch_radar_frames(candidates)
        if not frames:
            raise RuntimeError("No radar frames fetched. Check network access or try again later.")
        latest = frames[0]
        payload = latest.png_bytes
        frame_label = latest.timestamp_token
        frame_url = latest.url

    image = decode_png(payload)
    x, y = lat_lng_to_pixel(args.lat, args.lng, image.width, image.height, bounds)
    radar_rgba = bytearray(image.rgba)

    if args.background_file:
        bg_path = Path(args.background_file).expanduser().resolve()
        bg_payload = bg_path.read_bytes()
        background_source = str(bg_path)
    else:
        try:
            bg_payload = _fetch_url_bytes(args.background_url)
        except urllib.error.URLError as error:
            raise RuntimeError(f"Failed to fetch background image: {error}") from error
        background_source = args.background_url

    bg_image = decode_png(bg_payload)
    out_width = bg_image.width
    out_height = bg_image.height
    bg_rgba = bytearray(bg_image.rgba)
    radar_rgba = _resize_rgba(
        src_rgba=radar_rgba,
        src_w=image.width,
        src_h=image.height,
        dst_w=out_width,
        dst_h=out_height,
    )
    composite = _alpha_composite(bg_rgba, radar_rgba, out_width, out_height)

    x_out = x * (out_width - 1) / max(1, image.width - 1)
    y_out = y * (out_height - 1) / max(1, image.height - 1)
    x_out_int = _clamp(round(x_out), 0, out_width - 1)
    y_out_int = _clamp(round(y_out), 0, out_height - 1)
    draw_dot(
        composite,
        out_width,
        out_height,
        x_out_int,
        y_out_int,
        radius=max(1, args.dot_radius),
        ring=max(0, args.dot_ring),
    )

    output = Path(args.output).resolve()
    write_png(output, composite, out_width, out_height)

    print(f"saved={output}")
    print(f"frame={frame_label}")
    print(f"url={frame_url}")
    print(f"background={background_source}")
    print(f"output_size={out_width}x{out_height}")
    print(f"radar_pixel_x={x:.2f}")
    print(f"radar_pixel_y={y:.2f}")
    print(f"output_pixel_x={x_out:.2f}")
    print(f"output_pixel_y={y_out:.2f}")


if __name__ == "__main__":
    main()
