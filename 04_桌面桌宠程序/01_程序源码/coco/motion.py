"""Frame-rate-independent entrance choreography, reusable by future handoff UI."""
import math


def entrance_pose(t):
    """Normalized [0,1] time -> progress, jump height, body scale and tilt.

    0-.15 anticipation outside edge; .15-.72 arc; .72-1 damped landing.
    Values and first landing position are continuous across phase boundaries.
    """
    t = max(0., min(1., t))
    if t < .15:
        s = math.sin(math.pi * t / .15)
        return 0., 0., 1 + .07 * s, 1 - .07 * s, 0.
    if t < .72:
        u = (t - .15) / .57
        progress = u * u * (3 - 2 * u)
        arc = math.sin(math.pi * u)
        return progress, -115 * arc, 1 - .035 * arc, 1 + .045 * arc, -9 * math.sin(2 * math.pi * u)
    u = (t - .72) / .28
    settle = math.sin(3 * math.pi * u) * (1 - u) ** 2
    return 1., 0., 1 + .13 * settle, 1 - .13 * settle, 2 * settle
