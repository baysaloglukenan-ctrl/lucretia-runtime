from __future__ import annotations

import math

from .scene_models import Keyframe


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease(name: str, t: float) -> float:
    t = clamp01(t)
    if name == "linear":
        return t
    if name == "ease_in":
        return t * t
    if name == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if name == "snap":
        return t * t * t
    if name == "overshoot":
        c1 = 1.70158
        c3 = c1 + 1.0
        return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2
    return t * t * (3.0 - 2.0 * t)


def sample_keyframes(keyframes: tuple[Keyframe, ...], t: float, easing: str = "ease_in_out") -> Keyframe:
    if not keyframes:
        return Keyframe(t=t, x=0.0, y=0.0)
    keys = tuple(sorted(keyframes, key=lambda item: item.t))
    if t <= keys[0].t:
        first = keys[0]
        return Keyframe(t=t, x=first.x, y=first.y, rotation=first.rotation, scale=first.scale, opacity=first.opacity)
    if t >= keys[-1].t:
        last = keys[-1]
        return Keyframe(t=t, x=last.x, y=last.y, rotation=last.rotation, scale=last.scale, opacity=last.opacity)
    for idx in range(len(keys) - 1):
        a = keys[idx]
        b = keys[idx + 1]
        if a.t <= t <= b.t:
            local = (t - a.t) / max(1e-6, b.t - a.t)
            e = ease(easing, local)
            return Keyframe(
                t=t,
                x=lerp(a.x, b.x, e),
                y=lerp(a.y, b.y, e),
                rotation=lerp(a.rotation, b.rotation, e),
                scale=lerp(a.scale, b.scale, e),
                opacity=lerp(a.opacity, b.opacity, e),
            )
    return keys[-1]


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
