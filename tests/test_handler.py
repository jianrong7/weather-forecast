from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from weather_bot.risk import MotionEstimate, RiskDebug, RiskResult


class HandlerTests(unittest.TestCase):
    @patch("weather_bot.handler.send_telegram_message")
    @patch("weather_bot.handler.should_send_alert")
    @patch("weather_bot.handler.evaluate_risk_from_frames")
    @patch("weather_bot.handler.filter_recent_frames")
    @patch("weather_bot.handler.lat_lng_to_pixel")
    @patch("weather_bot.handler.decode_png")
    @patch("weather_bot.handler.fetch_radar_frames")
    @patch("weather_bot.handler.generate_radar_candidates")
    @patch("weather_bot.handler.StateStore")
    @patch("weather_bot.handler.load_config")
    def test_lambda_returns_debug_fields_and_persists_eta_bucket(
        self,
        mock_load_config: MagicMock,
        mock_state_store: MagicMock,
        mock_generate_candidates: MagicMock,
        mock_fetch_frames: MagicMock,
        mock_decode_png: MagicMock,
        mock_lat_lng_to_pixel: MagicMock,
        mock_filter_recent_frames: MagicMock,
        mock_evaluate_risk: MagicMock,
        mock_should_send_alert: MagicMock,
        mock_send_telegram: MagicMock,
    ) -> None:
        config = SimpleNamespace(
            table_name="rain_alert_state",
            user_id="me",
            telegram_chat_id="123",
            quiet_start="23:00",
            quiet_end="07:00",
            cooldown_minutes=30,
            history_window_minutes=30,
            radar_min_lat=1.163,
            radar_max_lat=1.493,
            radar_min_lng=103.577,
            radar_max_lng=104.077,
            telegram_bot_token="token",
        )
        mock_load_config.return_value = config

        store = MagicMock()
        store.get_profile.return_value = {"lat": 1.3, "lng": 103.8, "chatId": "123"}
        store.get_alert_state.return_value = {"lastLevel": "low"}
        mock_state_store.return_value = store

        mock_generate_candidates.return_value = [SimpleNamespace()]
        mock_fetch_frames.return_value = [
            SimpleNamespace(
                index=0,
                timestamp_token="202602161500",
                url="https://example.com/radar.png",
                content_hash="abcd1234",
                png_bytes=b"\x89PNG\r\n\x1a\n",
            )
        ]

        mock_decode_png.return_value = SimpleNamespace(width=100, height=100)
        mock_filter_recent_frames.side_effect = lambda frames, _window: frames
        mock_lat_lng_to_pixel.return_value = (50.0, 50.0)
        mock_evaluate_risk.return_value = RiskResult(
            level="medium",
            score=61,
            eta_minutes=12,
            eta_bucket="15_6",
            rain_now=False,
            confidence=0.74,
            reasons=("eta_estimated", "approaching_fast"),
            debug=RiskDebug(
                now_local=0.1,
                rain_now=False,
                nearby_signal=True,
                distance_series_px=(24.0, 28.0, 31.0),
                minutes_series=(0.0, 5.0, 10.0),
                motion=MotionEstimate(
                    eta_minutes=12,
                    eta_bucket="15_6",
                    intercept_px=8.4,
                    slope_px_per_min=0.7,
                    r2=0.94,
                    confidence=0.74,
                    proximity=0.7,
                    valid_ratio=1.0,
                    valid_points=3,
                    valid_span_minutes=10.0,
                    valid_approach=True,
                ),
            ),
        )
        mock_should_send_alert.return_value = SimpleNamespace(
            notify=True,
            reason="upward_transition",
            next_state={
                "lastLevel": "medium",
                "lastEtaBucket": "15_6",
                "lastSignalHash": "medium:6:15_6",
                "lastSentAt": "2026-02-16T15:00:00+08:00",
            },
        )

        from weather_bot.handler import lambda_handler

        result = lambda_handler({}, None)

        self.assertTrue(result["ok"])
        self.assertTrue(result["notify"])
        self.assertEqual("15_6", result["risk"]["eta_bucket"])
        self.assertIn("eta_slope", result["risk"]["debug"])
        self.assertIn("eta_r2", result["risk"]["debug"])
        self.assertIn("distance_series_px", result["risk"]["debug"])
        self.assertIn("minutes_series", result["risk"]["debug"])

        persisted_state = store.put_alert_state.call_args[0][1]
        self.assertEqual("15_6", persisted_state["lastEtaBucket"])
        self.assertEqual(0.7, persisted_state["lastEtaSlope"])
        self.assertEqual(0.94, persisted_state["lastEtaR2"])
        mock_send_telegram.assert_called_once()


if __name__ == "__main__":
    unittest.main()
