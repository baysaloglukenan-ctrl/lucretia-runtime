from __future__ import annotations

import json
from pathlib import Path

from lucretia_runtime.comfy.workflow_patch import (
    normalize_ltx_frames,
    patch_ids_from_env,
    patch_workflow_with_report,
    strip_generated_audio,
    strip_ltx23_audio,
    strip_minimax_h3_audio,
    validate_workflow,
)


def _incomplete_t2i_video_wrapper() -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "model.safetensors"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive", "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality, blurry", "clip": ["2", 0]}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "CreateVideo", "inputs": {"fps": 24, "images": ["8", 0]}},
        "10": {"class_type": "SaveVideo", "inputs": {"video": ["9", 0]}},
    }


def _complete_i2v_workflow() -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": "source.png"}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "model.safetensors"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive", "clip": ["3", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality, blurry", "clip": ["3", 0]}},
        "7": {
            "class_type": "ImageToVideoConditioning",
            "inputs": {"image": ["1", 0], "vae": ["4", 0], "width": 720, "height": 1280, "num_frames": 60},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "model": ["2", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0],
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"fps": 24, "images": ["9", 0]}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0]}},
    }


def test_incomplete_workflow_is_blocked_before_submission() -> None:
    report = validate_workflow(_incomplete_t2i_video_wrapper(), require_i2v=True)
    assert report["valid"] is False
    assert report["connections"]["image_to_sampler"] is False
    assert any("image_input" in error for error in report["errors"])
    assert any("frame_control" in error for error in report["errors"])
    assert any("batch_size" in warning for warning in report["warnings"])


def test_batch_size_is_not_patched_as_frames() -> None:
    _, patch_report = patch_workflow_with_report(
        _incomplete_t2i_video_wrapper(),
        image_name="source.png",
        prompt="ball rolling",
        negative_prompt="duplicate ball",
        seed=7,
        frames=60,
        width=720,
        height=1280,
        strict=False,
    )
    assert "frames" not in patch_report["patched_fields"]
    assert patch_report["resolved_nodes"]["frames"] is None


def test_complete_i2v_workflow_validates_and_patches_all_controls() -> None:
    workflow = _complete_i2v_workflow()
    validation = validate_workflow(workflow, require_i2v=True)
    assert validation["valid"] is True
    assert validation["workflow_type"] == "i2v"

    patched, patch_report = patch_workflow_with_report(
        workflow,
        image_name="lucretia/source.png",
        prompt="A metal ball rolls down a grassy hill.",
        negative_prompt="duplicate ball, floating",
        seed=12345,
        frames=60,
        width=720,
        height=1280,
        strict=True,
    )
    assert set(("image", "positive_prompt", "negative_prompt", "seed", "frames", "width", "height")).issubset(
        patch_report["patched_fields"]
    )
    assert patched["1"]["inputs"]["image"] == "lucretia/source.png"
    assert patched["7"]["inputs"]["num_frames"] == 60
    assert patched["7"]["inputs"]["width"] == 720
    assert patched["7"]["inputs"]["height"] == 1280


