from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lucretia_runtime.local_video_builder import build_local_videos_from_dir


def run_test():
    out = ROOT / "data" / "generated" / "test_videos"
    paths = build_local_videos_from_dir(ROOT / "data" / "generated" / "assembly", out, project_root=ROOT, fps=6, width=360, height=640)
    assert paths
    assert paths[0].exists()
    assert paths[0].suffix == ".mp4"
    summary = json.loads((out / "local_video_builder_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "built"
    assert summary["segment_count"] >= 1
    print("OK — Local Video Builder test passed.")


if __name__ == "__main__":
    run_test()
