from __future__ import annotations

import re
import subprocess
import time
import math
import os
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaptionCue:
    start: float
    end: float
    text: str


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def captions_from_text(text: str, *, start: float = 1.0, duration: float = 6.0, parts: int = 4) -> list[CaptionCue]:
    words = re.findall(r"\S+", text.strip())
    if not words:
        return []
    parts = max(1, min(parts, len(words)))
    chunks: list[list[str]] = [[] for _ in range(parts)]
    for index, word in enumerate(words):
        chunks[min(parts - 1, index * parts // len(words))].append(word)
    step = duration / parts
    return [
        CaptionCue(start + index * step, start + (index + 1) * step, " ".join(chunk))
        for index, chunk in enumerate(chunks)
        if chunk
    ]


def write_srt(path: Path, cues: list[CaptionCue]) -> Path:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(f"{index}\n{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n{cue.text}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(blocks), encoding="utf-8")
    os.replace(temporary, path)
    return path


def _filter_path(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    return value.replace(":", r"\:").replace("'", r"\'")


def _drawtext_filter(output_dir: Path, stamp: int, cues: list[CaptionCue]) -> str:
    filters = []
    for index, cue in enumerate(cues, start=1):
        text_path = output_dir / f"FINAL_REEL_{stamp}_caption_{index}.txt"
        text_path.write_text(cue.text, encoding="utf-8")
        filters.append(
            "drawtext="
            f"textfile='{_filter_path(text_path)}':"
            "font='Arial':fontsize=42:fontcolor=white:"
            "borderw=4:bordercolor=black:box=1:boxcolor=black@0.38:boxborderw=14:"
            "x=(w-text_w)/2:y=h-text_h-150:"
            f"enable='gte(t,{cue.start:.3f})*lt(t,{cue.end:.3f})'"
        )
    return ",".join(filters) if filters else "null"


def compose_final_reel(
    video_path: Path,
    audio_path: Path,
    output_dir: Path,
    *,
    transcript: str,
    audio_start: float = 1.0,
    audio_duration: float = 6.0,
) -> Path:
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    output = output_dir / f"FINAL_REEL_{stamp}.mp4"
    srt = output_dir / f"FINAL_REEL_{stamp}.srt"
    cues = captions_from_text(transcript, start=audio_start, duration=audio_duration)
    write_srt(srt, cues)
    delay_ms = max(0, round(audio_start * 1000))
    command = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        f"[0:v]{_drawtext_filter(output_dir, stamp, cues)}[v];[1:a]adelay={delay_ms}:all=1,apad=pad_dur=60[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output


def _write_original_soundtrack(path: Path, duration: float = 10.0, sample_rate: int = 44_100) -> Path:
    """Create a small original soundtrack so the publish artifact is never silent."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = round(duration * sample_rate)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        frames = bytearray()
        for index in range(count):
            moment = index / sample_rate
            fade = min(1.0, moment / 0.35, max(0.0, (duration - moment) / 0.6))
            beat_phase = moment % 0.5
            beat = 0.05 * math.sin(2 * math.pi * 82 * moment) * max(0.0, 1.0 - beat_phase / 0.16)
            bed = 0.07 * math.sin(2 * math.pi * 110 * moment) + 0.035 * math.sin(2 * math.pi * 165 * moment)
            pulse = 0.0
            cue_points = (
                (0.0, 440),
                (duration / 3, 260),
                (2 * duration / 3, 520),
                (max(0.0, duration - 0.8), 880),
            )
            for point, frequency in cue_points:
                delta = moment - point
                if 0 <= delta < 0.22:
                    pulse += 0.22 * math.sin(2 * math.pi * frequency * delta) * (1 - delta / 0.22)
            value = max(-1.0, min(1.0, (bed + beat + pulse) * fade))
            frames.extend(int(value * 32767).to_bytes(2, "little", signed=True))
        target.writeframes(frames)
    return path


def publish_single_shot(
    root: Path,
    production_id: str,
    video_path: Path,
    caption_data: list[dict],
    *,
    duration_seconds: float = 10.0,
) -> tuple[Path, Path]:
    """Burn timed captions and original audio into one continuous generated video."""

    if not video_path.exists():
        raise FileNotFoundError(video_path)
    output_dir = root / "data" / "generated" / "videos"
    subtitle_dir = root / "data" / "generated" / "subtitles"
    output_dir.mkdir(parents=True, exist_ok=True)
    cues = [CaptionCue(float(item["start"]), float(item["end"]), str(item["text"])) for item in caption_data]
    subtitle = write_srt(subtitle_dir / f"REEL_{production_id}.srt", cues)
    audio = _write_original_soundtrack(
        output_dir / f"REEL_{production_id}_soundtrack.wav",
        duration=duration_seconds,
    )
    output = output_dir / f"REEL_{production_id}_PUBLISH.mp4"
    temporary = output.with_name(f".{output.stem}.{time.time_ns()}.tmp.mp4")
    video_filter = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,"
        + _drawtext_filter(output_dir, int(time.time()), cues)
    )
    command = [
        _ffmpeg_exe(), "-y", "-i", str(video_path), "-i", str(audio),
        "-filter_complex", f"[0:v]{video_filter}[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-profile:v", "high", "-level", "4.1", "-r", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-t", f"{duration_seconds:g}", "-movflags", "+faststart", str(temporary),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output, subtitle
