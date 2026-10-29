from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Keyframe:
    t: float
    x: float
    y: float
    rotation: float = 0.0
    scale: float = 1.0
    opacity: float = 1.0


@dataclass(frozen=True)
class AnimationSpec:
    object_id: str
    keyframes: tuple[Keyframe, ...]
    easing: str = "ease_in_out"
    motion_blur: bool = True
    shadow: bool = True


@dataclass(frozen=True)
class SpriteSpec:
    object_id: str
    image_path: str
    anchor_x: float = 0.5
    anchor_y: float = 0.5
    z_index: int = 10
    default_x: float = 0.0
    default_y: float = 0.0
    default_rotation: float = 0.0
    default_scale: float = 1.0
    default_opacity: float = 1.0


@dataclass(frozen=True)
class MotionSceneSpec:
    scene_id: str
    background_path: str
    sprites: tuple[SpriteSpec, ...]
    animations: tuple[AnimationSpec, ...]
    duration_seconds: float = 4.0
    fps: int = 24
    width: int = 720
    height: int = 1280
    caption: str = ""
    effects: dict = field(default_factory=dict)
