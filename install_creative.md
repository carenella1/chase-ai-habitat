# Setting up NEX's Creative tab (local image generation)

The Creative tab doesn't generate images itself — it hands the job to a
separate free program called **ComfyUI**, running quietly in the background
on your own PC (no cloud, nothing leaves your machine). Think of it like
Ollama, but for images instead of text.

**Status as of the 2026-07-13 fix: ComfyUI is installed and all required
files for both options are in place.** (An earlier version of this doc had
you fetching `t5xxl_fp8_e4m3fn.safetensors`/`clip_l.safetensors`/
`ae.safetensors` for the "quality" option — those are FLUX.1 files. FLUX.2
klein-9B, which is what's actually installed, needs a different text
encoder and VAE entirely; see the checklist in section 2.)

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
| `qwen_3_8b_fp8mixed.safetensors` (FLUX.2 text encoder) | `models\text_encoders\` | ✅ present |
| `full_encoder_small_decoder.safetensors` (FLUX.2 image decoder / VAE) | `models\vae\` | ✅ present |

**Both options are fully ready to use right now.**

FLUX.2 klein-9B uses a single **Qwen3-8B** text encoder (not the T5-XXL +
CLIP-L pair FLUX.1 used) and its own small-decoder VAE. If you ever
reinstall from scratch, get them from:

- `qwen_3_8b_fp8mixed.safetensors` — `https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors`
- `full_encoder_small_decoder.safetensors` — `https://huggingface.co/black-forest-labs/FLUX.2-small-decoder/resolve/main/full_encoder_small_decoder.safetensors`

**Leftover files you can ignore (or delete to save space)**: `models\clip\`
still has `t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors`, and
`CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`, and `models\vae\` still has
`ae.safetensors` — these were FLUX.1-era downloads that turned out not to
apply to FLUX.2 klein-9B. Neither workflow uses them anymore; they're just
inert disk space (~5.7GB combined) unless you add a FLUX.1 workflow later.

### ⚠️ Size note on the FLUX unet file

The file on disk, `flux-2-klein-9b.safetensors`, is the **9B** parameter
build at ~18GB — bigger than the 4B build this feature was originally scoped
around. You checked and a 4B FLUX.2 klein build isn't published on Hugging
Face, so 9B is what's actually available — this isn't something to keep
chasing. At full precision that's too big for a 16GB card on its own, so
`flux2_klein_quality.json` loads it with `weight_dtype: "fp8_e4m3fn"` —
ComfyUI compresses it to roughly half size (~9GB) the moment it loads, the
same trick already used for the Turbo checkpoint. That's noticeably slower
than the fast option (bigger model, more sampling steps), but should fit
without spilling to system RAM as long as nothing else is holding a big
chunk of VRAM at the same time (e.g. a chat model still loaded in Ollama).

## 3. Optional: LoRAs

If you download a LoRA (a small style/character add-on file) later, drop it
in `C:\ComfyUI\ComfyUI\models\loras\` and type its exact filename into the
LoRA field in the Creative tab when generating.

## 4. How you'll know something's missing

If you try to generate before ComfyUI is running, or before a model file is
in place, the Creative tab tells you exactly what's missing and which folder
it belongs in — it won't just fail silently or throw a raw error.
