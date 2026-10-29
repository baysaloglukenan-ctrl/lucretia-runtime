from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .provider_models import ProviderAssetRequest


def _font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _color(seed: str) -> tuple[int, int, int]:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return (
        35 + int(digest[0:2], 16) % 120,
        45 + int(digest[2:4], 16) % 120,
        80 + int(digest[4:6], 16) % 130,
    )


def _draw_centered(draw: ImageDraw.ImageDraw, img: Image.Image, text: str, y: int, size: int, fill=(255, 255, 255, 245)) -> None:
    font = _font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (img.width - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


def build_mock_provider_asset(request: ProviderAssetRequest, output_dir: Path, job_id: str) -> Path:
    """Create a deterministic local image asset for a provider request.

    This does not pretend to be Runway. It is a safe adapter substitute that proves
    the future provider contract: request in, asset out, manifest around it.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    seed = request.seed or f"{request.assembly_plan_id}:{request.segment_id}:{request.scene_id}"
    bg = _color(seed)
    img = Image.new("RGB", (request.width, request.height), bg)
    draw = ImageDraw.Draw(img, "RGBA")

    # soft frame + motion marks
    margin = max(28, request.width // 18)
    draw.rounded_rectangle(
        (margin, margin, request.width - margin, request.height - margin),
        radius=max(22, request.width // 22),
        outline=(255, 255, 255, 70),
        width=3,
    )
    for idx in range(7):
        x = int(request.width * (0.13 + idx * 0.12))
        y = int(request.height * (0.30 + (idx % 3) * 0.08))
        draw.ellipse((x - 26, y - 26, x + 26, y + 26), fill=(255, 255, 255, 32 + idx * 10))

    _draw_centered(draw, img, "LUCREȚIA MOCK PROVIDER", int(request.height * 0.12), max(28, request.width // 15))
    _draw_centered(draw, img, request.provider.upper(), int(request.height * 0.20), max(20, request.width // 24), fill=(255, 220, 140, 245))
    _draw_centered(draw, img, request.episode_id, int(request.height * 0.30), max(20, request.width // 25))
    _draw_centered(draw, img, request.segment_id, int(request.height * 0.36), max(22, request.width // 22))
    _draw_centered(draw, img, request.scene_id[-34:], int(request.height * 0.44), max(18, request.width // 28))

    prompt = request.prompt.strip() or request.scene_id
    words = prompt.split()
    lines: list[str] = []
    line = ""
    for word in words[:34]:
        candidate = f"{line} {word}".strip()
        if len(candidate) > 34:
            if line:
                lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    for idx, line in enumerate(lines[:4]):
        _draw_centered(draw, img, line, int(request.height * 0.58) + idx * max(28, request.height // 34), max(18, request.width // 32), fill=(235, 245, 255, 235))

    _draw_centered(draw, img, f"duration target: {request.duration_seconds:.2f}s", int(request.height * 0.86), max(16, request.width // 36), fill=(210, 225, 245, 220))

    out_path = output_dir / f"{job_id}_{request.segment_id}.png"
    img.save(out_path)
    return out_path
