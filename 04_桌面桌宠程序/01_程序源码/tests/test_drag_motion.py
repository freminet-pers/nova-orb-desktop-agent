import math
import unittest

from coco.drag_motion import DragMotionTracker


def feed(points, dt):
    tracker = DragMotionTracker()
    tracker.begin(*points[0], 0.0)
    snapshots = []
    for index, point in enumerate(points[1:], 1):
        snapshots.append(tracker.update(*point, index * dt))
    return tracker, snapshots


def horizontal_wave(amplitude=70, period=0.55, seconds=2.2, dt=0.02):
    points = []
    count = int(seconds / dt)
    for i in range(count + 1):
        t = i * dt
        points.append((110 + amplitude * math.sin(2 * math.pi * t / period), 110))
    return points


def vertical_wave(amplitude=70, period=0.8, seconds=1.2, dt=0.02):
    points = []
    count = int(seconds / dt)
    for i in range(count + 1):
        t = i * dt
        points.append((110, 110 + amplitude * math.sin(2 * math.pi * t / period)))
    return points


class DragMotionTests(unittest.TestCase):
    def test_slow_move_stays_light_and_does_not_bounce(self):
        points = [(20 + i * 2, 110) for i in range(51)]
        tracker, snapshots = feed(points, 0.04)
        self.assertLess(max(s.intensity for s in snapshots), 0.35)
        self.assertNotIn("confused", {s.stage for s in snapshots})
        release = tracker.finish(2.1)
        self.assertEqual(release.kind, "settle")

    def test_progressive_horizontal_stages_need_sustained_reversal(self):
        tracker, snapshots = feed(horizontal_wave(24, 1.3, 0.8), 0.02)
        self.assertIn("curious", {s.stage for s in snapshots})
        self.assertNotIn("drowsy", {s.stage for s in snapshots})
        tracker, snapshots = feed(horizontal_wave(55, 0.8, 1.15), 0.02)
        stages = {s.stage for s in snapshots}
        self.assertTrue(stages.intersection({"surprised", "suspicious", "confused"}), stages)
        self.assertNotIn("drowsy", stages)
        tracker, snapshots = feed(horizontal_wave(90, 0.42, 2.4), 0.02)
        stages = {s.stage for s in snapshots}
        self.assertIn("confused", stages)
        self.assertIn("drowsy", stages)

    def test_vertical_release_bounces_only_with_recent_vertical_speed(self):
        tracker, _ = feed(vertical_wave(72, 0.72, 0.9), 0.02)
        release = tracker.finish(0.91)
        self.assertEqual(release.kind, "bounce")
        self.assertGreater(abs(release.vertical_velocity), 260)
        tracker, _ = feed([(110, 110 + i * 2) for i in range(41)], 0.04)
        self.assertEqual(tracker.finish(2.0).kind, "settle")

    def test_pause_decays_release_momentum_and_feedback(self):
        tracker, snapshots = feed(horizontal_wave(90, 0.42, 1.8), 0.02)
        self.assertIn("confused", {s.stage for s in snapshots})
        before = tracker.update(110, 110, 1.84)
        after = tracker.update(110, 110, 2.5)
        self.assertLess(after.speed, before.speed)
        self.assertLess(after.reversal_energy, before.reversal_energy)
        self.assertEqual(tracker.finish(2.6).kind, "settle")

    def test_physical_path_is_close_at_different_sample_rates(self):
        fast, fast_samples = feed(horizontal_wave(70, 0.65, 1.8, 0.02), 0.02)
        slow, slow_samples = feed(horizontal_wave(70, 0.65, 1.8, 0.08), 0.08)
        self.assertAlmostEqual(max(s.intensity for s in fast_samples), max(s.intensity for s in slow_samples), delta=0.15)
        ranks = {"none": 0, "curious": 1, "surprised": 2, "suspicious": 3, "confused": 4, "drowsy": 5}
        self.assertLessEqual(abs(max(ranks[s.stage] for s in fast_samples) - max(ranks[s.stage] for s in slow_samples)), 1)
        self.assertEqual(fast.finish(1.81).kind, slow.finish(1.84).kind)

    def test_cancel_clears_motion_and_release(self):
        tracker, _ = feed(horizontal_wave(90, 0.4, 1.0), 0.02)
        tracker.cancel()
        self.assertFalse(tracker.active)
        self.assertEqual(tracker.finish(2.0).kind, "none")


if __name__ == "__main__":
    unittest.main()
