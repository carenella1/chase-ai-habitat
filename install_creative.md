# Setting up NEX's Creative tab (local image generation)

The Creative tab doesn't generate images itself — it hands the job to a
separate free program called **ComfyUI**, running quietly in the background
on your own PC (no cloud, nothing leaves your machine). Think of it like
Ollama, but for images instead of text.

**Status as of the last check (2026-07-11): ComfyUI is installed and three of
the four required FLUX files are in place. Only `clip_l.safetensors` is still
missing — see the checklist in section 2.**

---

## 1. ComfyUI install — done, here's the layout

ComfyUI is installed as the Windows portable build at:

```
C:\ComfyUI\
├── ComfyUI\              ← the actual app (main.py, models\, etc.)
├── python_embeded\       ← its own bundled Python — NEX uses this to launch it
├── run_nvidia_gpu.bat    ← manual launcher, for testing by hand
└── ...
```

This is a two-level layout: `C:\ComfyUI` is the portable install's root
folder, and the real app + its `models\` folder live one level down, inside
`C:\ComfyUI\ComfyUI\`. `creative_engine.py` is already pointed at this exact
structure (`COMFYUI_ROOT` / `COMFYUI_DIR` near the top of the file) — nothing
else to do here unless you ever move the install.

To confirm it still works by hand any time: double-click
`C:\ComfyUI\run_nvidia_gpu.bat`. A console window opens, loads for a bit, and
says it's running on `http://127.0.0.1:8188` — open that address in a browser
to see the ComfyUI interface. Close the console when done; NEX starts/stops
it on its own from the Creative tab.

## 2. Model files — checklist

NEX's Creative tab offers two options, **fast** (Z-Image Turbo) and
**quality** (FLUX.2 klein). Checked against what's actually in
`C:\ComfyUI\ComfyUI\models\` right now:

| File | Goes in | Status |
|---|---|---|
| `z-image-turbo-fp8-aio.safetensors` | `models\checkpoints\` | ✅ present |
| `flux-2-klein-9b.safetensors` (main FLUX model) | `models\unet\` | ✅ present — **see size note below** |
| `t5xxl_fp8_e4m3fn.safetensors` (FLUX text encoder) | `models\clip\` | ✅ present |
| `ae.safetensors` (FLUX image decoder / VAE) | `models\vae\` | ✅ present |
| `clip_l.safetensors` (FLUX text encoder) | `models\clip\` | ❌ **still missing** |

**Fast option (Z-Image Turbo) is fully ready to use right now.**

**Quality option (FLUX.2 klein) needs one more file**: `clip_l.safetensors`.
This one's genuinely harder to find than it should be if you're searching
Comfy-Org's own collection — it isn't listed there under that name. It comes
from a different, very standard repo instead:

**`https://huggingface.co/comfyanonymous/flux_text_encoders`**

That repo is the canonical source ComfyUI's own examples point to for FLUX's
text encoders, and it's almost certainly where `t5xxl_fp8_e4m3fn.safetensors`
(already in your `models\clip\` folder) came from — `clip_l.safetensors`
sits right next to it in the same file list. It's small (~235MB, plain
OpenAI CLIP-L/14) — download it and drop it straight into
`C:\ComfyUI\ComfyUI\models\clip\`.

**Note on `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`** (the other file
already sitting in your `models\clip\` folder): that's an OpenCLIP ViT-H
model, a different architecture used for other things (like IP-Adapter or
Stable Cascade) — it is not a substitute for FLUX's `clip_l.safetensors` and
ComfyUI won't accept it in that role. It's harmless to leave it there; it's
just not doing anything for the Creative tab.

### ⚠️ Size note on the FLUX unet file

The file on disk, `flux-2-klein-9b.safetensors`, is the **9B** parameter
build at ~18GB — bigger than the 4B build this feature was originally scoped
around. You checked and a 4B FLUX.2 klein build isn't published on Hugging
Face, so 9B is what's actually available — this isn't something to keep
chasing. An 18GB file doesn't fit inside 16GB VRAM on its own, so ComfyUI
will spill part of it onto the CPU/system RAM: the "quality" option will
work, just noticeably slower than the fast option, with some risk of running
out of memory depending on overhead at generation time. Nothing to do here —
just setting the expectation.

## 3. Optional: LoRAs

If you download a LoRA (a small style/character add-on file) later, drop it
in `C:\ComfyUI\ComfyUI\models\loras\` and type its exact filename into the
LoRA field in the Creative tab when generating.

## 4. How you'll know something's missing

If you try to generate before ComfyUI is running, or before a model file is
in place, the Creative tab tells you exactly what's missing and which folder
it belongs in — it won't just fail silently or throw a raw error.
