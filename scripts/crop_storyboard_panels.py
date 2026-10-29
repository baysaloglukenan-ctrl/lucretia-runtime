from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def content_runs(image: Image.Image) -> list[tuple[int, int]]:
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    # A storyboard gutter is nearly white for almost the entire column.
    non_white = np.mean(np.any(pixels < 245, axis=2), axis=0) > 0.08
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, active in enumerate(non_white.tolist() + [False]):
        if active and start is None:
            start = index
        elif not active and start is not None:
            if index - start > image.width * 0.2:
                runs.append((start, index))
            start = None
    return runs


def crop_sheet(source: Path, output_dir: Path) -> list[Path]:
    image = Image.open(source).convert("RGB")
    runs = content_runs(image)
    if len(runs) != 3:
        raise RuntimeError(f"Expected exactly three panels in {source}, found {runs}")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for number, (left, right) in enumerate(runs, start=1):
        panel = image.crop((left, 0, right, image.height))
        output = output_dir / f"{source.stem}_scene_{number:02d}.png"
        panel.save(output, optimize=True)
        outputs.append(output)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    for source in args.sources:
        for output in crop_sheet(source, args.output_dir):
            print(output)


if __name__ == "__main__":
    main()
