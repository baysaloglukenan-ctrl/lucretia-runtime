# ComfyUI Workflows for Lucreția

Lucreția integrates ComfyUI as an executable engine, but the actual model graph must be a ComfyUI **API workflow JSON**.

## Required file

Default path:

```text
workflows/comfy/ltx23_i2v_api.json
```

This file is the API export of the official ComfyUI LTX-2.3 Image-to-Video
template. The older `i2v_api_template.json` remains only as a generic example.

- LTX Video I2V
- Wan I2V / TI2V
- Stable Video Diffusion
- other ComfyUI image-to-video workflow

## Patch contract

Lucreția patches these values before queueing the workflow:

- source image
- positive prompt
- negative prompt
- seed
- frames
- width
- height

Configure node IDs via environment variables:

```env
LUCRETIA_COMFY_WORKFLOW=workflows/comfy/ltx23_i2v_api.json
LUCRETIA_COMFY_IMAGE_NODE_ID=10
LUCRETIA_COMFY_IMAGE_INPUT=image
LUCRETIA_COMFY_PROMPT_NODE_ID=20
LUCRETIA_COMFY_PROMPT_INPUT=text
LUCRETIA_COMFY_NEGATIVE_NODE_ID=21
LUCRETIA_COMFY_NEGATIVE_INPUT=text
LUCRETIA_COMFY_SEED_NODE_ID=30
LUCRETIA_COMFY_SEED_INPUT=seed
LUCRETIA_COMFY_FRAMES_NODE_ID=31
LUCRETIA_COMFY_FRAMES_INPUT=value
LUCRETIA_COMFY_WIDTH_NODE_ID=32
LUCRETIA_COMFY_WIDTH_INPUT=value
LUCRETIA_COMFY_HEIGHT_NODE_ID=33
LUCRETIA_COMFY_HEIGHT_INPUT=value
```

If your workflow uses different node ids or input names, update the env values instead of editing Python.

For the bundled LTX-2.3 workflow, node IDs are discovered automatically.
Lucreția patches the prompt primitive, negative conditioning, both noise
seeds, final width/height controls, and the video frame controls.
Requested frames are normalized to the LTX `8n+1` rule.

## Silent generation policy

ComfyUI generation always produces a silent MP4. AI-generated wind, dialogue,
music, and model-native sound are disabled. Child-friendly voice, music,
captions, and comic sound effects are added only in Lucreția's separate
post-production stage after the animation is approved.

`minimax_h3_r2v_api.json` uses MiniMax H3's required internal AV latent, but it
does not load a dedicated Audio VAE, decode audio, or connect an audio stream to
`CreateVideo`. Its first and final images are hard frame guides rather than
unpositioned reference images, and its story prompt must begin with an immediate
visual hook.

## Engine config

```env
LUCRETIA_COMFY_MODE=managed
LUCRETIA_COMFY_ROOT=vendor/ComfyUI
LUCRETIA_COMFY_URL=http://127.0.0.1:8188
LUCRETIA_COMFY_HOST=127.0.0.1
LUCRETIA_COMFY_PORT=8188
LUCRETIA_COMFY_PYTHON=python
LUCRETIA_COMFY_AUTO_START=true
```

Run setup:

```bash
python scripts/setup_comfyui.py
```

Then start Lucreția and use the ComfyUI panel.
