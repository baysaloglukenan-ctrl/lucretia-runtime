from __future__ import annotations

import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from lucretia_runtime.production import get_production
from produce_three_reels import BATCH_NAME, load_manifest


SAMPLE_RATE = 48_000
UPLOAD = [
    {
        "filename": "01_surubul_piulita_magnetul_short.mp4",
        "title": "Magnetul l-a prins… dar Piuli avea un plan! 🧲 #shorts",
        "description": "Șurubel se grăbește spre prietena lui, dar un magnet rău îl trage în capcană. Poate o simplă bucată de lemn să-i salveze?\n\nAnimație originală din universul Lucreția.\n#animatie #pentrucopii #shorts #lucretia",
        "notes": [60, 64, 67, 72],
        "events": [(3.0, "danger"), (6.5, "impact"), (9.2, "win")],
    },
    {
        "filename": "02_avionul_si_firul_de_salvare_short.mp4",
        "title": "Avionul era să cadă! Firul de salvare ✈️ #shorts",
        "description": "O rafală îl împinge pe Pli spre margine. Mosorel are o singură șansă: firul roșu!\n\nAnimație originală din universul Lucreția.\n#animatie #aventura #pentrucopii #shorts",
        "notes": [67, 71, 74, 79],
        "events": [(3.0, "wind"), (6.5, "pull"), (9.2, "win")],
    },
    {
        "filename": "03_buretele_opreste_valul_short.mp4",
        "title": "Un burete mic împotriva unui val uriaș! 🌊 #shorts",
        "description": "Bărcuța este luată de un val chiar înainte de margine. Burețel sare în apă și își folosește superputerea.\n\nAnimație originală din universul Lucreția.\n#animatie #pentrucopii #aventura #shorts",
        "notes": [62, 65, 69, 74],
        "events": [(3.0, "water"), (6.5, "absorb"), (9.2, "win")],
    },
]


def midi_hz(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def envelope(length: int, attack: float = 0.02, release: float = 0.08) -> np.ndarray:
    values = np.ones(length, dtype=np.float32)
    a = min(length, int(SAMPLE_RATE * attack))
    r = min(length, int(SAMPLE_RATE * release))
    if a:
        values[:a] = np.linspace(0, 1, a, dtype=np.float32)
    if r:
        values[-r:] = np.linspace(1, 0, r, dtype=np.float32)
    return values


def add_tone(track: np.ndarray, start: float, duration: float, frequency: float, volume: float, *, glide: float = 0.0) -> None:
    begin = int(start * SAMPLE_RATE)
    length = min(int(duration * SAMPLE_RATE), len(track) - begin)
    if length <= 0:
        return
    t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
    phase = 2 * math.pi * (frequency * t + 0.5 * glide * t * t)
    tone = (np.sin(phase) + 0.25 * np.sin(2 * phase)) * envelope(length)
    track[begin : begin + length] += tone.astype(np.float32) * volume


def add_noise(track: np.ndarray, start: float, duration: float, volume: float, seed: int) -> None:
    begin = int(start * SAMPLE_RATE)
    length = min(int(duration * SAMPLE_RATE), len(track) - begin)
    if length <= 0:
        return
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, length).astype(np.float32)
    kernel = np.ones(180, dtype=np.float32) / 180
    softened = np.convolve(noise, kernel, mode="same")
    track[begin : begin + length] += softened * envelope(length, 0.03, 0.15) * volume


def soundtrack(duration: float, spec: dict, index: int) -> np.ndarray:
    track = np.zeros(int(duration * SAMPLE_RATE), dtype=np.float32)
    beat = 0.38
    for count, start in enumerate(np.arange(0, duration, beat)):
        note = spec["notes"][count % len(spec["notes"])]
        add_tone(track, float(start), 0.22, midi_hz(note), 0.055)
    for when, kind in spec["events"]:
        if kind in {"danger", "wind", "water"}:
            add_noise(track, when, 1.25, 0.8, 100 + index)
            add_tone(track, when, 0.8, 180, 0.12, glide=-90)
        elif kind in {"impact", "pull", "absorb"}:
            add_tone(track, when, 0.28, 110, 0.22, glide=-180)
            add_noise(track, when, 0.35, 0.7, 200 + index)
        elif kind == "win":
            for offset, note in enumerate(spec["notes"][-3:]):
                add_tone(track, when + offset * 0.12, 0.42, midi_hz(note + 12), 0.11)
    peak = max(1.0, float(np.max(np.abs(track))) / 0.88)
    return np.clip(track / peak, -1, 1)


def write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (samples * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def probe_duration(ffmpeg: str, video: Path) -> float:
    completed = subprocess.run([ffmpeg, "-i", str(video)], capture_output=True, text=True)
    import re
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", completed.stderr)
    if not match:
        raise RuntimeError(f"Cannot read duration: {video}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    manifest = load_manifest(root)
    output_dir = root / "data" / "generated" / "productions" / BATCH_NAME / "upload_ready"
    audio_dir = output_dir / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    package = []
    for index, (production_id, spec) in enumerate(zip(manifest["production_ids"], UPLOAD), start=1):
        production = get_production(root, production_id)
        source = root / production["final_output"]
        subtitles = root / production["subtitle_output"]
        duration = probe_duration(ffmpeg, source)
        audio = audio_dir / f"reel_{index:02d}_original_soundtrack.wav"
        write_wav(audio, soundtrack(duration, spec, index))
        output = output_dir / spec["filename"]
        subtitle_relative = subtitles.relative_to(root).as_posix()
        subtitle_filter = (
            f"subtitles='{subtitle_relative}':"
            "force_style='FontName=Arial,FontSize=15,Bold=1,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00101010,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=72'"
        )
        subprocess.run(
            [ffmpeg, "-y", "-i", str(source), "-i", str(audio), "-vf", subtitle_filter,
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(output)],
            check=True, capture_output=True, cwd=root,
        )
        package.append({"reel": index, "production_id": production_id, "file": str(output.relative_to(root)).replace("\\", "/"), "title": spec["title"], "description": spec["description"], "duration_seconds": duration})
    metadata = output_dir / "youtube_upload_metadata.json"
    metadata.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "reels": package}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
