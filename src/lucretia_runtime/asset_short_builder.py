from __future__ import annotations

import json
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .provider_models import utc_now_iso

MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "hold", "slide_up", "parallax_soft"]
VALID_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class AssetSceneSpec:
    asset_path: str
    caption: str = ""
    motion: str = "zoom_in"


@dataclass(frozen=True)
class AssetShortSpec:
    title: str = "Lucretia Short"
    hook_text: str = ""
    outro_text: str = ""
    duration_seconds: int = 30
    fps: int = 12
    width: int = 720
    height: int = 1280
    publish_mode: bool = True
    scenes: tuple[AssetSceneSpec, ...] = ()


def short_assets_dir(root: Path) -> Path:
    path = root / "data" / "generated" / "short_assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_short_assets(root: Path) -> list[dict]:
    assets = []
    base = short_assets_dir(root)
    for path in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.suffix.lower() not in VALID_IMAGE_SUFFIXES:
            continue
        assets.append(
            {
                "name": path.name,
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "size": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            }
        )
    return assets


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _cover_resize(img: Image.Image, width: int, height: int) -> Image.Image:
    img = img.convert("RGB")
    src_w, src_h = img.size
    scale = max(width / max(1, src_w), height / max(1, src_h))
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = max(0, (new_w - width) // 2)
    top = max(0, (new_h - height) // 2)
    return img.crop((left, top, left + width, top + height))


def _fit_base(path: Path, width: int, height: int) -> Image.Image:
    img = Image.open(path)
    img = _cover_resize(img, width, height)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(1.06)
    return img


def _motion_crop(img: Image.Image, motion: str, progress: float, width: int, height: int) -> Image.Image:
    """Visible, smooth camera motion. No sine jitter."""
    motion = motion if motion in MOTIONS else "zoom_in"
    if motion == "hold":
        return img
    e = _ease(progress)
    zoom = 1.18
    if motion == "zoom_out":
        z = zoom - (zoom - 1.0) * e
    else:
        z = 1.0 + (zoom - 1.0) * e
    if motion in {"pan_left", "pan_right", "slide_up", "parallax_soft"}:
        z = 1.16
    big_w, big_h = int(width * z), int(height * z)
    big = img.resize((big_w, big_h), Image.Resampling.LANCZOS)
    max_x = max(0, big_w - width)
    max_y = max(0, big_h - height)
    if motion == "pan_left":
        x = int(max_x * (1.0 - e))
        y = max_y // 2
    elif motion == "pan_right":
        x = int(max_x * e)
        y = max_y // 2
    elif motion == "slide_up":
        x = max_x // 2
        y = int(max_y * e)
    else:
        x = max_x // 2
        y = max_y // 2
    return big.crop((x, y, x + width, y + height))


def _safe_text(text: str, limit: int = 160) -> str:
    return " ".join((text or "").strip().split())[:limit]


def _draw_text_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, align: str = "center", alpha: int = 255) -> None:
    text = _safe_text(text, 220)
    if not text:
        return
    x1, y1, x2, y2 = box
    max_chars = 24 if font.size >= 48 else 34
    lines = textwrap.wrap(text, width=max_chars)[:3]
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + max(0, len(lines) - 1) * 10
    y = y1 + max(0, (y2 - y1 - total_h) // 2)
    for idx, line in enumerate(lines):
        tw = line_widths[idx]
        x = x1 if align == "left" else x1 + max(0, (x2 - x1 - tw) // 2)
        stroke = (0, 0, 0, min(255, alpha))
        fill = (255, 255, 255, min(255, alpha))
        for ox, oy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            draw.text((x + ox, y + oy), line, font=font, fill=stroke)
        draw.text((x, y), line, font=font, fill=fill)
        y += line_heights[idx] + 10


def _draw_light_sweep(draw: ImageDraw.ImageDraw, width: int, height: int, local_progress: float, scene_idx: int) -> None:
    sweep = int((local_progress * 1.35 - 0.18) * (width + 420)) - 210
    color = (255, 255, 255, 26 if scene_idx % 2 else 38)
    draw.polygon([(sweep, 0), (sweep + 140, 0), (sweep + 420, height), (sweep + 250, height)], fill=color)


def _draw_speed_lines(draw: ImageDraw.ImageDraw, width: int, height: int, local_progress: float, direction: int = 1) -> None:
    for i in range(22):
        y = int(210 + i * 42 + math.sin(local_progress * math.tau + i) * 12)
        length = 80 + (i % 5) * 34
        base = int((local_progress * 980 + i * 97) % (width + 220)) - 110
        x1 = base if direction > 0 else width - base
        x2 = x1 - direction * length
        draw.line([x1, y, x2, y + direction * 8], fill=(255, 255, 255, 58), width=3)


def _draw_pulse_rings(draw: ImageDraw.ImageDraw, width: int, height: int, local_progress: float, scene_idx: int) -> None:
    cx = int(width * (0.5 + 0.18 * math.sin(scene_idx + 0.7)))
    cy = int(height * (0.48 + 0.12 * math.cos(scene_idx + 0.3)))
    for j in range(4):
        phase = (local_progress + j * 0.23) % 1.0
        r = int(45 + phase * 330)
        a = int(125 * (1.0 - phase))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, a), width=4)


def _draw_particles(draw: ImageDraw.ImageDraw, width: int, height: int, local_progress: float, scene_idx: int) -> None:
    # Deterministic particles: stable identity, visible motion.
    for i in range(42):
        seed = (scene_idx + 1) * 1009 + i * 917
        base_x = (seed * 37) % width
        base_y = (seed * 53) % height
        speed_x = 30 + (i % 7) * 18
        speed_y = 22 + (i % 5) * 14
        x = int((base_x + local_progress * speed_x * (1 + scene_idx % 3)) % width)
        y = int((base_y + local_progress * speed_y * 2.5) % height)
        r = 2 + (i % 4)
        a = 38 + (i % 5) * 12
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))