def test_default_node_ids_cannot_collide_with_real_workflow_nodes(monkeypatch) -> None:
    for name in (
        "LUCRETIA_COMFY_IMAGE_NODE_ID",
        "LUCRETIA_COMFY_PROMPT_NODE_ID",
        "LUCRETIA_COMFY_NEGATIVE_NODE_ID",
        "LUCRETIA_COMFY_SEED_NODE_ID",
        "LUCRETIA_COMFY_FRAMES_NODE_ID",
        "LUCRETIA_COMFY_WIDTH_NODE_ID",
        "LUCRETIA_COMFY_HEIGHT_NODE_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    workflow = _complete_i2v_workflow()
    patched, report = patch_workflow_with_report(
        workflow,
        image_name="lucretia/source.png",
        prompt="A metal ball rolls down a grassy hill.",
        negative_prompt="duplicate ball",
        seed=9,
        frames=60,
        width=720,
        height=1280,
        strict=True,
        **patch_ids_from_env(),
    )
    assert report["resolved_nodes"]["image"] == "1"
    assert patched["1"]["inputs"]["image"] == "lucretia/source.png"
    assert "image" not in patched["10"]["inputs"]


def test_ltx23_workflow_validates_and_patches_synchronized_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = json.loads((root / "workflows" / "comfy" / "ltx23_i2v_api.json").read_text(encoding="utf-8"))

    validation = validate_workflow(workflow, require_i2v=True)
    assert validation["valid"] is True
    assert validation["workflow_type"] == "i2v"

    patched, report = patch_workflow_with_report(
        workflow,
        image_name="lucretia/ball.png",
        prompt="a single shiny metal ball rolling down a grassy hill",
        negative_prompt="multiple balls, blurry",
        seed=12345,
        frames=10,
        width=512,
        height=320,
        strict=True,
    )

    assert report["workflow_profile"] == "ltx-2.3-i2v"
    assert report["requested_frames"] == 10
    assert report["effective_frames"] == 9
    assert patched["269"]["inputs"]["image"] == "lucretia/ball.png"
    assert patched["320:319"]["inputs"]["value"].startswith("a single shiny metal ball")
    assert patched["320:313"]["inputs"]["text"] == "multiple balls, blurry"
    assert patched["320:295"]["inputs"]["length"] == 9
    assert patched["320:305"]["inputs"]["frames_number"] == 9
    assert patched["320:312"]["inputs"]["value"] == 512
    assert patched["320:299"]["inputs"]["value"] == 320
    assert patched["320:276"]["inputs"]["noise_seed"] == 12345
    assert patched["320:277"]["inputs"]["noise_seed"] == 12346


def test_ltx_frame_normalization() -> None:
    assert normalize_ltx_frames(1) == 9
    assert normalize_ltx_frames(9) == 9
    assert normalize_ltx_frames(10) == 9
    assert normalize_ltx_frames(17) == 17
    assert normalize_ltx_frames(60) == 57


def test_ltx23_audio_can_be_removed_without_breaking_video_path() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = json.loads((root / "workflows" / "comfy" / "ltx23_i2v_api.json").read_text(encoding="utf-8"))
    silent, report = strip_ltx23_audio(workflow)

    assert report["audio_enabled"] is False
    assert validate_workflow(silent, require_i2v=True)["valid"] is True
    assert not any(
        node.get("class_type") in {
            "LTXVAudioVAELoader",
            "LTXVAudioVAEDecode",
            "LTXVEmptyLatentAudio",
            "LTXVConcatAVLatent",
            "LTXVSeparateAVLatent",
        }
        for node in silent.values()
    )
    assert "audio" not in silent["320:310"]["inputs"]
    assert silent["320:283"]["inputs"]["latent_image"] == ["320:296", 0]
    assert silent["320:287"]["inputs"]["samples"] == ["320:283", 0]
    assert silent["320:308"]["inputs"]["latent_image"] == ["320:288", 0]
    assert silent["320:315"]["inputs"]["samples"] == ["320:308", 0]


def test_minimax_h3_workflow_is_silent_and_anchors_both_ends() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = json.loads(
        (root / "workflows" / "comfy" / "minimax_h3_r2v_api.json").read_text(encoding="utf-8")
    )

    silent, report = strip_minimax_h3_audio(workflow)

    assert report["audio_enabled"] is False
    assert report["internal_av_latent_required_by_model"] is True
    assert "audio" not in silent["130"]["inputs"]
    assert silent["136"]["inputs"]["audio_vae"] == silent["136"]["inputs"]["vae"]
    assert not any(node.get("class_type") == "VAEDecodeAudio" for node in silent.values())
    assert not any(
        node.get("class_type") == "VAELoader"
        and "audio" in str(node.get("inputs", {}).get("vae_name", "")).lower()
        for node in silent.values()
    )
    assert silent["146"]["class_type"] == "MiniMaxH3AddGuide"
    assert silent["146"]["inputs"]["frame_idx"] == 0
    assert silent["146"]["inputs"]["image"] == ["137", 0]
    assert silent["147"]["class_type"] == "MiniMaxH3AddGuide"
    assert silent["147"]["inputs"]["frame_idx"] == -1
    assert silent["147"]["inputs"]["image"] == ["139", 0]
    assert silent["126"]["inputs"]["conditioning"] == ["147", 0]
    assert validate_workflow(silent, require_i2v=True)["valid"] is True


def test_silent_policy_dispatches_to_minimax_h3() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = json.loads(
        (root / "workflows" / "comfy" / "minimax_h3_r2v_api.json").read_text(encoding="utf-8")
    )

    silent, report = strip_generated_audio(workflow)

    assert report["profile"] == "minimax-h3-video-output-only"
    assert report["audio_enabled"] is False
    assert "audio" not in silent["130"]["inputs"]
