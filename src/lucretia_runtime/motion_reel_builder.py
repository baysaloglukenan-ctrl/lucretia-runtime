from __future__ import annotations

import json
import math
import random
import textwrap
from dataclasses import dataclass
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .prompt_catalog import compose_prompt, get_catalog
from .provider_models import utc_now_iso


TEMPLATES: list[dict] = [
    {"id": "atlas_object_lab", "label": "Atlas Object Lab", "description": "Magnet, material block, metal particles, tabletop experiment."},
    {"id": "story_cards", "label": "Story Cards", "description": "Hook/detail/payoff cards with bold motion and clean structure."},
    {"id": "cinematic_product", "label": "Cinematic Product", "description": "Pedestal, spotlight, macro panels, premium reveal."},
    {"id": "noir_signal", "label": "Noir Signal", "description": "Rain, neon, device pulse, coded signal atmosphere."},
    {"id": "cyber_interface", "label": "Cyber Interface", "description": "Hologram panels, node graph, prompt engine look."},
    {"id": "urban_kinetic", "label": "Urban Kinetic", "description": "Road lines, light streaks, speed and arrival energy."},
    {"id": "fitness_cut", "label": "Fitness Cut", "description": "Gym timer, silhouette, rep rhythm, training energy."},
]


@dataclass(frozen=True)
class MotionReelSpec:
    universe_id: str = "atlas_lab"
    scene_id: str = "lab_object_awake"
    preset_id: str = "hook_fast"
    custom_prompt: str = ""
    template_id: str = "atlas_object_lab"
    duration_seconds: int = 30
    fps: int = 12
    width: int = 720
    height: int = 1280


def get_motion_templates() -> list[dict]:
    return [dict(item) for item in TEMPLATES]


def _find(items: list[dict], item_id: str) -> dict | None:
    return next((item for item in items if item.get("id") == item_id), None)


def _labels(spec: MotionReelSpec) -> tuple[str, str, str, str]:
    catalog = get_catalog()
    universe = _find(catalog.get("universes", []), spec.universe_id) or {}
    scene = _find(catalog.get("scenes", []), spec.scene_id) or {}
    preset = _find(catalog.get("presets", []), spec.preset_id) or {}
    template = _find(TEMPLATES, spec.template_id) or TEMPLATES[0]
    return (
        str(universe.get("label", spec.universe_id)),
        str(scene.get("label", spec.scene_id)),
        str(preset.get("label", spec.preset_id)),
        str(template.get("label", spec.template_id)),
    )


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


