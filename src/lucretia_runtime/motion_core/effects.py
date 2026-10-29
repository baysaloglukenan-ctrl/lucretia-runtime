from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter


def draw_shadow(canvas: Image.Image, sprite_img: Image.Image, pos: tuple[int, int], offset: tuple[int, int] = (16, 24), opacity: int = 90) -> None:
    alpha = sprite_img.getchannel("A")
    shadow = Image.new("RGBA", sprite_img.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda value: int(value * opacity / 255)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    canvas.alpha_composite(shadow, (pos[0] + offset[0], pos[1] + offset[1]))


def draw_magnet_pulse(draw: ImageDraw.ImageDraw, center: tuple[float, float], progress: float, strength: float = 1.0) -> None:
    cx, cy = int(center[0]), int(center[1])
    for idx in range(4):
        phase = (progress * 1.8 + idx * 0.22) % 1.0
        radius = int(34 + phase * 210 * strength)
        alpha = int(135 * (1.0 - phase))
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(105, 205, 255, alpha), width=4)


def draw_metal_particles(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], progress: float, count: int = 30) -> None:
    rng = random.Random(1209)
    sx, sy = start
    ex, ey = end
    for idx in range(count):
        phase = (progress * (0.55 + idx * 0.013) + idx / count) % 1.0
        pull = min(1.0, max(0.0, (phase - 0.18) / 0.82))
        wobble = math.sin(progress * math.tau * 2.0 + idx) * 18
        x = sx * (1 - pull) + ex * pull + rng.uniform(-90, 90) * (1 - pull) + wobble
        y = sy * (1 - pull) + ey * pull + rng.uniform(-70, 70) * (1 - pull) + math.cos(idx) * 12
        alpha = int(50 + 145 * pull)
        draw.rounded_rectangle([x - 10, y - 3, x + 10, y + 3], radius=3, fill=(225, 235, 245, alpha))


def draw_impact_flash(draw: ImageDraw.ImageDraw, center: tuple[float, float], progress: float) -> None:
    if progress < 0.86:
        return
    local = min(1.0, (progress - 0.86) / 0.14)
    alpha = int(180 * (1.0 - local))
    radius = int(40 + local * 180)
    cx, cy = int(center[0]), int(center[1])
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(255, 248, 180, alpha), width=7)
    draw.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=(255, 245, 180, max(0, alpha // 2)))


def draw_caption(canvas: Image.Image, text: str) -> None:
    if not text:
        return
    draw = ImageDraw.Draw(canvas, "RGBA")
    w, h = canvas.size
    draw.rounded_rectangle([42, h - 172, w - 42, h - 54], radius=26, fill=(0, 0, 0, 138), outline=(255, 255, 255, 54), width=2)
    # Use default if project font missing; text is secondary for demo.
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=34)
    except Exception:
        from PIL import ImageFont
        font = ImageFont.load_default()
    safe = " ".join(text.strip().split())[:110]
    bbox = draw.textbbox((0, 0), safe, font=font)
    x = (w - (bbox[2] - bbox[0])) // 2
    y = h - 132
    for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
        draw.text((x + ox, y + oy), safe, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), safe, font=font, fill=(255, 255, 255, 255))
