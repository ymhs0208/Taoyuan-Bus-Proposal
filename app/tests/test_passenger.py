"""Population transitions and time/resource edge cases. Run with unittest."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.passenger import allocation, best_access, population_changes, recommend


class PassengerTests(unittest.TestCase):
    def test_gross_gains_and_losses_do_not_disappear_in_net(self):
        def ev(any_mask, target):
            return {"coverage": {"mask_conn": np.array(any_mask, bool), "conn": 30.0,
                                  "per_station": {"G12": {"mask": np.array(target, bool)}}}}
        before = ev([0, 1, 1, 1], [0, 0, 1, 0])
        after = ev([1, 1, 1, 0], [1, 1, 1, 0])
        result = population_changes(before, after, "G12", np.array([10., 20., 5., 10.]))
        self.assertEqual(result["first"], 10)
        self.assertEqual(result["choice"], 20)
        self.assertEqual(result["target_gain"], 30)
        self.assertEqual(result["new_any"], 10)
        self.assertEqual(result["lost_any"], 10)
        self.assertEqual(result["net_any"], 0)

    def test_resource_caps_never_round_up_to_an_unfunded_trip(self):
        self.assertEqual(allocation(35, "相同工時上限", 30, 1), (1, 35/60))
        self.assertEqual(allocation(65, "相同工時上限", 30, 1), (0, 0))
        self.assertEqual(allocation(35, "相同班次", 30, 1), (30, 17.5))

    def test_a_slow_feeder_cannot_force_walking_passengers_to_lose_time(self):
        r = best_access(np.array([600.]), np.array([0.]), (0, 0),
                        [(600, 0, 30, 10, 20, True)], 3, 300, 8)
        self.assertAlmostEqual(r["total"][0], 16)
        self.assertFalse(r["feeder"][0])

    def test_transfer_walk_and_train_wait_are_counted_once(self):
        r = best_access(np.array([1000.]), np.array([0.]), (0, 0),
                        [(900, 0, 2, 1, 50, True)], 3, 300, 8)
        self.assertTrue(r["feeder"][0])
        self.assertAlmostEqual(r["walk"][0], 2)
        self.assertAlmostEqual(r["interchange_walk"][0], 1)
        self.assertAlmostEqual(r["total"][0], 10)
        self.assertAlmostEqual(sum(r[k][0] for k in ["walk", "interchange_walk", "wait", "ride", "transfer"]), r["total"][0])

    def test_no_time_benefit_means_no_time_winner(self):
        rows = [dict(station=c, first=100, first_per_hour=10, choice_per_hour=20, time_per_hour=0) for c in ["G12", "G14"]]
        self.assertIsNone(recommend(rows, "改善到站時間優先"))


if __name__ == "__main__":
    unittest.main()
