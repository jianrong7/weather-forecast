from __future__ import annotations

import unittest

from weather_bot.risk import RadarFramePayload, compute_risk_from_signals, filter_recent_frames


class RiskModelTests(unittest.TestCase):
    def test_medium_when_light_rain_is_now(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[1.0, 0.7, 0.3],
            distance_series_px=[2.0, 4.0, 8.0],
            minutes_series=[0.0, 5.0, 10.0],
            motion_search_radius=80,
            nearby_distance_px=25,
            rain_now_intensity_threshold=0.8,
        )
        self.assertEqual("medium", risk.level)
        self.assertEqual(0, risk.eta_minutes)
        self.assertEqual("now", risk.eta_bucket)
        self.assertTrue(risk.rain_now)
        self.assertIn("rain_now", risk.reasons)

    def test_high_for_strong_local_rain(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[3.2, 2.5, 2.0],
            distance_series_px=[0.0, 1.0, 2.0],
            minutes_series=[0.0, 5.0, 10.0],
            motion_search_radius=80,
            nearby_distance_px=25,
            rain_now_intensity_threshold=0.8,
        )
        self.assertEqual("high", risk.level)
        self.assertEqual(0, risk.eta_minutes)
        self.assertEqual("now", risk.eta_bucket)
        self.assertIn("heavy_rain_now", risk.reasons)

    def test_high_for_fast_approaching_cells_with_good_confidence(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[0.1, 0.1, 0.1, 0.0],
            distance_series_px=[4.0, 10.0, 16.0, 22.0],
            minutes_series=[0.0, 5.0, 10.0, 15.0],
            motion_search_radius=80,
            nearby_distance_px=25,
            rain_now_intensity_threshold=0.8,
        )
        self.assertEqual("high", risk.level)
        self.assertEqual("5_1", risk.eta_bucket)
        self.assertLessEqual(risk.eta_minutes, 10)
        self.assertIn("eta_estimated", risk.reasons)
        self.assertIn("approaching_fast", risk.reasons)

    def test_medium_when_eta_unknown_but_cells_are_nearby(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[0.2, 0.2, 0.2],
            distance_series_px=[15.0, 12.0, 10.0],
            minutes_series=[0.0, 5.0, 10.0],
            motion_search_radius=80,
            nearby_distance_px=25,
            rain_now_intensity_threshold=0.8,
        )
        self.assertEqual("medium", risk.level)
        self.assertEqual("unknown", risk.eta_bucket)
        self.assertIn("eta_unknown_conservative", risk.reasons)

    def test_low_for_weak_signal_far_from_location(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[0.0, 0.0, 0.0],
            distance_series_px=[60.0, 55.0, 50.0],
            minutes_series=[0.0, 5.0, 10.0],
            motion_search_radius=80,
            nearby_distance_px=25,
            rain_now_intensity_threshold=0.8,
        )
        self.assertEqual("low", risk.level)
        self.assertEqual("unknown", risk.eta_bucket)
        self.assertIn("weak_signal", risk.reasons)

    def test_filter_recent_frames_uses_30_minute_window(self) -> None:
        frames = [
            RadarFramePayload(index=0, timestamp_token="202602161500", url="", content_hash="", image=None),
            RadarFramePayload(index=1, timestamp_token="202602161455", url="", content_hash="", image=None),
            RadarFramePayload(index=2, timestamp_token="202602161430", url="", content_hash="", image=None),
            RadarFramePayload(index=3, timestamp_token="202602161425", url="", content_hash="", image=None),
        ]
        recent = filter_recent_frames(frames, 30)
        self.assertEqual(
            ["202602161500", "202602161455", "202602161430"],
            [item.timestamp_token for item in recent],
        )

    def test_risk_debug_dict_keeps_expected_keys(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[0.1, 0.1, 0.1, 0.0],
            distance_series_px=[4.0, 10.0, 16.0, 22.0],
            minutes_series=[0.0, 5.0, 10.0, 15.0],
            motion_search_radius=80,
            nearby_distance_px=25,
            rain_now_intensity_threshold=0.8,
        )
        debug = risk.debug_dict()
        self.assertIn("distance_series_px", debug)
        self.assertIn("minutes_series", debug)
        self.assertIn("eta_slope", debug)
        self.assertIn("eta_r2", debug)
        self.assertIn("eta_bucket", debug)
        self.assertEqual(risk.eta_bucket, debug["eta_bucket"])


if __name__ == "__main__":
    unittest.main()
