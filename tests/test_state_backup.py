from __future__ import annotations

from pathlib import Path

from lucretia_runtime.autonomous_production import create_original_reel
from lucretia_runtime.comfy.job_store import save_jobs
from lucretia_runtime.production import load_productions
from lucretia_runtime.state_backup import export_relay_state, restore_relay_state


def test_safe_relay_snapshot_round_trips_state_and_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    production = create_original_reel(source)
    video = source / "data" / "generated" / "videos" / "finished.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video-result")
    subtitle = source / "data" / "generated" / "subtitles" / "finished.srt"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nSalut!\n", encoding="utf-8")
    save_jobs(source, [{"job_id": "DONE", "status": "built"}])

    snapshot = export_relay_state(source)
    result = restore_relay_state(target, snapshot)

    assert snapshot["safe"] is True
    assert result["restored"] is True
    assert load_productions(target)[0]["production_id"] == production["production_id"]
    assert target.joinpath("data/generated/videos/finished.mp4").read_bytes() == b"video-result"
    assert "Salut" in target.joinpath("data/generated/subtitles/finished.srt").read_text(encoding="utf-8")
    assert len(list(target.joinpath("data/generated/short_assets").glob("*.png"))) == 1


def test_relay_restore_never_overwrites_existing_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    original = create_original_reel(source)
    existing = create_original_reel(target)

    result = restore_relay_state(target, export_relay_state(source))

    assert result == {"restored": False, "reason": "server state is not empty"}
    assert load_productions(target)[0]["production_id"] == existing["production_id"]
    assert load_productions(target)[0]["production_id"] != original["production_id"]


def test_active_production_is_not_exported_with_artifacts_or_restored(tmp_path: Path) -> None:
    source = tmp_path / "source"
    production = create_original_reel(source)
    production["automation"]["running"] = True
    from lucretia_runtime.production import save_production

    save_production(source, production)

    snapshot = export_relay_state(source)

    assert snapshot["safe"] is False
    assert snapshot["files"] == []
    try:
        restore_relay_state(tmp_path / "target", snapshot)
        raise AssertionError("active snapshot was restored")
    except ValueError as exc:
        assert "Active production" in str(exc)
