from __future__ import annotations

import json
import urllib.error
import urllib.request


def send_telegram_message(bot_token: str, chat_id: str, text: str, disable_notification: bool = False) -> None:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": disable_notification,
        }
    ).encode("utf-8")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as error:
        raise RuntimeError(f"Telegram request failed: {error}") from error

    parsed = json.loads(body)
    if not parsed.get("ok", False):
        raise RuntimeError(f"Telegram send failed: {parsed}")
