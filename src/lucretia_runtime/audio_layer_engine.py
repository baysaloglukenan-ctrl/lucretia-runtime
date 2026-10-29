from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def create_silent_audio_wav(path: Path, duration_seconds: float, sample_rate: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(duration_seconds * sample_rate)
    with wave.open(str(path), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(total_samples):
            amp = 0
            if i % sample_rate < 600:
                amp = int(600 * math.sin(2 * math.pi * 440 * i / sample_rate))
            wav.writeframes(struct.pack("<h", amp))
    return path
