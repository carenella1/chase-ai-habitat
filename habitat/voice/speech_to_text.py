import io

_stt_model = None
_stt_available = None


def _get_model():
    """Lazily load the local Whisper model. Prefers GPU (large-v3), falls
    back to CPU (small) if CUDA isn't available or fails to initialize."""
    global _stt_model, _stt_available

    if _stt_available is False:
        return None, False
    if _stt_model is not None:
        return _stt_model, True

    from faster_whisper import WhisperModel

    try:
        _stt_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception as e:
        print(f"⚠️ Whisper GPU load failed ({e}), falling back to CPU")
        try:
            _stt_model = WhisperModel("small", device="cpu", compute_type="int8")
        except Exception as e2:
            print(f"⚠️ Local Whisper unavailable: {e2}")
            _stt_available = False
            return None, False

    _stt_available = True
    return _stt_model, True


def transcribe_audio_data(audio_data) -> str:
    """Transcribe a speech_recognition AudioData object using local Whisper."""
    model, available = _get_model()
    if not available:
        return ""
    segments, _ = model.transcribe(io.BytesIO(audio_data.get_wav_data()))
    return "".join(segment.text for segment in segments).strip()


def is_available() -> bool:
    _, available = _get_model()
    return available


class SpeechToText:
    """Kept for habitat/voice/voice_interface.py, which transcribes from a file."""

    def __init__(self):
        self.model, self.available = _get_model()

    def transcribe(self, audio_path):
        if not self.available:
            return ""
        segments, _ = self.model.transcribe(audio_path)
        return "".join(segment.text for segment in segments).strip()
