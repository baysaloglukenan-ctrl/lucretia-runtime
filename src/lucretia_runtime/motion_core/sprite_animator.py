from __future__ import annotations

from PIL import Image, ImageEnhance, ImageFilter

from .scene_models import AnimationSpec, Keyframe, SpriteSpec
from .tween import sample_keyframes


def _apply_opacity(img: Image.Image, opacity: float) -> Image.Image:
    opacity = max(0.0, min(1.0, float(opacity)))
    if opacity >= 0.995:
        return img
    out = img.copy()
    alpha = out.getchannel("A")
    alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
    out.putalpha(alpha)
    return out


def transform_sprite(sprite_img: Image.Image, sprite: SpriteSpec, frame: Keyframe) -> tuple[Image.Image, tuple[int, int]]:
    scale = max(0.02, frame.scale * sprite.default_scale)
    new_w = max(1, int(sprite_img.width * scale))
    new_h = max(1, int(sprite_img.height * scale))
    img = sprite_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    rotation = frame.rotation + sprite.default_rotation
    if abs(rotation) > 0.01:
        img = img.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
    img = _apply_opacity(img, frame.opacity * sprite.default_opacity)
    x = int(frame.x + sprite.default_x - img.width * sprite.anchor_x)
    y = int(frame.y + sprite.default_y - img.height * sprite.anchor_y)
    return img, (x, y)


def sample_sprite_state(sprite: SpriteSpec, animation: AnimationSpec | None, t: float) -> Keyframe:
    # Unanimated sprites are positioned by SpriteSpec.default_x/default_y in transform_sprite().
    # Returning those values here would double-apply the default position.
    if animation is None:
        return Keyframe(t=t, x=0.0, y=0.0, rotation=0.0, scale=1.0, opacity=1.0)
    return sample_keyframes(animation.keyframes, t, animation.easing)


def motion_blur_sprite(img: Image.Image, intensity: float = 1.0) -> Image.Image:
    radius = max(0.0, min(6.0, 2.5 * intensity))
    if radius <= 0.1:
        return img
    return img.filter(ImageFilter.GaussianBlur(radius=radius))
