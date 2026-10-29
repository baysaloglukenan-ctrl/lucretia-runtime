from __future__ import annotations

import math

from .scene_models import Keyframe
from .tween import lerp


def cubic_bezier(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float], t: float) -> tuple[float, float]:
    u = 1.0 - t
    x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
    return x, y


def line_keyframes(start: tuple[float, float], end: tuple[float, float], rotation: float = 0.0) -> tuple[Keyframe, ...]:
    return (
        Keyframe(t=0.0, x=start[0], y=start[1], rotation=0.0, scale=1.0),
        Keyframe(t=1.0, x=end[0], y=end[1], rotation=rotation, scale=1.0),
    )


def bezier_keyframes(
    start: tuple[float, float],
    end: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    samples: int = 7,
    rotation: float = 540.0,
    scale_start: float = 1.0,
    scale_end: float = 1.0,
) -> tuple[Keyframe, ...]:
    rows = []
    samples = max(2, int(samples))
    for idx in range(samples):
        t = idx / max(1, samples - 1)
        x, y = cubic_bezier(start, control_1, control_2, end, t)
        rows.append(Keyframe(t=t, x=x, y=y, rotation=lerp(0.0, rotation, t), scale=lerp(scale_start, scale_end, t)))
    return tuple(rows)


def magnet_pull_keyframes(
    start: tuple[float, float],
    target: tuple[float, float],
    arc_height: float = -170.0,
    rotation: float = 780.0,
) -> tuple[Keyframe, ...]:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    c1 = (start[0] + dx * 0.18, start[1] + dy * 0.12 + arc_height * 0.35)
    c2 = (start[0] + dx * 0.68, start[1] + dy * 0.72 + arc_height)
    sampled = list(bezier_keyframes(start, target, c1, c2, samples=8, rotation=rotation, scale_start=1.0, scale_end=1.04))
    # Pause + vibration start, then acceleration, then magnetic snap.
    sampled[0] = Keyframe(t=0.0, x=start[0], y=start[1], rotation=0.0, scale=1.0)
    sampled.insert(1, Keyframe(t=0.12, x=start[0] + 4, y=start[1] - 2, rotation=8.0, scale=1.0))
    sampled.insert(2, Keyframe(t=0.20, x=start[0] - 5, y=start[1] + 3, rotation=-7.0, scale=1.0))
    remapped = []
    for item in sampled:
        # Bias later samples toward the end so it feels like attraction/acceleration.
        t = item.t
        if t >= 0.24:
            t = 0.24 + (t ** 1.6) * 0.76
        remapped.append(Keyframe(t=min(1.0, t), x=item.x, y=item.y, rotation=item.rotation, scale=item.scale, opacity=item.opacity))
    remapped.append(Keyframe(t=0.94, x=target[0] - 18, y=target[1] + 8, rotation=rotation - 45, scale=1.08))
    remapped.append(Keyframe(t=1.0, x=target[0], y=target[1], rotation=rotation, scale=1.0))
    return tuple(sorted(remapped, key=lambda row: row.t))


def orbit_keyframes(center: tuple[float, float], radius: float = 160.0, samples: int = 12) -> tuple[Keyframe, ...]:
    rows = []
    for idx in range(max(3, samples)):
        t = idx / max(1, samples - 1)
        angle = t * math.tau
        rows.append(Keyframe(t=t, x=center[0] + math.cos(angle) * radius, y=center[1] + math.sin(angle) * radius, rotation=math.degrees(angle)))
    return tuple(rows)
