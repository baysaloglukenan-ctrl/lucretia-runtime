from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


WIDTH = 320
HEIGHT = 576


def _face(draw: ImageDraw.ImageDraw, x: int, y: int, mood: str) -> None:
    eye_y = y - 18
    if mood == "angry":
        draw.line((x - 21, eye_y - 8, x - 5, eye_y - 2), fill=(40, 25, 25, 255), width=4)
        draw.line((x + 5, eye_y - 2, x + 21, eye_y - 8), fill=(40, 25, 25, 255), width=4)
    elif mood == "afraid":
        draw.arc((x - 24, eye_y - 13, x - 2, eye_y + 6), 185, 350, fill=(40, 30, 30, 255), width=3)
        draw.arc((x + 2, eye_y - 13, x + 24, eye_y + 6), 190, 355, fill=(40, 30, 30, 255), width=3)
    for offset in (-13, 13):
        draw.ellipse((x + offset - 8, eye_y - 9, x + offset + 8, eye_y + 9), fill=(250, 253, 255, 255))
        draw.ellipse((x + offset - 2, eye_y - 3, x + offset + 3, eye_y + 3), fill=(25, 38, 48, 255))
    if mood == "afraid":
        draw.ellipse((x - 7, y + 2, x + 7, y + 17), outline=(35, 30, 30, 255), width=3)
    elif mood == "angry":
        draw.arc((x - 15, y + 2, x + 15, y + 20), 190, 350, fill=(35, 25, 25, 255), width=3)
    else:
        draw.arc((x - 15, y - 1, x + 15, y + 18), 10, 170, fill=(35, 35, 40, 255), width=3)


def _character(draw: ImageDraw.ImageDraw, shape: str, x: int, y: int, mood: str) -> None:
    outline = (238, 244, 248, 255)
    if shape == "screw":
        draw.rounded_rectangle((x - 31, y - 70, x + 31, y - 22), radius=15, fill=(186, 201, 216, 255), outline=outline, width=3)
        draw.polygon([(x - 18, y - 22), (x + 18, y - 22), (x + 13, y + 43), (x, y + 58), (x - 13, y + 43)], fill=(156, 176, 195, 255), outline=outline)
        for offset in range(-12, 38, 12):
            draw.line((x - 14, y + offset, x + 14, y + offset + 8), fill=(90, 112, 130, 255), width=3)
        _face(draw, x, y - 36, mood)
    elif shape == "nut":
        points = [(x + int(math.cos(math.radians(a)) * 46), y + int(math.sin(math.radians(a)) * 46)) for a in range(0, 360, 60)]
        draw.polygon(points, fill=(224, 166, 53, 255), outline=outline)
        draw.ellipse((x - 17, y - 17, x + 17, y + 17), fill=(72, 68, 60, 255), outline=(255, 215, 100, 255), width=3)
        _face(draw, x, y - 3, mood)
    elif shape == "key":
        draw.ellipse((x - 38, y - 62, x + 22, y - 2), fill=(218, 166, 56, 255), outline=outline, width=3)
        draw.ellipse((x - 23, y - 47, x + 7, y - 17), fill=(78, 72, 55, 255))
        draw.rounded_rectangle((x - 3, y - 10, x + 15, y + 55), radius=7, fill=(218, 166, 56, 255), outline=outline, width=2)
        draw.rectangle((x + 14, y + 29, x + 35, y + 44), fill=(218, 166, 56, 255))
        _face(draw, x - 8, y - 22, mood)
    elif shape == "spring":
        for offset in range(-52, 45, 13):
            draw.arc((x - 35, y + offset, x + 35, y + offset + 24), 0, 180, fill=(184, 204, 219, 255), width=8)
            draw.arc((x - 35, y + offset + 6, x + 35, y + offset + 30), 180, 360, fill=(120, 147, 169, 255), width=8)
        _face(draw, x, y - 7, mood)
    elif shape == "cork":
        draw.rounded_rectangle((x - 36, y - 57, x + 36, y + 52), radius=17, fill=(178, 122, 70, 255), outline=outline, width=3)
        for dx, dy in ((-20, -42), (20, -32), (-18, 35), (17, 22)):
            draw.ellipse((x + dx - 3, y + dy - 3, x + dx + 3, y + dy + 3), fill=(115, 76, 48, 150))
        _face(draw, x, y - 2, mood)
    elif shape == "eraser":
        draw.rounded_rectangle((x - 43, y - 43, x + 43, y + 43), radius=13, fill=(56, 129, 211, 255), outline=outline, width=3)
        draw.rectangle((x - 43, y + 17, x + 43, y + 43), fill=(38, 93, 167, 255))
        _face(draw, x, y - 1, mood)
    elif shape in {"paper_plane", "feather"}:
        draw.polygon([(x - 48, y + 25), (x + 52, y - 30), (x + 14, y + 42), (x - 3, y + 8)], fill=(238, 239, 229, 255), outline=outline)
        draw.line((x - 20, y + 8, x + 36, y - 18), fill=(63, 121, 192, 255), width=4)
        _face(draw, x, y + 5, mood)
    elif shape in {"spool", "book"}:
        draw.rounded_rectangle((x - 38, y - 48, x + 38, y + 48), radius=10, fill=(111, 76, 48, 255), outline=outline, width=3)
        for offset in range(-28, 33, 10):
            draw.line((x - 37, y + offset, x + 37, y + offset), fill=(39, 163, 164, 255), width=5)
        _face(draw, x, y, mood)
    elif shape in {"fan", "dryer"}:
        draw.ellipse((x - 48, y - 52, x + 48, y + 44), fill=(46, 132, 154, 255), outline=outline, width=4)
        for angle in (0, 120, 240):
            radians = math.radians(angle)
            tip = (x + int(math.cos(radians) * 35), y - 4 + int(math.sin(radians) * 35))
            draw.line((x, y - 4, tip[0], tip[1]), fill=(236, 188, 55, 255), width=12)
        draw.ellipse((x - 8, y - 12, x + 8, y + 4), fill=(60, 65, 72, 255))
        _face(draw, x, y + 17, "angry")
    elif shape in {"paper_boat", "soap"}:
        draw.polygon([(x - 50, y + 10), (x + 50, y + 10), (x + 28, y + 47), (x - 30, y + 47)], fill=(233, 238, 230, 255), outline=outline)
        draw.polygon([(x - 28, y + 8), (x, y - 47), (x + 28, y + 8)], fill=(218, 73, 67, 255), outline=outline)
        _face(draw, x, y + 20, mood)
    elif shape in {"sponge", "towel"}:
        draw.rounded_rectangle((x - 43, y - 44, x + 43, y + 44), radius=16, fill=(235, 196, 52, 255), outline=outline, width=3)
        for dx, dy in ((-24, -25), (21, -31), (-29, 27), (28, 20)):
            draw.ellipse((x + dx - 4, y + dy - 4, x + dx + 4, y + dy + 4), fill=(178, 141, 35, 180))
        _face(draw, x, y, mood)
    elif shape in {"pitcher", "faucet"}:
        draw.rounded_rectangle((x - 37, y - 50, x + 30, y + 48), radius=14, fill=(139, 73, 181, 255), outline=outline, width=3)
        draw.arc((x + 8, y - 31, x + 65, y + 29), 250, 105, fill=(203, 171, 225, 255), width=12)
        draw.polygon([(x - 36, y - 42), (x - 58, y - 27), (x - 35, y - 17)], fill=(139, 73, 181, 255))
        _face(draw, x - 5, y, "angry")
    elif shape == "magnet":
        draw.arc((x - 48, y - 61, x + 48, y + 40), 22, 338, fill=(211, 47, 55, 255), width=25)
        draw.rectangle((x - 48, y + 3, x - 22, y + 46), fill=(38, 44, 52, 255))
        draw.rectangle((x + 22, y + 3, x + 48, y + 46), fill=(38, 44, 52, 255))
        _face(draw, x, y - 17, "angry")
    else:
        draw.rounded_rectangle((x - 46, y - 35, x + 46, y + 35), radius=10, fill=(48, 101, 197, 255), outline=outline, width=3)
        draw.rectangle((x + 20, y - 35, x + 46, y + 35), fill=(210, 52, 61, 255))
        _face(draw, x, y, "angry")


