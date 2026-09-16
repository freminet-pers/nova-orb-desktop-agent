"""Frame-rate independent drag trajectory analysis.

The desktop surface can receive very different mouse event rates depending on
display scaling and pointer speed.  This tracker therefore works in seconds,
not event counts: velocity and acceleration are low-pass filtered, direction
reversal energy decays with elapsed time, and release feedback is derived from
the recent physical motion.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _smoothstep(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if value >= high else 0.0
    t = _clamp((value - low) / (high - low))
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True)
class DragSnapshot:
    """The physical state at one sampled point in a drag."""

    x: float
    y: float
    dt: float
    elapsed: float
    active_time: float
    vx: float
    vy: float
    speed: float
    acceleration: float
    intensity: float
    reversal_energy: float
    vertical_energy: float
    axis: str
    stage: str


@dataclass(frozen=True)
class DragRelease:
    """Release decision made from the last physical sample."""

    kind: str
    vertical_velocity: float
    horizontal_velocity: float
    strength: float
    snapshot: DragSnapshot


class DragMotionTracker:
    """Track a drag in logical screen pixels and seconds.

    ``stage`` is deliberately monotonic within a drag from the caller's point
    of view: a pause decays the measured snapshot, but it does not replay
    lower emotion stages.  A new drag starts from neutral and can climb again.
    """

    _VELOCITY_TAU = 0.085
    _ACCELERATION_TAU = 0.12
    _ENERGY_TAU = 1.15
    _PAUSE_SECONDS = 0.18

    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.started_at = 0.0
        self.last_at = 0.0
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.ax = 0.0
        self.ay = 0.0
        self.reversal_energy = 0.0
        self.vertical_energy = 0.0
        self.active_time = 0.0
        self.path_length = 0.0
        self.last_x_sign = 0
        self.last_y_sign = 0
        self.last_axis = "still"
        self._snapshot = DragSnapshot(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "still", "none")

    def begin(self, x: float, y: float, now: float):
        self.reset()
        self.active = True
        self.started_at = self.last_at = float(now)
        self.x = float(x)
        self.y = float(y)
        self._snapshot = DragSnapshot(self.x, self.y, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "still", "none")
        return self._snapshot

    def _stage(self, speed: float, speed_score: float, intensity: float, axis: str) -> str:
        if axis == "horizontal":
            if self.active_time >= 1.55 and self.reversal_energy >= 0.68 and intensity >= 0.52:
                return "drowsy"
            if self.active_time >= 0.78 and self.reversal_energy >= 0.40 and intensity >= 0.34:
                return "confused"
            if self.active_time >= 0.34 and self.reversal_energy >= 0.22 and intensity >= 0.25:
                return "suspicious"
            if speed_score >= 0.28 or intensity >= 0.14:
                return "surprised"
            if speed >= 75 or speed_score >= 0.05:
                return "curious"
            return "none"
        if speed_score >= 0.48 or intensity >= 0.38:
            return "surprised"
        if speed >= 75 or speed_score >= 0.05:
            return "curious"
        return "none"

    def _make_snapshot(self, dt: float, elapsed: float) -> DragSnapshot:
        speed = math.hypot(self.vx, self.vy)
        acceleration = math.hypot(self.ax, self.ay)
        horizontal = abs(self.vx)
        vertical = abs(self.vy)
        if max(horizontal, vertical) < 45:
            axis = self.last_axis if self.last_axis != "still" and speed > 12 else "still"
        elif horizontal > vertical * 1.18:
            axis = "horizontal"
        elif vertical > horizontal * 1.18:
            axis = "vertical"
        else:
            axis = "diagonal"
        if axis in {"horizontal", "vertical", "diagonal"}:
            self.last_axis = axis
        speed_score = _smoothstep(speed, 90.0, 900.0)
        acceleration_score = _smoothstep(acceleration, 600.0, 5200.0)
        oscillation_score = _clamp(self.reversal_energy)
        intensity = _clamp(0.56 * speed_score + 0.24 * acceleration_score + 0.20 * oscillation_score)
        stage = self._stage(speed, speed_score, intensity, axis)
        return DragSnapshot(
            self.x, self.y, dt, elapsed, self.active_time, self.vx, self.vy, speed,
            acceleration, intensity, self.reversal_energy, self.vertical_energy, axis, stage,
        )

    def update(self, x: float, y: float, now: float) -> DragSnapshot:
        if not self.active:
            return self.begin(x, y, now)
        now = float(now)
        gap = max(0.0, now - self.last_at)
        if gap <= 1e-6:
            return self._snapshot
        dt = min(gap, 0.25)
        dx = float(x) - self.x
        dy = float(y) - self.y
        distance = math.hypot(dx, dy)
        self.x = float(x)
        self.y = float(y)
        self.last_at = now
        # A timer sample after a pause is a zero-velocity sample.  This makes
        # a stationary held pointer lose release momentum naturally instead of
        # preserving the last mouse event's speed.
        if gap > self._PAUSE_SECONDS:
            raw_vx = raw_vy = 0.0
        else:
            raw_vx = dx / max(gap, 1e-4)
            raw_vy = dy / max(gap, 1e-4)
        velocity_alpha = 1.0 - math.exp(-dt / self._VELOCITY_TAU)
        previous_vx, previous_vy = self.vx, self.vy
        self.vx += (raw_vx - self.vx) * velocity_alpha
        self.vy += (raw_vy - self.vy) * velocity_alpha
        acceleration_alpha = 1.0 - math.exp(-dt / self._ACCELERATION_TAU)
        raw_ax = (self.vx - previous_vx) / max(dt, 1e-4)
        raw_ay = (self.vy - previous_vy) / max(dt, 1e-4)
        self.ax += (raw_ax - self.ax) * acceleration_alpha
        self.ay += (raw_ay - self.ay) * acceleration_alpha
        energy_decay = math.exp(-gap / self._ENERGY_TAU)
        self.reversal_energy *= energy_decay
        self.vertical_energy *= energy_decay
        speed = math.hypot(self.vx, self.vy)
        speed_score = _smoothstep(speed, 90.0, 900.0)
        if speed > 45:
            self.active_time += min(gap, 0.25) * _clamp(speed / 260.0, 0.0, 1.0)
        self.path_length += distance
        x_sign = 1 if self.vx > 70 else -1 if self.vx < -70 else 0
        y_sign = 1 if self.vy > 70 else -1 if self.vy < -70 else 0
        if x_sign and self.last_x_sign and x_sign != self.last_x_sign:
            self.reversal_energy = _clamp(self.reversal_energy + 0.18 + 0.72 * speed_score)
        if y_sign and self.last_y_sign and y_sign != self.last_y_sign:
            self.vertical_energy = _clamp(self.vertical_energy + 0.18 + 0.72 * speed_score)
        if x_sign:
            self.last_x_sign = x_sign
        elif gap > self._PAUSE_SECONDS:
            self.last_x_sign = 0
        if y_sign:
            self.last_y_sign = y_sign
        elif gap > self._PAUSE_SECONDS:
            self.last_y_sign = 0
        elapsed = max(0.0, now - self.started_at)
        self._snapshot = self._make_snapshot(dt, elapsed)
        return self._snapshot

    def finish(self, now: float | None = None) -> DragRelease:
        if not self.active:
            return DragRelease("none", 0.0, 0.0, 0.0, self._snapshot)
        if now is not None and now > self.last_at:
            self.update(self.x, self.y, now)
        snap = self._snapshot
        vertical_dominant = snap.axis == "vertical" and abs(snap.vy) >= abs(snap.vx) * 1.12
        horizontal_dominant = snap.axis == "horizontal" and abs(snap.vx) > abs(snap.vy) * 1.12
        if vertical_dominant and abs(snap.vy) >= 260 and snap.active_time >= 0.12:
            kind = "bounce"
            strength = _clamp((abs(snap.vy) - 260) / 700, 0.12, 1.0)
        elif horizontal_dominant and abs(snap.vx) >= 220 and snap.intensity >= 0.16:
            kind = "sway"
            strength = _clamp((abs(snap.vx) - 220) / 800, 0.08, 0.8)
        else:
            kind = "settle"
            strength = 0.0
        result = DragRelease(kind, snap.vy, snap.vx, strength, snap)
        self.reset()
        return result

    def cancel(self):
        self.reset()
