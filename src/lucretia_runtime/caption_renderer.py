from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _wrap_lines(text: str, max_chars: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:max_lines]


def draw_caption(img: Image.Image, text: str, safe_bottom: int = 110) -> None:
    draw = ImageDraw.Draw(img)
    font = _font(44)
    lines = _wrap_lines(text, max_chars=28, max_lines=3)
    y = img.height - safe_bottom - len(lines) * 56
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (img.width - w) // 2
        pad = 14
        draw.rounded_rectangle((x - pad, y - pad, x + w + pad, y + 52), radius=18, fill=(0, 0, 0, 175))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += 58


def draw_compact_caption(img: Image.Image, text: str) -> None:
    """Small caption layer for provider-backed assets.

    Provider assets often already include prompt or scene text. This compact layer
    keeps the final MP4 readable without covering the asset.
    """
    draw = ImageDraw.Draw(img, "RGBA")
    font_size = max(14, min(26, img.width // 18))
    font = _font(font_size)
    lines = _wrap_lines(text, max_chars=max(22, img.width // 14), max_lines=2)
    if not lines:
        return

    line_height = font_size + 8
    box_height = len(lines) * line_height + 18
    x0 = 18
    y0 = img.height - box_height - 24
    x1 = img.width - 18
    y1 = y0 + box_height
    draw.rounded_rectangle((x0, y0, x1, y1), radius=14, fill=(0, 0, 0, 95))

    y = y0 + 10
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (img.width - w) // 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 218))
        y += line_height
