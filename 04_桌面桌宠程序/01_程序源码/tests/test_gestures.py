import unittest
from coco.gestures import HeadStrokes


class StrokeTests(unittest.TestCase):
    def test_head_back_and_forth_triggers_once_then_cools_down(self):
        strokes = HeadStrokes()
        got = [strokes.move(x, 60, 220, 220, i * .15) for i, x in enumerate([70, 140, 70, 140])]
        self.assertEqual(got, [False, False, False, True])
        self.assertFalse(any(strokes.move(x, 60, 220, 220, 1 + i * .1)
                             for i, x in enumerate([70, 140, 70, 140])))

    def test_one_pass_stationary_or_below_head_does_not_pet(self):
        for xs, y in [([60, 70, 80, 90, 100, 110], 60), ([90] * 8, 60), ([70, 140, 70, 140], 160)]:
            strokes = HeadStrokes()
            self.assertFalse(any(strokes.move(x, y, 220, 220, i * .1) for i, x in enumerate(xs)))

    def test_old_movements_expire(self):
        strokes = HeadStrokes()
        self.assertFalse(any(strokes.move(x, 60, 220, 220, i * 2) for i, x in enumerate([70, 140, 70, 140])))


if __name__ == '__main__':
    unittest.main()
