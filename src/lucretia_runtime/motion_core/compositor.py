from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw

from .effects import draw_caption, draw_impact_flash, draw_magnet_pulse, draw_metal_particles, draw_shadow
from .layer_loader import load_background, load_sprites
from .scene_models import AnimationSpec, MotionSceneSpec, SpriteSpec
from .sprite_animator import motion_blur_sprite, sample_sprite_state, transform_sprite


def _animations_by_object(scene: MotionSceneSpec) -> dict[str, AnimationSpec]:
    return {animation.object_id: animation for animation in scene.animations}


def _compose_frame(root: Path, scene: MotionSceneSpec, sprite_images: dict[str, Image.Image], background: Image.Image, frame_idx: int, total_frames: int) -> Image.Image:
    progress = frame_idx / max(1, total_frames - 1)
    canvas = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")
    animations = _animations_by_object(scene)
    target = scene.effects.get("target", (scene.width * 0.65, scene.height * 0.42))
    start = scene.effects.get("start", (scene.width * 0.25, scene.height * 0.72))

    if scene.effects.get("magnet_pulse", False):
        draw_magnet_pulse(draw, target, progress, strength=float(scene.effects.get("magnet_strength", 1.0)))
    if scene.effects.get("metal_particles", False):
        draw_metal_particles(draw, start, target, progress, count=int(scene.effects.get("particle_count", 30)))

    for sprite in sorted(scene.sprites, key=lambda item: item.z_index):
        sprite_img = sprite_images[sprite.object_id]
        animation = animations.get(sprite.object_id)
        state = sample_sprite_state(sprite, animation, progress)
        transformed, pos = transform_sprite(sprite_img, sprite, state)
        if animation and animation.shadow:
            draw_shadow(canvas, transformed, pos)
        if animation and animation.motion_blur and 0.10 < progress < 0.92:
            blur_intensity = min(1.0, max(0.0, progress * 1.35))
            ghost = motion_blur_sprite(transformed, blur_intensity)
            canvas.alpha_composite(ghost, (pos[0] - 5, pos[1] + 3))
        canvas.alpha_composite(transformed, pos)

    if scene.effects.get("impact_flash", False):
        draw_impact_flash(draw, target, progress)
    draw_caption(canvas, scene.caption)
    return canvas.convert("RGB")


def render_scene(root: Path, scene: MotionSceneSpec, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    background = load_background(root, scene.background_path, scene.width, scene.height)
    sprite_images = load_sprites(root, scene.sprites)
    duration = max(0.25, float(scene.duration_seconds))
    fps = max(1, int(scene.fps))
    total_frames = max(1, int(round(duration * fps)))
    with imageio.get_writer(str(output_path), fps=fps, codec="libx264", quality=8, macro_block_size=None) as writer:
        for frame_idx in range(total_frames):
            frame = _compose_frame(root, scene, sprite_images, background, frame_idx, total_frames)
            writer.append_data(np.asarray(frame))
    return output_path
