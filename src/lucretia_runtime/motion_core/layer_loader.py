from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance

from .scene_models import SpriteSpec


def cover_resize(img: Image.Image, width: int, height: int) -> Image.Image:
    img = img.convert("RGB")
    src_w, src_h = img.size
    scale = max(width / max(1, src_w), height / max(1, src_h))
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = max(0, (new_w - width) // 2)
    top = max(0, (new_h - height) // 2)
    return img.crop((left, top, left + width, top + height))


def load_background(root: Path, path: str, width: int, height: int) -> Image.Image:
    image_path = root / path
    if not image_path.exists():
        raise RuntimeError(f"Missing background: {path}")
    img = Image.open(image_path)
    img = cover_resize(img, width, height)
    img = ImageEnhance.Contrast(img).enhance(1.04)
    img = ImageEnhance.Color(img).enhance(1.03)
    return img.convert("RGBA")


def load_sprite(root: Path, sprite: SpriteSpec) -> Image.Image:
    image_path = root / sprite.image_path
    if not image_path.exists():
        raise RuntimeError(f"Missing sprite {sprite.object_id}: {sprite.image_path}")
    img = Image.open(image_path).convert("RGBA")
    return img


def load_sprites(root: Path, sprites: tuple[SpriteSpec, ...]) -> dict[str, Image.Image]:
    return {sprite.object_id: load_sprite(root, sprite) for sprite in sprites}
