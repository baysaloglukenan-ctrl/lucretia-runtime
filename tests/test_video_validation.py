from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import numpy as np

from lucretia_runtime.video_validation import validate_scene_video


def test_video_validation_rejects_non_video(tmp_path: Path) -> None:
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"broken")

    result = validate_scene_video(path, 2)

    assert result["valid"] is False
    assert result["errors"]


def _write_video(path: Path, frames: list[np.ndarray], fps: int = 8) -> None:
    writer = imageio.get_writer(path, fps=fps, codec="libx264", macro_block_size=None)
    try:
        for frame in frames:
            writer.append_data(frame)
    finally:
        writer.close()


def test_video_validation_decodes_and_measures_video(tmp_path: Path) -> None:
    path = tmp_path / "valid.mp4"
    _write_video(path, [np.full((96, 64, 3), value * 8, dtype=np.uint8) for value in range(16)])

    result = validate_scene_video(path, 2)

    assert result["valid"] is True
    assert result["duration_seconds"] >= 1.9
    assert result["size_bytes"] >= 1024
    assert result["first_frame"]["portrait"] is True


def test_video_validation_compares_first_frame_to_source(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source_frame = np.zeros((96, 64, 3), dtype=np.uint8)
    source_frame[:, :32] = (220, 30, 30)
    source_frame[:, 32:] = (20, 180, 80)
    imageio.imwrite(source, source_frame)
    matching = tmp_path / "matching.mp4"
    _write_video(matching, [source_frame for _ in range(16)])

    result = validate_scene_video(matching, 2, source_path=source)

    assert result["valid"] is True
    assert result["first_frame"]["source_similarity"] > 0.9


def test_video_validation_rejects_unrelated_or_landscape_opening(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    imageio.imwrite(source, np.zeros((96, 64, 3), dtype=np.uint8))
    unrelated = tmp_path / "unrelated.mp4"
    _write_video(unrelated, [np.full((64, 96, 3), 255, dtype=np.uint8) for _ in range(16)])

    result = validate_scene_video(unrelated, 2, source_path=source)

    assert result["valid"] is False
    assert result["first_frame"]["portrait"] is False
    assert result["first_frame"]["source_similarity"] < 0.35
