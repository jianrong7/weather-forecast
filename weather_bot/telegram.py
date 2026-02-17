from __future__ import annotations

import json
from http.client import HTTPResponse
from typing import Any, TypedDict
import urllib.error
import urllib.request


class TelegramResponse(TypedDict, total=False):
    ok: bool
    description: str
    result: dict[str, Any]


def _parse_telegram_error_body(raw_body: bytes | str | None) -> str:
    if raw_body is None:
        return "no response body"
    if isinstance(raw_body, bytes):
        decoded = raw_body.decode("utf-8", errors="replace")
    else:
        decoded = raw_body

    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return decoded.strip() or "empty response body"

    description = payload.get("description")
    if isinstance(description, str) and description.strip():
        return description
    return decoded.strip() or "empty response body"


def _decode_response_body(response: HTTPResponse) -> TelegramResponse:
    body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected Telegram response payload: {parsed!r}")
    return parsed


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
            parsed = _decode_response_body(response)
    except urllib.error.HTTPError as error:
        detail = _parse_telegram_error_body(error.read())
        raise RuntimeError(
            f"Telegram request failed: HTTP {error.code} {error.reason}; {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Telegram request failed: {error}") from error

    if not parsed.get("ok", False):
        raise RuntimeError(f"Telegram send failed: {parsed}")
