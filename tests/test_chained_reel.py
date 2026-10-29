from __future__ import annotations

import runpy
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image


def _script_namespace() -> dict:
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_chained_reel_test.py"
    return runpy.run_path(str(script))


def test_extract_end_frame_uses_the_last_decoded_frame(tmp_path: Path) -> None:
    namespace = _script_namespace()
    video = tmp_path / "three_colors.mp4"
    colors = ((240, 0, 0), (0, 240, 0), (0, 0, 240))
    writer = imageio.get_writer(video, fps=3, codec="libx264", macro_block_size=None)
    try:
        for color in colors:
            writer.append_data(np.full((96, 64, 3), color, dtype=np.uint8))
    finally:
        writer.close()

    relative = namespace["_extract_end_frame"](tmp_path, video, 1)
    observed = np.asarray(Image.open(tmp_path / relative).convert("RGB"), dtype=np.float32).mean(axis=(0, 1))

    assert observed[2] > 200
    assert observed[0] < 30
    assert observed[1] < 30


def test_state_save_is_atomic_and_round_trips_unicode(tmp_path: Path) -> None:
    namespace = _script_namespace()
    state = {"status": "ready", "caption": "Împreună"}

    namespace["save"](tmp_path, state)

    restored = namespace["initialise"](tmp_path)
    assert restored["caption"] == "Împreună"
    assert not namespace["state_path"](tmp_path).with_suffix(".json.tmp").exists()
