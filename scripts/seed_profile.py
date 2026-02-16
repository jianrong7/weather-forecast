#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python scripts/seed_profile.py` from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weather_bot.config import load_config
from weather_bot.state_store import StateStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed PROFILE item for rain alert bot")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--chat-id", required=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(require_telegram_token=False)
    region = os.getenv("AWS_REGION")

    store = StateStore(config.table_name, region=region)

    chat_id = args.chat_id or config.telegram_chat_id
    if not chat_id:
        raise ValueError("Provide --chat-id or TELEGRAM_CHAT_ID")

    store.put_profile(
        config.user_id,
        {
            "lat": args.lat,
            "lng": args.lng,
            "chatId": str(chat_id),
            "alertStyle": "balanced",
            "quietStart": config.quiet_start,
            "quietEnd": config.quiet_end,
            "enabled": True,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"Seeded PROFILE for USER#{config.user_id} lat={args.lat} lng={args.lng} chatId={chat_id}")


if __name__ == "__main__":
    main()
