from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import numpy as np

from lucretia_runtime.final_reel_composer import captions_from_text, publish_single_shot, write_srt
from lucretia_runtime.video_validation import validate_scene_video


def test_caption_cues_cover_voice_window(tmp_path: Path) -> None:
    cues = captions_from_text(
        "I know exactly what you're thinking. But trust me, this is going to work perfectly!",
        start=1.0,
        duration=6.0,
    )
    assert len(cues) == 4
    assert cues[0].start == 1.0
    assert cues[-1].end == 7.0
    path = write_srt(tmp_path / "captions.srt", cues)
    text = path.read_text(encoding="utf-8")
    assert "00:00:01,000 -->" in text
    assert "00:00:07,000" in text


def test_publish_single_shot_honors_requested_duration_and_platform_shape(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    writer = imageio.get_writer(source, fps=8, codec="libx264", macro_block_size=None)
    try:
        for index in range(12):
            frame = np.zeros((96, 64, 3), dtype=np.uint8)
            frame[:, :, 0] = index * 12
            writer.append_data(frame)
    finally:
        writer.close()

    output, subtitle = publish_single_shot(
        tmp_path,
        "TEST_1500MS",
        source,
        [{"start": 0.0, "end": 1.5, "text": "Test complet"}],
        duration_seconds=1.5,
    )

    report = validate_scene_video(output, 1.5)
    assert output.exists()
    assert subtitle.exists()
    assert report["valid"] is True
    assert abs(report["duration_seconds"] - 1.5) <= 0.05
    assert report["first_frame"]["width"] == 720
    assert report["first_frame"]["height"] == 1280
