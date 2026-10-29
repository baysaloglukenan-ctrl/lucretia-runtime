from __future__ import annotations

import copy
import json
import os
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


REQUIRED_I2V_ROLES = (
    "model_loader",
    "clip_loader",
    "vae_loader",
    "image_input",
    "positive_prompt",
    "negative_prompt",
    "image_conditioning",
    "sampler",
    "decoder",
    "video_builder",
    "video_saver",
    "frame_control",
)


class WorkflowValidationError(ValueError):
    def __init__(self, report: dict) -> None:
        self.report = report
        errors = report.get("errors") or ["Unknown workflow validation error"]
        super().__init__("Workflow validation failed: " + "; ".join(str(item) for item in errors))


def load_workflow(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"ComfyUI workflow API JSON not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"ComfyUI workflow must be a JSON object: {path}")
    return payload


def _node(workflow: dict, node_id: str | None) -> dict | None:
    if not node_id:
        return None
    node = workflow.get(str(node_id))
    return node if isinstance(node, dict) else None


def _node_name(node: dict) -> str:
    class_type = str(node.get("class_type", ""))
    meta = node.get("_meta")
    title = str(meta.get("title", "")) if isinstance(meta, dict) else ""
    return f"{class_type} {title}".strip().lower()


def _node_title(node: dict) -> str:
    meta = node.get("_meta")
    return str(meta.get("title", "")).strip().lower() if isinstance(meta, dict) else ""


def _set_input(
    workflow: dict,
    node_id: str | None,
    input_name: str,
    value: Any,
    *,
    strict: bool = False,
    patches: list[dict] | None = None,
    logical_field: str = "",
) -> bool:
    if not node_id:
        if strict:
            raise KeyError(f"No workflow node resolved for {logical_field or input_name}")
        return False
    node = _node(workflow, node_id)
    if node is None:
        if strict:
            raise KeyError(f"Workflow node id not found: {node_id}")
        return False
    inputs = node.setdefault("inputs", {})
    if not isinstance(inputs, dict):
        if strict:
            raise TypeError(f"Workflow node {node_id} has invalid inputs")
        return False
    previous = inputs.get(input_name)
    inputs[input_name] = value
    if patches is not None:
        patches.append(
            {
                "field": logical_field or input_name,
                "node_id": str(node_id),
                "class_type": str(node.get("class_type", "")),
                "input_name": input_name,
                "previous": previous,
                "value": value,
            }
        )
    return True


def _input_keys(node: dict) -> set[str]:
    inputs = node.get("inputs", {})
    return set(inputs.keys()) if isinstance(inputs, dict) else set()


def _text_value(node: dict) -> str:
    inputs = node.get("inputs", {})
    if not isinstance(inputs, dict):
        return ""
    return str(inputs.get("text", ""))


def _looks_negative(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "low quality",
        "bad anatomy",
        "extra limbs",
        "missing limbs",
        "deformed",
        "worst quality",
        "blurry",
        "duplicate",
        "artifact",
    ]
    return any(marker in lowered for marker in markers)


def _find_first_node_with_input(workflow: dict, names: set[str]) -> str | None:
    for node_id, node in workflow.items():
        if isinstance(node, dict) and _input_keys(node).intersection(names):
            return str(node_id)
    return None


def _find_image_node(workflow: dict) -> str | None:
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        name = _node_name(node)
        keys = _input_keys(node)
        if str(node.get("class_type", "")).lower() == "loadimage" or "load image" in name:
            return str(node_id)
        if "image" in keys and "load" in name:
            return str(node_id)
    return None


def _find_prompt_nodes(workflow: dict) -> tuple[str | None, str | None]:
    positive = None
    negative = None
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if "prompt" in _node_title(node) and _input_keys(node).intersection({"value", "text"}):
            positive = str(node_id)
            break
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        name = _node_name(node)
        if "textencode" not in name and "text encode" not in name:
            continue
        text = _text_value(node)
        if _looks_negative(text) or "negative" in name:
            negative = negative or str(node_id)
        else:
            positive = positive or str(node_id)
    return positive, negative


def _find_titled_value_node(workflow: dict, title: str) -> str | None:
    wanted = title.strip().lower()
    for node_id, node in workflow.items():
        if isinstance(node, dict) and _node_title(node) == wanted and "value" in _input_keys(node):
            return str(node_id)
    return None


def is_ltx23_workflow(workflow: dict) -> bool:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if "ltx-2.3" in json.dumps(node.get("inputs", {}), ensure_ascii=False).lower():
            return True
    return False


def normalize_ltx_frames(frames: int) -> int:
    """Return the largest valid LTX frame count (8n+1) not above the request."""
    requested = max(1, int(frames))
    if requested <= 9:
        return 9
    return ((requested - 1) // 8) * 8 + 1


def strip_ltx23_audio(workflow: dict) -> tuple[dict, dict]:
    """Convert the verified LTX-2.3 AV workflow into a silent video-only graph."""
    graph = copy.deepcopy(workflow)
    required = {
        "320:283": "SamplerCustomAdvanced",
        "320:284": "LTXVCropGuides",
        "320:287": "LTXVLatentUpsampler",
        "320:288": "LTXVImgToVideoInplace",
        "320:296": "LTXVImgToVideoInplace",
        "320:308": "SamplerCustomAdvanced",
        "320:310": "CreateVideo",
        "320:315": "VAEDecodeTiled",
    }
    for node_id, class_type in required.items():
        node = graph.get(node_id)
        if not isinstance(node, dict) or node.get("class_type") != class_type:
            raise WorkflowValidationError(
                {"valid": False, "errors": [f"LTX video-only conversion requires node {node_id} ({class_type})."]}
            )

    graph["320:283"]["inputs"]["latent_image"] = ["320:296", 0]
    graph["320:284"]["inputs"]["latent"] = ["320:283", 0]
    graph["320:287"]["inputs"]["samples"] = ["320:283", 0]
    graph["320:308"]["inputs"]["latent_image"] = ["320:288", 0]
    graph["320:315"]["inputs"]["samples"] = ["320:308", 0]
    graph["320:310"]["inputs"].pop("audio", None)

    audio_types = {
        "LTXVAudioVAELoader",
        "LTXVAudioVAEDecode",
        "LTXVEmptyLatentAudio",
        "LTXVConcatAVLatent",
        "LTXVSeparateAVLatent",
    }
    removed = []
    for node_id in list(graph):
        if graph[node_id].get("class_type") in audio_types:
            removed.append(node_id)
            del graph[node_id]
    return graph, {
        "profile": "ltx-2.3-i2v-video-only",
        "audio_enabled": False,
        "removed_nodes": sorted(removed),
        "rewired_nodes": ["320:283", "320:284", "320:287", "320:308", "320:310", "320:315"],
    }


def strip_minimax_h3_audio(workflow: dict) -> tuple[dict, dict]:
    """Keep H3's required AV latent internal while producing a silent MP4."""
    graph = copy.deepcopy(workflow)
    h3_nodes = [
        node_id
        for node_id, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") == "MiniMaxH3ReferenceToVideo"
    ]
    if not h3_nodes:
        raise WorkflowValidationError(
            {"valid": False, "errors": ["MiniMax H3 silent conversion requires MiniMaxH3ReferenceToVideo."]}
        )

    rewired = []
    for node_id in h3_nodes:
        inputs = graph[node_id].setdefault("inputs", {})
        if "vae" not in inputs:
            raise WorkflowValidationError(
                {"valid": False, "errors": [f"MiniMax H3 node {node_id} has no video VAE input."]}
            )
        inputs["audio_vae"] = copy.deepcopy(inputs["vae"])
        for key in list(inputs):
            if key.startswith("ref_audios.") or key.startswith("ref_video_audios."):
                del inputs[key]
        rewired.append(node_id)

    for node_id, node in graph.items():
        if isinstance(node, dict) and node.get("class_type") == "CreateVideo":
            node.setdefault("inputs", {}).pop("audio", None)
            rewired.append(node_id)

    removed = []
    for node_id in list(graph):
        node = graph[node_id]
        class_type = str(node.get("class_type", ""))
        vae_name = str(node.get("inputs", {}).get("vae_name", "")).lower()
        if class_type == "VAEDecodeAudio" or (class_type == "VAELoader" and "audio" in vae_name):
            removed.append(node_id)
            del graph[node_id]

    return graph, {
        "profile": "minimax-h3-video-output-only",
        "audio_enabled": False,
        "internal_av_latent_required_by_model": True,
        "removed_nodes": sorted(removed),
        "rewired_nodes": sorted(set(rewired)),
    }


def strip_generated_audio(workflow: dict) -> tuple[dict, dict]:
    """Enforce Lucreția's silent-generation policy for supported video models."""
    class_types = {
        node.get("class_type")
        for node in workflow.values()
        if isinstance(node, dict)
    }
    if "MiniMaxH3ReferenceToVideo" in class_types:
        return strip_minimax_h3_audio(workflow)
    if is_ltx23_workflow(workflow):
        return strip_ltx23_audio(workflow)

    graph = copy.deepcopy(workflow)
    changed = []
    for node_id, node in graph.items():
        if isinstance(node, dict) and node.get("class_type") == "CreateVideo":
            if "audio" in node.setdefault("inputs", {}):
                node["inputs"].pop("audio", None)
                changed.append(node_id)
    return graph, {
        "profile": "generic-silent-video-output",
        "audio_enabled": False,
        "removed_nodes": [],
        "rewired_nodes": changed,
    }


def _ltx_frame_targets(workflow: dict) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", "")).lower()
        keys = _input_keys(node)
        if class_type in {"emptyltxvlatentvideo", "ltxvimgtovideo"} and "length" in keys:
            targets.append((str(node_id), "length"))
        elif class_type == "ltxvemptylatentaudio" and "frames_number" in keys:
            targets.append((str(node_id), "frames_number"))
    return targets


def _find_size_node(workflow: dict) -> str | None:
    preferred = []
    fallback = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        keys = _input_keys(node)
        if "width" not in keys or "height" not in keys:
            continue
        name = _node_name(node)
        if any(marker in name for marker in ("video", "i2v", "image to video", "conditioning", "wan", "ltx", "svd")):
            preferred.append(str(node_id))
        else:
            fallback.append(str(node_id))
    return (preferred or fallback or [None])[0]


def _is_video_context(node: dict) -> bool:
    name = _node_name(node)
    return any(marker in name for marker in ("video", "i2v", "image to video", "wan", "ltx", "svd", "animatediff", "temporal"))


def _find_frames_node(workflow: dict) -> tuple[str | None, str]:
    # Never treat a generic T2I EmptyLatent batch_size as video frames.
    # That was the cause of the 60-frame smoke test rendering 60 independent 1024px images.
    strong_candidates = ["frames", "frame_count", "num_frames", "video_frames", "length"]
    for input_name in strong_candidates:
        for node_id, node in workflow.items():
            if isinstance(node, dict) and input_name in _input_keys(node):
                return str(node_id), input_name
    for node_id, node in workflow.items():
        if isinstance(node, dict) and "batch_size" in _input_keys(node) and _is_video_context(node):
            return str(node_id), "batch_size"
    return None, "value"


def _connections(workflow: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for target_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and len(value) >= 2 and str(value[0]) in workflow:
                source_id = str(value[0])
                target = str(target_id)
                forward[source_id].add(target)
                reverse[target].add(source_id)
    return forward, reverse


def _reachable(graph: dict[str, set[str]], source: str | None, target: str | None) -> bool:
    if not source or not target:
        return False
    if source == target:
        return True
    queue: deque[str] = deque([source])
    visited = {source}
    while queue:
        current = queue.popleft()
        for neighbour in graph.get(current, set()):
            if neighbour == target:
                return True
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return False


def _role_nodes(workflow: dict) -> dict[str, str | None]:
    roles: dict[str, str | None] = {role: None for role in REQUIRED_I2V_ROLES}
    roles["image_input"] = _find_image_node(workflow)
    roles["positive_prompt"], roles["negative_prompt"] = _find_prompt_nodes(workflow)
    roles["frame_control"], _ = _find_frames_node(workflow)

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        name = _node_name(node)
        class_type = str(node.get("class_type", "")).lower()
        node_id = str(node_id)
        if roles["model_loader"] is None and (
            "unetloader" in class_type
            or "checkpointloader" in class_type
            or "diffusionmodelload" in name
            or ("model" in name and "loader" in name and "sampling" not in name)
        ):
            roles["model_loader"] = node_id
        if roles["clip_loader"] is None and (
            ("clip" in name and "load" in name) or "textencoderloader" in class_type
        ):
            roles["clip_loader"] = node_id
        if roles["vae_loader"] is None and (
            ("vae" in name and "load" in name) or "checkpointloader" in class_type
        ):
            roles["vae_loader"] = node_id
        if roles["sampler"] is None and (
            ("ksampler" in class_type and "select" not in class_type)
            or "samplercustom" in class_type
        ):
            roles["sampler"] = node_id
        if roles["decoder"] is None and (
            ("vaedecode" in class_type and "audio" not in class_type)
            or ("decode" in name and "vae" in name and "audio" not in name)
        ):
            roles["decoder"] = node_id
        if roles["video_builder"] is None and ("createvideo" in class_type or "create video" in name or "video combine" in name):
            roles["video_builder"] = node_id
        if roles["video_saver"] is None and ("savevideo" in class_type or "save video" in name):
            roles["video_saver"] = node_id
        if roles["image_conditioning"] is None and any(
            marker in name
            for marker in (
                "image to video",
                "imagetovideo",
                "imgtovideo",
                "i2v",
                "image conditioning",
                "vae encode",
                "vaeencode",
                "svd conditioning",
                "wan image",
                "ltx image",
                "reference to video",
                "referencetovideo",
                "add guide for minimax",
                "minimaxh3addguide",
            )
        ):
            roles["image_conditioning"] = node_id
    return roles


def validate_workflow(workflow: dict, *, require_i2v: bool = True) -> dict:
    roles = _role_nodes(workflow)
    forward, _reverse = _connections(workflow)
    errors: list[str] = []
    warnings: list[str] = []
    class_types = {
        node.get("class_type")
        for node in workflow.values()
        if isinstance(node, dict)
    }
    is_minimax_h3 = "MiniMaxH3ReferenceToVideo" in class_types

    required = list(REQUIRED_I2V_ROLES if require_i2v else ())
    if is_minimax_h3:
        # H3 uses one multimodal prompt and has no separate negative-conditioning node.
        required.remove("negative_prompt")
    for role in required:
        if not roles.get(role):
            errors.append(f"Missing logical block: {role}")

    image_to_sampler = _reachable(forward, roles.get("image_input"), roles.get("sampler"))
    sampler_to_decoder = _reachable(forward, roles.get("sampler"), roles.get("decoder"))
    decoder_to_video = _reachable(forward, roles.get("decoder"), roles.get("video_builder"))
    video_to_save = _reachable(forward, roles.get("video_builder"), roles.get("video_saver"))

    if require_i2v and roles.get("image_input") and roles.get("sampler") and not image_to_sampler:
        errors.append("The source image is not connected to the sampling path; this is not a real I2V graph.")
    if roles.get("sampler") and roles.get("decoder") and not sampler_to_decoder:
        errors.append("Sampler output is not connected to the decoder.")
    if roles.get("decoder") and roles.get("video_builder") and not decoder_to_video:
        errors.append("Decoded frames are not connected to the video builder.")
    if roles.get("video_builder") and roles.get("video_saver") and not video_to_save:
        errors.append("Video builder output is not connected to the video saver.")

    generic_empty_latents = []
    for node_id, node in workflow.items():
        if isinstance(node, dict) and "empty" in _node_name(node) and "latent" in _node_name(node):
            generic_empty_latents.append(str(node_id))
    if require_i2v and generic_empty_latents and not image_to_sampler:
        warnings.append(
            "Generic empty latent detected without image conditioning. Do not map batch_size to frames; it creates independent images."
        )

    workflow_type = "i2v" if image_to_sampler else "non_i2v_or_incomplete"
    return {
        "valid": not errors,
        "require_i2v": require_i2v,
        "workflow_type": workflow_type,
        "node_count": len([node for node in workflow.values() if isinstance(node, dict)]),
        "roles": roles,
        "connections": {
            "image_to_sampler": image_to_sampler,
            "sampler_to_decoder": sampler_to_decoder,
            "decoder_to_video": decoder_to_video,
            "video_to_save": video_to_save,
        },
        "errors": errors,
        "warnings": warnings,
        "generic_empty_latent_nodes": generic_empty_latents,
    }


def patch_workflow_with_report(
    workflow: dict,
    *,
    image_name: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
    frames: int,
    width: int | None = None,
    height: int | None = None,
    image_node_id: str | None = None,
    image_input_name: str = "image",
    prompt_node_id: str | None = None,
    prompt_input_name: str = "text",
    negative_prompt_node_id: str | None = None,
    negative_prompt_input_name: str = "text",
    seed_node_id: str | None = None,
    seed_input_name: str = "seed",
    frames_node_id: str | None = None,
    frames_input_name: str = "value",
    width_node_id: str | None = None,
    width_input_name: str = "value",
    height_node_id: str | None = None,
    height_input_name: str = "value",
    strict: bool = False,
) -> tuple[dict, dict]:
    patched = json.loads(json.dumps(workflow))
    patches: list[dict] = []
    ltx23 = is_ltx23_workflow(patched)

    image_node_id = image_node_id if _node(patched, image_node_id) else _find_image_node(patched)
    detected_positive, detected_negative = _find_prompt_nodes(patched)
    prompt_node_id = prompt_node_id if _node(patched, prompt_node_id) else detected_positive
    negative_prompt_node_id = negative_prompt_node_id if _node(patched, negative_prompt_node_id) else detected_negative
    if ltx23 and _node_title(_node(patched, prompt_node_id) or {}) == "prompt":
        prompt_input_name = "value"
    seed_node_id = seed_node_id if _node(patched, seed_node_id) else _find_first_node_with_input(
        patched, {seed_input_name, "seed", "noise_seed"}
    )

    detected_frames_node, detected_frames_input = _find_frames_node(patched)
    if not _node(patched, frames_node_id):
        frames_node_id = detected_frames_node
        frames_input_name = detected_frames_input

    size_node = _find_size_node(patched)
    detected_width_node = _find_titled_value_node(patched, "Width") if ltx23 else size_node
    detected_height_node = _find_titled_value_node(patched, "Height") if ltx23 else size_node
    width_node_id = width_node_id if _node(patched, width_node_id) else detected_width_node
    height_node_id = height_node_id if _node(patched, height_node_id) else detected_height_node
    if width_node_id == height_node_id and size_node:
        width_input_name = "width"
        height_input_name = "height"

    _set_input(patched, image_node_id, image_input_name, image_name, strict=strict, patches=patches, logical_field="image")
    _set_input(patched, prompt_node_id, prompt_input_name, prompt, strict=strict, patches=patches, logical_field="positive_prompt")
    _set_input(
        patched,
        negative_prompt_node_id,
        negative_prompt_input_name,
        negative_prompt,
        strict=strict,
        patches=patches,
        logical_field="negative_prompt",
    )
    effective_frames = int(frames)
    frame_targets: list[tuple[str, str]] = []
    seed_targets: list[str] = []
    if ltx23:
        effective_frames = normalize_ltx_frames(frames)
        frame_targets = _ltx_frame_targets(patched)
        if strict and not frame_targets:
            raise KeyError("No synchronized LTX video/audio frame controls found")
        for target_id, target_input in frame_targets:
            _set_input(
                patched,
                target_id,
                target_input,
                effective_frames,
                strict=strict,
                patches=patches,
                logical_field="frames",
            )
        for node_id, node in patched.items():
            if isinstance(node, dict) and "noise_seed" in _input_keys(node):
                seed_targets.append(str(node_id))
        if strict and not seed_targets:
            raise KeyError("No LTX noise seed controls found")
        for offset, target_id in enumerate(seed_targets):
            _set_input(
                patched,
                target_id,
                "noise_seed",
                int(seed) + offset,
                strict=strict,
                patches=patches,
                logical_field="seed",
            )
    else:
        _set_input(patched, seed_node_id, seed_input_name, int(seed), strict=strict, patches=patches, logical_field="seed")
        _set_input(
            patched,
            frames_node_id,
            frames_input_name,
            effective_frames,
            strict=strict,
            patches=patches,
            logical_field="frames",
        )
    if width is not None:
        _set_input(patched, width_node_id, width_input_name, int(width), strict=strict, patches=patches, logical_field="width")
    if height is not None:
        _set_input(patched, height_node_id, height_input_name, int(height), strict=strict, patches=patches, logical_field="height")

    report = {
        "workflow_profile": "ltx-2.3-i2v" if ltx23 else "generic-i2v",
        "requested_frames": int(frames),
        "effective_frames": effective_frames,
        "patched": patches,
        "patched_fields": [item["field"] for item in patches],
        "resolved_nodes": {
            "image": image_node_id,
            "positive_prompt": prompt_node_id,
            "negative_prompt": negative_prompt_node_id,
            "seed": seed_node_id,
            "frames": frames_node_id,
            "width": width_node_id,
            "height": height_node_id,
            "frame_targets": [{"node_id": node_id, "input_name": input_name} for node_id, input_name in frame_targets],
            "seed_targets": seed_targets,
        },
        "unresolved_fields": [
            field
            for field, node_id in {
                "image": image_node_id,
                "positive_prompt": prompt_node_id,
                "negative_prompt": negative_prompt_node_id,
                "seed": seed_node_id,
                "frames": frames_node_id,
                "width": width_node_id if width is not None else "not_requested",
                "height": height_node_id if height is not None else "not_requested",
            }.items()
            if node_id is None
        ],
    }
    return patched, report


def patch_workflow(workflow: dict, **kwargs: Any) -> dict:
    patched, _report = patch_workflow_with_report(workflow, **kwargs)
    return patched


def patch_ids_from_env(prefix: str = "LUCRETIA_COMFY") -> dict:
    """Return optional node ids/input names for workflow patching.

    Node IDs are used only when explicitly configured. Otherwise Lucreția
    resolves the logical roles from the workflow graph. Frame auto-detection is
    intentionally conservative and will not map a generic EmptyLatent
    ``batch_size`` to video frames.
    """
    return {
        "image_node_id": os.environ.get(f"{prefix}_IMAGE_NODE_ID"),
        "image_input_name": os.environ.get(f"{prefix}_IMAGE_INPUT", "image"),
        "prompt_node_id": os.environ.get(f"{prefix}_PROMPT_NODE_ID"),
        "prompt_input_name": os.environ.get(f"{prefix}_PROMPT_INPUT", "text"),
        "negative_prompt_node_id": os.environ.get(f"{prefix}_NEGATIVE_NODE_ID"),
        "negative_prompt_input_name": os.environ.get(f"{prefix}_NEGATIVE_INPUT", "text"),
        "seed_node_id": os.environ.get(f"{prefix}_SEED_NODE_ID"),
        "seed_input_name": os.environ.get(f"{prefix}_SEED_INPUT", "seed"),
        "frames_node_id": os.environ.get(f"{prefix}_FRAMES_NODE_ID"),
        "frames_input_name": os.environ.get(f"{prefix}_FRAMES_INPUT", "value"),
        "width_node_id": os.environ.get(f"{prefix}_WIDTH_NODE_ID"),
        "width_input_name": os.environ.get(f"{prefix}_WIDTH_INPUT", "value"),
        "height_node_id": os.environ.get(f"{prefix}_HEIGHT_NODE_ID"),
        "height_input_name": os.environ.get(f"{prefix}_HEIGHT_INPUT", "value"),
    }
