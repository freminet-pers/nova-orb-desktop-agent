"""Time/distance based gestures, independent of pointer event frequency."""
from collections import deque


class HeadStrokes:
    def __init__(self):
        self.points = deque()
        self.last_reaction = -10.

    def move(self, x, y, width, height, now):
        if not (.24 * width < x < .76 * width and .18 * height < y < .49 * height):
            self.points.clear()
            return False
        self.points.append((now, x))
        while self.points and now - self.points[0][0] > 1.3:
            self.points.popleft()
        if len(self.points) < 4 or now - self.last_reaction < 2.4:
            return False
        deltas = [b[1] - a[1] for a, b in zip(self.points, list(self.points)[1:])]
        travel = sum(abs(d) for d in deltas)
        directions = [1 if d > 0 else -1 for d in deltas if abs(d) > 1.5]
        turns = sum(a != b for a, b in zip(directions, directions[1:]))
        if travel > width * .32 and turns >= 2:
            self.last_reaction = now
            self.points.clear()
            return True
        return False