def _seed_color(seed: str, low: int = 36, high: int = 190) -> tuple[int, int, int]:
    value = abs(hash(seed))
    span = max(1, high - low)
    return (low + value % span, low + (value // 19) % span, low + (value // 47) % span)


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _gradient(width: int, height: int, c1: tuple[int, int, int], c2: tuple[int, int, int], t: float, vignette: bool = True) -> Image.Image:
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    wave = 0.5 + 0.5 * np.sin((xx * 2.4 + yy * 2.1 + t * 0.8) * math.pi)
    if vignette:
        dist = np.sqrt((xx - 0.5) ** 2 + (yy - 0.5) ** 2)
        shade = np.clip(1.12 - dist * 1.45, 0.25, 1.0)
    else:
        shade = 1.0
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for idx in range(3):
        arr[:, :, idx] = np.clip((c1[idx] * (1.0 - wave) + c2[idx] * wave) * shade, 0, 255)
    return Image.fromarray(arr, mode="RGB")


def _rounded(draw: ImageDraw.ImageDraw, box: list[int], fill, outline=None, width: int = 1, radius: int = 34) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, fill: tuple[int, int, int], width_chars: int, max_lines: int = 4, line_gap: int = 7) -> None:
    x, y = xy
    for line in textwrap.wrap(text, width=width_chars)[:max_lines]:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap


def _frame_title(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, segment_name: str, progress: float) -> None:
    universe, scene, preset, template = _labels(spec)
    w, h = spec.width, spec.height
    top_h = 145
    _rounded(draw, [36, 36, w - 36, 36 + top_h], fill=(4, 10, 22, 150), outline=(220, 235, 255, 58), width=2, radius=30)
    draw.text((62, 62), segment_name.upper(), font=_font(40), fill=(238, 246, 255))
    draw.text((62, 112), f"{template} · {universe}", font=_font(23, bold=False), fill=(177, 196, 225))
    # progress rail
    rail_y = 36 + top_h - 28
    draw.rounded_rectangle([62, rail_y, w - 62, rail_y + 8], radius=5, fill=(42, 57, 82, 180))
    draw.rounded_rectangle([62, rail_y, 62 + int((w - 124) * progress), rail_y + 8], radius=5, fill=(235, 244, 255, 210))


def _segment(progress: float) -> tuple[int, float, str]:
    names = ["hook", "activate", "detail", "payoff"]
    idx = min(3, int(progress * 4.0))
    local = (progress - idx / 4.0) * 4.0
    return idx, max(0.0, min(1.0, local)), names[idx]


def _draw_particles(draw: ImageDraw.ImageDraw, width: int, height: int, progress: float, seed: int, count: int = 70, tint=(255, 255, 255)) -> None:
    rng = random.Random(seed)
    for i in range(count):
        speed = 0.14 + (i % 7) * 0.018
        px = int((rng.random() * width + progress * width * speed) % width)
        py = int((rng.random() * height + math.sin(progress * 9 + i) * 35) % height)
        r = 1 + (i % 4)
        a = 32 + (i % 5) * 14
        draw.ellipse([px - r, py - r, px + r, py + r], fill=(*tint, a))


def _draw_lab_objects(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, p: float, local: float, seed: int) -> None:
    w, h = spec.width, spec.height
    table_y = int(h * 0.66)
    draw.polygon([(0, table_y), (w, table_y - 40), (w, h), (0, h)], fill=(13, 18, 29, 230))
    # horseshoe magnet
    mx = int(w * (0.22 + 0.07 * math.sin(p * math.tau)))
    my = int(h * 0.49)
    draw.arc([mx - 80, my - 110, mx + 80, my + 110], 82, 278, fill=(225, 60, 76, 238), width=38)
    draw.line([mx - 85, my + 40, mx - 40, my + 40], fill=(235, 245, 255, 230), width=28)
    draw.line([mx + 40, my + 40, mx + 85, my + 40], fill=(235, 245, 255, 230), width=28)
    draw.text((mx - 38, my - 18), "MAG", font=_font(22), fill=(255, 240, 240))
    # material block / sponge
    bx = int(w * 0.58)
    by = int(h * 0.55 + math.sin(p * math.tau * 1.5) * 18)
    squeeze = int(30 * math.sin(p * math.tau * 2))
    block = [bx - 115 - squeeze // 2, by - 70 + squeeze, bx + 115 + squeeze // 2, by + 70 - squeeze // 2]
    _rounded(draw, block, fill=(238, 188, 71, 238), outline=(255, 230, 120, 230), width=3, radius=28)
    for i in range(18):
        xx = block[0] + 20 + (i * 31) % max(1, block[2] - block[0] - 40)
        yy = block[1] + 18 + ((i * 47) % max(1, block[3] - block[1] - 36))
        draw.ellipse([xx - 4, yy - 4, xx + 4, yy + 4], fill=(120, 83, 38, 95))
    # metal chips moving toward magnet
    for i in range(24):
        phase = (i / 24.0 + p * 0.65) % 1.0
        sx = int(w * (0.52 + 0.32 * ((i % 5) / 5)))
        sy = int(table_y - 30 - (i % 6) * 33)
        tx = mx + 30 + int(math.sin(i) * 16)
        ty = my + 10 + int(math.cos(i) * 38)
        e = _ease(phase)
        x = int(sx * (1 - e) + tx * e)
        y = int(sy * (1 - e) + ty * e)
        draw.rounded_rectangle([x - 12, y - 4, x + 12, y + 4], radius=4, fill=(220, 230, 242, 220))


def _draw_story_cards(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, p: float, local: float, segment_name: str) -> None:
    w, h = spec.width, spec.height
    universe, scene, preset, template = _labels(spec)
    titles = ["HOOK", "BUILD", "DETAIL", "PAYOFF"]
    subtitles = [universe, scene, preset, "READY FOR PROVIDER"]
    for i in range(4):
        base_y = 235 + i * 205
        shift = int((i - p * 4.0) * 34)
        fill = (7 + i * 10, 16 + i * 8, 32 + i * 12, 210)
        _rounded(draw, [58 + shift, base_y, w - 58 + shift, base_y + 155], fill=fill, outline=(210, 230, 255, 58 + i * 26), width=2, radius=32)
        draw.text((92 + shift, base_y + 30), titles[i], font=_font(36), fill=(238, 246, 255))
        draw.text((92 + shift, base_y + 82), subtitles[i][:42], font=_font(25, bold=False), fill=(180, 205, 238))
    x = int(80 + _ease(local) * (w - 160))
    draw.ellipse([x - 18, h - 145, x + 18, h - 109], fill=(255, 255, 255, 230))


def _draw_product(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, p: float, local: float) -> None:
    w, h = spec.width, spec.height
    # spotlight
    draw.polygon([(w // 2 - 200, 130), (w // 2 + 200, 130), (w - 40, h - 130), (40, h - 130)], fill=(255, 255, 255, 25))
    pedestal_y = int(h * 0.73)
    draw.ellipse([100, pedestal_y - 55, w - 100, pedestal_y + 60], fill=(12, 20, 34, 220), outline=(215, 230, 255, 78), width=3)
    # product cube
    cx, cy = w // 2, int(h * 0.54 + math.sin(p * math.tau) * 18)
    box_w, box_h = 230, 300
    face = [cx - box_w // 2, cy - box_h // 2, cx + box_w // 2, cy + box_h // 2]
    side = [(face[2], face[1]), (face[2] + 70, face[1] + 45), (face[2] + 70, face[3] + 45), (face[2], face[3])]
    top = [(face[0], face[1]), (face[0] + 70, face[1] + 45), (face[2] + 70, face[1] + 45), (face[2], face[1])]
    draw.polygon(top, fill=(96, 114, 150, 238), outline=(230, 240, 255, 180))
    draw.polygon(side, fill=(55, 70, 102, 238), outline=(230, 240, 255, 180))
    _rounded(draw, face, fill=(25, 37, 63, 244), outline=(235, 245, 255, 220), width=3, radius=24)
    draw.text((face[0] + 40, face[1] + 110), "HERO", font=_font(38), fill=(235, 244, 255))
    # macro panels
    for i in range(3):
        x = 54 + i * 212
        y = 920 + int(math.sin(p * math.tau + i) * 14)
        _rounded(draw, [x, y, x + 170, y + 105], fill=(8, 14, 27, 178), outline=(220, 235, 255, 70), width=2, radius=22)
        draw.line([x + 28, y + 42, x + 142, y + 42], fill=(225, 235, 255, 130), width=3)
        draw.line([x + 28, y + 68, x + 118, y + 68], fill=(225, 235, 255, 80), width=2)


def _draw_noir(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, p: float, local: float, seed: int) -> None:
    w, h = spec.width, spec.height
    rng = random.Random(seed)
    # rain
    for i in range(95):
        x = int((rng.random() * w + p * 160 + i * 7) % w)
        y = int((rng.random() * h + p * 750 + i * 13) % h)
        draw.line([x, y, x - 18, y + 72], fill=(180, 210, 255, 68), width=2)
    # window bars and silhouette
    for x in range(80, w, 130):
        draw.line([x, 210, x, h - 210], fill=(200, 225, 255, 38), width=2)
    draw.ellipse([250, 450, 470, 720], fill=(3, 8, 15, 230))
    draw.rounded_rectangle([205, 670, 515, 980], radius=90, fill=(3, 8, 15, 230))
    # device pulse
    cx, cy = w // 2, 995
    pulse = int(30 + 50 * (0.5 + 0.5 * math.sin(p * math.tau * 3)))
    draw.ellipse([cx - pulse, cy - pulse, cx + pulse, cy + pulse], outline=(120, 210, 255, 90), width=4)
    _rounded(draw, [cx - 95, cy - 42, cx + 95, cy + 42], fill=(7, 16, 27, 230), outline=(125, 225, 255, 190), width=3, radius=24)
    draw.text((cx - 48, cy - 16), "SIGNAL", font=_font(20), fill=(205, 240, 255))


def _draw_cyber(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, p: float, local: float) -> None:
    w, h = spec.width, spec.height
    # grid perspective
    horizon = 420
    for i in range(16):
        y = horizon + int((i / 16) ** 2 * (h - horizon))
        draw.line([0, y, w, y], fill=(120, 200, 255, 48), width=2)
    for i in range(-8, 9):
        x = w // 2 + i * 46
        draw.line([w // 2, horizon, x, h], fill=(120, 200, 255, 40), width=2)
    # interface panels
    for i in range(5):
        px = 42 + (i % 2) * 350 + int(math.sin(p * math.tau + i) * 18)
        py = 250 + i * 145
        _rounded(draw, [px, py, px + 285, py + 105], fill=(5, 20, 42, 175), outline=(95, 210, 255, 120), width=2, radius=20)
        draw.line([px + 22, py + 40, px + 230, py + 40], fill=(155, 230, 255, 130), width=3)
        draw.line([px + 22, py + 70, px + 185, py + 70], fill=(155, 230, 255, 80), width=2)
    # central generated asset
    cx, cy = w // 2, 840
    for r in range(160, 35, -26):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(120, 230, 255, 32), width=3)
    draw.regular_polygon((cx, cy, 72), n_sides=6, rotation=p * 360, fill=(215, 245, 255, 210), outline=(255, 255, 255, 230))


def _draw_urban(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, p: float, local: float) -> None:
    w, h = spec.width, spec.height
    horizon = 520
    draw.rectangle([0, horizon, w, h], fill=(5, 7, 12, 180))
    # road perspective
    draw.polygon([(w // 2 - 70, horizon), (w // 2 + 70, horizon), (w - 40, h), (40, h)], fill=(16, 19, 27, 230))
    for i in range(20):
        y = int(horizon + ((i / 20 + p * 0.8) % 1.0) ** 1.8 * (h - horizon))
        half = int((y - horizon) * 0.35 + 40)
        draw.line([w // 2 - half, y, w // 2 - half - 50, y + 90], fill=(230, 235, 255, 50), width=3)
        draw.line([w // 2 + half, y, w // 2 + half + 50, y + 90], fill=(230, 235, 255, 50), width=3)
        if i % 2 == 0:
            draw.line([w // 2, y, w // 2, y + 55], fill=(255, 220, 120, 130), width=5)
    # bike/headlights silhouette
    bx, by = w // 2, int(805 + math.sin(p * math.tau * 2) * 24)
    draw.ellipse([bx - 190, by + 100, bx - 90, by + 200], outline=(240, 245, 255, 220), width=10)
    draw.ellipse([bx + 90, by + 100, bx + 190, by + 200], outline=(240, 245, 255, 220), width=10)
    draw.line([bx - 140, by + 130, bx - 20, by + 40, bx + 120, by + 120], fill=(245, 245, 255, 210), width=14)
    draw.polygon([(bx + 118, by + 72), (bx + 250, by + 22), (bx + 250, by + 118)], fill=(255, 245, 190, 48))


def _draw_fitness(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, p: float, local: float) -> None:
    w, h = spec.width, spec.height
    # gym panels
    for i in range(6):
        x = 50 + i * 115
        draw.rectangle([x, 240, x + 20, 1040], fill=(210, 230, 255, 24))
    # silhouette
    cx, cy = w // 2, 650
    rep = abs(math.sin(p * math.tau * 3))
    draw.ellipse([cx - 42, cy - 230, cx + 42, cy - 146], fill=(5, 10, 18, 235))
    draw.rounded_rectangle([cx - 62, cy - 150, cx + 62, cy + 105], radius=42, fill=(5, 10, 18, 235))
    arm_y = int(cy - 70 - 120 * rep)
    draw.line([cx - 60, cy - 80, cx - 210, arm_y], fill=(5, 10, 18, 245), width=26)
    draw.line([cx + 60, cy - 80, cx + 210, arm_y], fill=(5, 10, 18, 245), width=26)
    # dumbbells
    for side in [-1, 1]:
        x = cx + side * 220
        y = arm_y
        draw.line([x - 45, y, x + 45, y], fill=(235, 242, 255, 210), width=10)
        draw.rectangle([x - 68, y - 28, x - 45, y + 28], fill=(235, 242, 255, 190))
        draw.rectangle([x + 45, y - 28, x + 68, y + 28], fill=(235, 242, 255, 190))
    # timer
    sec = int(99 - p * 99)
    _rounded(draw, [68, 930, w - 68, 1035], fill=(7, 15, 27, 190), outline=(220, 235, 255, 80), width=2, radius=24)
    draw.text((100, 955), f"REP TEMPO · {sec:02d}", font=_font(38), fill=(238, 246, 255))


def _draw_template(draw: ImageDraw.ImageDraw, spec: MotionReelSpec, progress: float, local: float, segment_name: str, seed: int) -> None:
    tid = spec.template_id
    if tid == "story_cards":
        _draw_story_cards(draw, spec, progress, local, segment_name)
    elif tid == "cinematic_product":
        _draw_product(draw, spec, progress, local)
    elif tid == "noir_signal":
        _draw_noir(draw, spec, progress, local, seed)
    elif tid == "cyber_interface":
        _draw_cyber(draw, spec, progress, local)
    elif tid == "urban_kinetic":
        _draw_urban(draw, spec, progress, local)
    elif tid == "fitness_cut":
        _draw_fitness(draw, spec, progress, local)
    else:
        _draw_lab_objects(draw, spec, progress, local, seed)


def _draw_motion_frame(spec: MotionReelSpec, frame_idx: int, total_frames: int, seed: int) -> Image.Image:
    width, height = spec.width, spec.height
    progress = frame_idx / max(1, total_frames - 1)
    segment_idx, local, segment_name = _segment(progress)
    c1 = _seed_color(spec.universe_id + spec.template_id + "a", 12, 95)
    c2 = _seed_color(spec.scene_id + spec.preset_id + "b", 55, 210)
    img = _gradient(width, height, c1, c2, progress).filter(ImageFilter.GaussianBlur(radius=0.75))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    tint = (210, 232, 255) if spec.template_id != "noir_signal" else (140, 210, 255)
    _draw_particles(draw, width, height, progress, seed + segment_idx * 131, count=62, tint=tint)
    _draw_template(draw, spec, progress, local, segment_name, seed + frame_idx)
    _frame_title(draw, spec, segment_name, progress)

    # Bottom prompt strip, readable but not dominant.
    prompt = spec.custom_prompt.strip() or compose_prompt(spec.universe_id, spec.scene_id, spec.preset_id, "")
    bottom_h = 150
    draw.rectangle([0, height - bottom_h, width, height], fill=(0, 0, 0, 120))
    _draw_wrapped(draw, (42, height - bottom_h + 28), prompt[:230], _font(21, bold=False), (216, 230, 248), width_chars=58, max_lines=3)

    composed = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    # subtle camera push/pan
    zoom = 1.0 + 0.055 * _ease(progress)
    crop_x = int((zoom - 1.0) * width * 0.5)
    crop_y = int((zoom - 1.0) * height * 0.5)
    if crop_x > 1 and crop_y > 1:
        pan = int(math.sin(progress * math.tau) * 8)
        cropped = composed.crop((max(0, crop_x + pan), crop_y, min(width, width - crop_x + pan), height - crop_y))
        composed = cropped.resize((width, height), Image.Resampling.LANCZOS)
    return composed


def build_motion_reel(spec: MotionReelSpec, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = max(5, min(90, int(spec.duration_seconds)))
    fps = max(8, min(24, int(spec.fps)))
    total_frames = duration * fps
    stamp = utc_now_iso().replace(":", "-").replace("+", "Z")
    output = output_dir / f"MOTION_REEL_{stamp}.mp4"
    seed = abs(hash((spec.universe_id, spec.scene_id, spec.preset_id, spec.template_id, spec.custom_prompt))) % 2_000_000_000
    with imageio.get_writer(str(output), fps=fps, codec="libx264", quality=8, macro_block_size=None) as writer:
        for frame_idx in range(total_frames):
            frame = _draw_motion_frame(spec, frame_idx, total_frames, seed + frame_idx)
            writer.append_data(np.asarray(frame))
    summary = {
        "sprint": 14,
        "builder": "template_motion_engine",
        "status": "built",
        "output_file": str(output),
        "duration_seconds": duration,
        "fps": fps,
        "width": spec.width,
        "height": spec.height,
        "universe_id": spec.universe_id,
        "scene_id": spec.scene_id,
        "preset_id": spec.preset_id,
        "template_id": spec.template_id,
        "custom_prompt": spec.custom_prompt,
        "credits_spent": 0,
        "built_at": utc_now_iso(),
    }
    (output_dir / "motion_reel_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output