def _draw_scan_hud(draw: ImageDraw.ImageDraw, width: int, height: int, local_progress: float, scene_idx: int) -> None:
    y = int(170 + local_progress * (height - 460))
    draw.rectangle([0, y - 2, width, y + 2], fill=(130, 230, 255, 86))
    for side in [54, width - 174]:
        draw.rounded_rectangle([side, 245, side + 120, 330], radius=18, outline=(180, 230, 255, 80), width=3)
        draw.line([side + 20, 285, side + 96, 285], fill=(180, 230, 255, 90), width=3)
    if scene_idx % 2 == 0:
        draw.arc([width - 210, 180, width - 70, 320], start=int(local_progress * 360), end=int(local_progress * 360 + 210), fill=(170, 230, 255, 92), width=5)


def _draw_animated_overlay(frame: Image.Image, scene: AssetSceneSpec, scene_idx: int, scene_count: int, local_progress: float, global_progress: float) -> Image.Image:
    width, height = frame.size
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    motion = scene.motion if scene.motion in MOTIONS else "zoom_in"

    _draw_light_sweep(draw, width, height, local_progress, scene_idx)
    _draw_particles(draw, width, height, local_progress, scene_idx)
    if motion in {"pan_left", "pan_right"}:
        _draw_speed_lines(draw, width, height, local_progress, 1 if motion == "pan_right" else -1)
    elif motion == "parallax_soft":
        _draw_pulse_rings(draw, width, height, local_progress, scene_idx)
        _draw_scan_hud(draw, width, height, local_progress, scene_idx)
    elif motion == "slide_up":
        for j in range(4):
            yy = int(height - (local_progress * height + j * 125) % height)
            draw.rectangle([0, yy, width, yy + 8], fill=(255, 255, 255, 45))
    else:
        _draw_pulse_rings(draw, width, height, local_progress, scene_idx)

    # Scene beat marker, looks like motion graphics rather than debug.
    beat = _ease(min(1.0, local_progress * 2.2))
    bar_w = int((width - 110) * beat)
    draw.rounded_rectangle([55, 214, 55 + bar_w, 224], radius=6, fill=(255, 255, 255, 148))
    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def _parallax_frame(base: Image.Image, local_progress: float, width: int, height: int) -> Image.Image:
    bg = base.resize((int(width * 1.18), int(height * 1.18)), Image.Resampling.LANCZOS)
    bg = bg.crop(((bg.width - width) // 2, (bg.height - height) // 2, (bg.width - width) // 2 + width, (bg.height - height) // 2 + height))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=10))
    bg = ImageEnhance.Brightness(bg).enhance(0.72)
    fg_w, fg_h = int(width * 0.91), int(height * 0.91)
    fg = base.resize((fg_w, fg_h), Image.Resampling.LANCZOS)
    x = (width - fg_w) // 2 + int(math.sin(local_progress * math.tau) * 24)
    y = (height - fg_h) // 2 + int(math.cos(local_progress * math.tau) * 34)
    bg.paste(fg, (x, y))
    return bg


def _overlay_caption(frame: Image.Image, caption: str, hook: str, outro: str, scene_idx: int, scene_count: int, local_progress: float, publish: bool) -> Image.Image:
    width, height = frame.size
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rectangle([0, 0, width, 215], fill=(0, 0, 0, 84))
    draw.rectangle([0, height - 330, width, height], fill=(0, 0, 0, 128))
    text_alpha = int(170 + 85 * _ease(min(1.0, local_progress * 2.4)))
    if hook and scene_idx == 0:
        _draw_text_box(draw, (44, 48, width - 44, 190), hook, _font(52), align="center", alpha=text_alpha)
    if caption:
        # Small animated lift instead of static/vibrating label.
        lift = int((1.0 - _ease(min(1.0, local_progress * 2.0))) * 24)
        _draw_text_box(draw, (54, height - 280 - lift, width - 54, height - 95 - lift), caption, _font(44), align="center", alpha=text_alpha)
    if outro and scene_idx == scene_count - 1 and local_progress > 0.42:
        _draw_text_box(draw, (58, height - 145, width - 58, height - 44), outro, _font(34), align="center", alpha=255)
    if publish:
        rail_w = int((width - 96) * ((scene_idx + local_progress) / max(1, scene_count)))
        draw.rounded_rectangle([48, height - 36, width - 48, height - 26], radius=6, fill=(255, 255, 255, 58))
        draw.rounded_rectangle([48, height - 36, 48 + rail_w, height - 26], radius=6, fill=(255, 255, 255, 220))
    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def _fade(frame: Image.Image, local_progress: float) -> Image.Image:
    fade_len = 0.075
    alpha = 1.0
    if local_progress < fade_len:
        alpha = local_progress / fade_len
    elif local_progress > 1.0 - fade_len:
        alpha = (1.0 - local_progress) / fade_len
    if alpha >= 0.995:
        return frame
    black = Image.new("RGB", frame.size, (0, 0, 0))
    return Image.blend(black, frame, max(0.0, min(1.0, alpha)))


def build_asset_short(root: Path, spec: AssetShortSpec, output_dir: Path) -> Path:
    scenes = [scene for scene in spec.scenes if scene.asset_path]
    if not scenes:
        raise RuntimeError("No image assets selected. Upload/select at least one image.")
    scenes = scenes[:6]
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = max(6, min(120, int(spec.duration_seconds)))
    fps = max(8, min(24, int(spec.fps)))
    width, height = spec.width, spec.height
    total_frames = duration * fps
    frames_per_scene = max(1, total_frames // len(scenes))
    bases: list[Image.Image] = []
    for scene in scenes:
        path = root / scene.asset_path
        if not path.exists():
            raise RuntimeError(f"Missing asset: {scene.asset_path}")
        bases.append(_fit_base(path, width, height))
    stamp = utc_now_iso().replace(":", "-").replace("+", "Z")
    output = output_dir / f"ASSET_SHORT_{stamp}.mp4"
    with imageio.get_writer(str(output), fps=fps, codec="libx264", quality=8, macro_block_size=None) as writer:
        for frame_idx in range(total_frames):
            scene_idx = min(len(scenes) - 1, frame_idx // frames_per_scene)
            scene_start = scene_idx * frames_per_scene
            local_frame = frame_idx - scene_start
            local_total = frames_per_scene if scene_idx < len(scenes) - 1 else max(1, total_frames - scene_start)
            local_progress = local_frame / max(1, local_total - 1)
            global_progress = frame_idx / max(1, total_frames - 1)
            scene = scenes[scene_idx]
            if scene.motion == "parallax_soft":
                frame = _parallax_frame(bases[scene_idx], local_progress, width, height)
            else:
                frame = _motion_crop(bases[scene_idx], scene.motion, local_progress, width, height)
            frame = _draw_animated_overlay(frame, scene, scene_idx, len(scenes), local_progress, global_progress)
            frame = _fade(frame, local_progress)
            frame = _overlay_caption(frame, scene.caption, spec.hook_text, spec.outro_text, scene_idx, len(scenes), local_progress, spec.publish_mode)
            writer.append_data(np.asarray(frame))
    summary = {
        "sprint": 16,
        "builder": "kinetic_asset_short_builder",
        "status": "built",
        "output_file": str(output),
        "title": spec.title,
        "duration_seconds": duration,
        "fps": fps,
        "width": width,
        "height": height,
        "scene_count": len(scenes),
        "assets": [scene.asset_path for scene in scenes],
        "motions": [scene.motion for scene in scenes],
        "captions": [scene.caption for scene in scenes],
        "hook_text": spec.hook_text,
        "outro_text": spec.outro_text,
        "publish_mode": spec.publish_mode,
        "animation_layers": ["light_sweep", "particles", "pulse_rings", "speed_lines", "scan_hud", "animated_caption_lift"],
        "credits_spent": 0,
        "built_at": utc_now_iso(),
    }
    (output_dir / "asset_short_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output