def render_story_keyframe(root: Path, production_key: str, scene_index: int, story: dict) -> str:
    palette = ((18, 31, 52), (31, 45, 67), (22, 38, 55))
    image = Image.new("RGB", (WIDTH, HEIGHT), palette[scene_index % len(palette)])
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 386, WIDTH, HEIGHT), fill=(73, 92, 83, 255))
    draw.ellipse((-90, -70, 220, 240), fill=(255, 205, 104, 30))
    draw.rectangle((20, 420, 300, 432), fill=(117, 91, 61, 180))

    required = story["scenes"][scene_index][3]
    if scene_index == 0:
        positions = ((92, 355), (225, 355))
    elif scene_index == 1:
        positions = ((205, 350), (62, 360), (275, 348))
    else:
        positions = ((82, 355), (178, 360), (276, 350))
    for position, character_index in zip(positions, required):
        mood = "happy"
        if scene_index == 1 and character_index == 1:
            mood = "afraid"
        if character_index == 2:
            mood = "angry"
        _character(draw, story["characters"][character_index][3], position[0], position[1], mood)
    resolution_visual = story.get("resolution_visual")
    if scene_index == 2 and resolution_visual == "wedge":
        draw.polygon([(220, 390), (254, 310), (267, 390)], fill=(173, 116, 62, 255), outline=(239, 205, 151, 255))
    elif scene_index == 2 and resolution_visual == "thread":
        draw.line((82, 350, 178, 350), fill=(39, 190, 181, 255), width=6)
    elif scene_index == 2 and resolution_visual == "dry_path":
        draw.arc((20, 388, 250, 500), 185, 350, fill=(70, 174, 221, 120), width=12)

    output_dir = root / "data" / "generated" / "short_assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"AUTO_{production_key}_SCENE_{scene_index + 1}.png"
    image.save(output, "PNG")
    return str(output.relative_to(root)).replace("\\", "/")
