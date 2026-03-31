"""
habitat/voice/local_tts.py
"""

import base64
import io
import os
import traceback

# Force CPU — prevents cuDNN crash on systems with incompatible CUDA
os.environ["CUDA_VISIBLE_DEVICES"] = ""

KOKORO_VOICE_MAP = {
    "analytical": "af_sarah",
    "challenger": "am_adam",
    "explorer": "af_sky",
    "philosopher": "am_michael",
    "default": "af_sarah",
}

KOKORO_SPEED_MAP = {
    "analytical": 1.0,
    "challenger": 1.05,
    "explorer": 1.0,
    "philosopher": 0.92,
    "default": 1.0,
}

_kokoro_pipeline = None
_kokoro_available = None


def _get_kokoro():
    global _kokoro_pipeline, _kokoro_available

    if _kokoro_available is False:
        return None, False

    if _kokoro_pipeline is not None:
        return _kokoro_pipeline, True

    try:
        from kokoro import KPipeline

        print("🔊 Loading Kokoro TTS pipeline (CPU mode)...")
        _kokoro_pipeline = KPipeline(lang_code="a")
        _kokoro_available = True
        print("✅ Kokoro TTS ready")
        return _kokoro_pipeline, True
    except ImportError:
        print("⚠️ Kokoro not installed.")
        _kokoro_available = False
        return None, False
    except Exception as e:
        print(f"⚠️ Kokoro init failed: {e}")
        _kokoro_available = False
        return None, False


def generate_local_voice(text: str, persona: str = "analytical") -> str:
    if not text or not text.strip():
        return ""

    pipeline, available = _get_kokoro()
    if not available or pipeline is None:
        return ""

    try:
        import numpy as np
        import soundfile as sf

        voice_id = KOKORO_VOICE_MAP.get(persona, KOKORO_VOICE_MAP["default"])
        speed = KOKORO_SPEED_MAP.get(persona, 1.0)

        audio_chunks = []
        generator = pipeline(text, voice=voice_id, speed=speed, split_pattern=r"\n+")

        for _, _, audio in generator:
            if audio is not None and len(audio) > 0:
                audio_chunks.append(audio)

        if not audio_chunks:
            print("⚠️ Kokoro returned no audio chunks")
            return ""

        full_audio = np.concatenate(audio_chunks)
        wav_buffer = io.BytesIO()
        sf.write(wav_buffer, full_audio, samplerate=24000, format="WAV")
        wav_buffer.seek(0)
        return base64.b64encode(wav_buffer.read()).decode("utf-8")

    except Exception as e:
        print(f"⚠️ Kokoro generation error: {e}")
        traceback.print_exc()
        return ""


def is_available() -> bool:
    _, available = _get_kokoro()
    return available
