from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from weather_bot.radar import generate_radar_candidates


class RadarUrlTests(unittest.TestCase):
    def test_generate_candidates_uses_sg_slots(self) -> None:
        config = SimpleNamespace(
            frame_count=3,
            poll_interval_minutes=5,
            radar_base_url="https://example.com",
            radar_prefix="dpsri_70km_",
            radar_suffix="0000dBR.dpsri.png",
        )
        now_utc = datetime(2026, 2, 16, 7, 3, 31, tzinfo=timezone.utc)
        candidates = generate_radar_candidates(config, now_utc)

        self.assertEqual(3, len(candidates))
        self.assertEqual("202602161500", candidates[0].timestamp_token)
        self.assertEqual("202602161455", candidates[1].timestamp_token)
        self.assertEqual("202602161450", candidates[2].timestamp_token)
        self.assertTrue(candidates[0].url.endswith("dpsri_70km_2026021615000000dBR.dpsri.png"))


if __name__ == "__main__":
    unittest.main()
