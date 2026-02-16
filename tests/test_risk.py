from __future__ import annotations

import unittest

from weather_bot.risk import compute_risk_from_signals


class RiskModelTests(unittest.TestCase):
    def test_high_for_strong_local_rain(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[4.5, 4.0, 3.0, 2.0],
            ring_series=[3.4, 3.2, 2.8, 2.2],
            medium_threshold=45,
            high_threshold=70,
        )
        self.assertEqual("high", risk.level)
        self.assertEqual(0, risk.eta_minutes)

    def test_medium_for_approaching_cells(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[0.1, 0.0, 0.0, 0.0],
            ring_series=[4.5, 3.8, 3.0, 2.2],
            medium_threshold=45,
            high_threshold=70,
        )
        self.assertEqual("medium", risk.level)
        self.assertLessEqual(risk.eta_minutes, 20)

    def test_low_for_weak_signal(self) -> None:
        risk = compute_risk_from_signals(
            local_series=[0.0, 0.0, 0.0, 0.0],
            ring_series=[0.2, 0.1, 0.1, 0.0],
            medium_threshold=45,
            high_threshold=70,
        )
        self.assertEqual("low", risk.level)
        self.assertLess(risk.score, 45)


if __name__ == "__main__":
    unittest.main()
