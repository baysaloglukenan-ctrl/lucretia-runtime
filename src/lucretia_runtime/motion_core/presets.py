from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .scene_models import AnimationSpec, MotionSceneSpec, SpriteSpec
from .trajectories import magnet_pull_keyframes


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def motion_core_assets_dir(root: Path) -> Path:
    path = root / "data" / "generated" / "motion_core_assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_demo_background(path: Path, width: int = 720, height: int = 1280) -> None:
    img = Image.new("RGB", (width, height), (14, 18, 27))
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(height):
        shade = int(22 + 44 * (y / height))
        draw.line([(0, y), (width, y)], fill=(shade // 2, shade, shade + 20, 255))
    table_y = int(height * 0.70)
    draw.polygon([(0, table_y), (width, table_y - 56), (width, height), (0, height)], fill=(8, 10, 16, 238))
    for x in range(0, width, 48):
        draw.line([(x, table_y), (x + 220, height)], fill=(255, 255, 255, 18), width=1)
    draw.rounded_rectangle([42, 54, width - 42, 148], radius=24, fill=(0, 0, 0, 110), outline=(255, 255, 255, 45), width=2)
    draw.text((68, 84), "MOTION CORE · OBJECT ANIMATION", font=_font(28), fill=(235, 245, 255, 232))
    img.save(path)


def create_magnet_sprite(path: Path, size: tuple[int, int] = (260, 240)) -> None:
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    draw.arc([28, 10, w - 28, h + 76], 74, 286, fill=(232, 50, 68, 255), width=52)
    draw.line([42, h - 72, 104, h - 72], fill=(245, 245, 255, 255), width=38)
    draw.line([w - 104, h - 72, w - 42, h - 72], fill=(245, 245, 255, 255), width=38)
    draw.rounded_rectangle([58, h - 100, 114, h - 48], radius=12, fill=(255, 255, 255, 255))
    draw.rounded_rectangle([w - 114, h - 100, w - 58, h - 48], radius=12, fill=(255, 255, 255, 255))
    draw.text((w // 2 - 35, h // 2 - 10), "MAG", font=_font(24), fill=(255, 238, 238, 255))
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=160, threshold=3))
    img.save(path)


def create_screw_sprite(path: Path, size: tuple[int, int] = (220, 80)) -> None:
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    body = [42, 25, w - 38, 55]
    draw.rounded_rectangle(body, radius=15, fill=(206, 214, 222, 255), outline=(248, 252, 255, 255), width=3)
    # Thread lines.
    for x in range(62, w - 55, 18):
        draw.line([x, 27, x + 22, 54], fill=(126, 136, 148, 190), width=3)
    # Head.
    draw.ellipse([8, 10, 72, 74], fill=(185, 194, 205, 255), outline=(248, 252, 255, 255), width=3)
    draw.line([24, 42, 56, 42], fill=(88, 96, 110, 220), width=5)
    draw.line([40, 26, 40, 58], fill=(88, 96, 110, 170), width=4)
    # Tip.
    draw.polygon([(w - 40, 24), (w - 4, h // 2), (w - 40, 56)], fill=(218, 226, 235, 255), outline=(248, 252, 255, 210))
    img = img.filter(ImageFilter.UnsharpMask(radius=1.1, percent=180, threshold=2))
    img.save(path)


def ensure_demo_assets(root: Path, width: int = 720, height: int = 1280) -> dict[str, str]:
    base = motion_core_assets_dir(root)
    bg = base / "motion_core_bg.png"
    magnet = base / "magnet_sprite.png"
    screw = base / "screw_sprite.png"
    if not bg.exists():
        create_demo_background(bg, width, height)
    if not magnet.exists():
        create_magnet_sprite(magnet)
    if not screw.exists():
        create_screw_sprite(screw)
    return {
        "background": str(bg.relative_to(root)).replace("\\", "/"),
        "magnet": str(magnet.relative_to(root)).replace("\\", "/"),
        "screw": str(screw.relative_to(root)).replace("\\", "/"),
    }


def magnet_pull_scene(root: Path, width: int = 720, height: int = 1280, duration: float = 5.0, fps: int = 24) -> MotionSceneSpec:
    assets = ensure_demo_assets(root, width, height)
    start = (width * 0.28, height * 0.72)
    target = (width * 0.66, height * 0.44)
    magnet = SpriteSpec(object_id="magnet", image_path=assets["magnet"], anchor_x=0.5, anchor_y=0.55, z_index=5, default_x=target[0], default_y=target[1], default_scale=1.0)
    screw = SpriteSpec(object_id="screw", image_path=assets["screw"], anchor_x=0.5, anchor_y=0.5, z_index=20)
    screw_animation = AnimationSpec(object_id="screw", keyframes=magnet_pull_keyframes(start, target, arc_height=-210, rotation=920), easing="snap", motion_blur=True, shadow=True)
    return MotionSceneSpec(
        scene_id="MCORE_MAGNET_PULL_DEMO",
        background_path=assets["background"],
        sprites=(magnet, screw),
        animations=(screw_animation,),
        duration_seconds=duration,
        fps=fps,
        width=width,
        height=height,
        caption="Șurubul este atras de magnet — obiect animat local, nu slideshow.",
        effects={
            "magnet_pulse": True,
            "magnet_strength": 1.2,
            "metal_particles": True,
            "particle_count": 36,
            "impact_flash": True,
            "start": start,
            "target": target,
        },
    )
