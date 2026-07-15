"""
habitat/voice/vad_listen.py

Mic capture for Nex Live's /api/voice/listen, using Silero VAD (a small
open-source neural voice-activity model) to detect when the user has
stopped talking — instead of speech_recognition's simple energy/RMS
threshold, which is unreliable with mics that apply automatic gain
control or noise gating (common on wireless/gaming headsets).

Falls back to the original energy-threshold capture if Silero VAD can't
be loaded (e.g. no internet on first run, since the model is fetched via
torch.hub on first use and cached under ~/.cache/torch/hub afterward).
"""

import threading

import numpy as np
import speech_recognition as sr

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512  # Silero VAD's documented chunk size at 16kHz

_silero_model = None
_silero_utils = None
_silero_available = None
_vad_lock = threading.Lock()


def _get_silero_vad():
    global _silero_model, _silero_utils, _silero_available

    if _silero_available is False:
        return None, None, False
    if _silero_model is not None:
        return _silero_model, _silero_utils, True

    try:
        import torch

        print("🎙️ Loading Silero VAD...")
        model, utils = torch.hub.load(
            "snakers4/silero-vad", "silero_vad", trust_repo=True, onnx=False
        )
        _silero_model = model
        _silero_utils = utils
        _silero_available = True
        print("✅ Silero VAD ready")
        return model, utils, True
    except Exception as e:
        print(f"⚠️ Silero VAD unavailable ({e}), falling back to energy-threshold detection")
        _silero_available = False
        return None, None, False


def record_until_silence(
    device_index=None,
    silence_ms=700,
    max_duration=20.0,
    start_timeout=8.0,
    sample_rate=SAMPLE_RATE,
):
    """Records from the mic until the user stops talking (or start_timeout
    passes with no speech at all), returning a speech_recognition.AudioData
    ready for transcription, or None on timeout."""
    model, utils, available = _get_silero_vad()
    if not available:
        return _legacy_capture(device_index=device_index)

    with _vad_lock:
        return _vad_capture(
            model, utils, device_index, silence_ms, max_duration, start_timeout, sample_rate
        )


def _resolve_device_index(device_index):
    """Device indices aren't stable across reboots/driver changes — verify
    the configured one still exists, otherwise fall back to the system
    default rather than failing the whole capture."""
    if device_index is None:
        return None
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        if 0 <= device_index < len(devices) and devices[device_index]["max_input_channels"] > 0:
            return device_index
        print(f"⚠️ Configured input device #{device_index} no longer available, using system default")
    except Exception as e:
        print(f"⚠️ Could not validate input device #{device_index}: {e}")
    return None


def _vad_capture(model, utils, device_index, silence_ms, max_duration, start_timeout, sample_rate):
    import sounddevice as sd
    import torch

    _get_speech_timestamps, _save_audio, _read_audio, VADIterator, _collect_chunks = utils
    device_index = _resolve_device_index(device_index)

    # A fresh VADIterator resets the shared model's recurrent state in its
    # own __init__, so no state leaks between recordings.
    vad_iterator = VADIterator(
        model,
        threshold=0.5,
        sampling_rate=sample_rate,
        min_silence_duration_ms=silence_ms,
        speech_pad_ms=30,
    )

    stream, native_rate, native_chunk = _open_input_stream(device_index, sample_rate)

    frames = []
    speech_started = False
    chunk_seconds = CHUNK_SAMPLES / sample_rate
    elapsed = 0.0

    try:
        with stream:
            while elapsed < max_duration:
                raw_chunk, _overflowed = stream.read(native_chunk)
                raw_chunk = raw_chunk[:, 0]
                chunk = _resample(raw_chunk, native_rate, sample_rate) if native_rate != sample_rate else raw_chunk
                frames.append(chunk)
                elapsed += chunk_seconds

                event = vad_iterator(torch.from_numpy(chunk), return_seconds=False)
                if event and "start" in event:
                    speech_started = True
                if event and "end" in event and speech_started:
                    break

                if not speech_started and elapsed >= start_timeout:
                    return None
    finally:
        vad_iterator.reset_states()

    if not speech_started:
        return None

    audio_np = np.concatenate(frames)
    pcm16 = (audio_np * 32767).astype(np.int16).tobytes()
    return sr.AudioData(pcm16, sample_rate, 2)


def _open_input_stream(device_index, sample_rate):
    """Opens a mic input stream at sample_rate directly if the device
    supports it. Many WASAPI devices on Windows reject an arbitrary
    samplerate ("Invalid sample rate") and only support their own native
    rate — in that case, falls back to capturing at the device's native
    rate with a proportionally sized chunk, and the caller resamples each
    chunk down to sample_rate itself.

    Returns (stream, capture_rate, chunk_size) — the stream is NOT yet
    started (the caller uses it as a context manager)."""
    import sounddevice as sd

    try:
        # PortAudio validates the requested sample rate at construction
        # time (Pa_OpenStream), so an unsupported rate raises right here.
        stream = sd.InputStream(
            device=device_index, channels=1, samplerate=sample_rate,
            dtype="float32", blocksize=CHUNK_SAMPLES,
        )
        return stream, sample_rate, CHUNK_SAMPLES
    except Exception:
        pass

    query_index = device_index if device_index is not None else sd.default.device[0]
    native_rate = int(sd.query_devices(query_index)["default_samplerate"])
    native_chunk = max(1, round(CHUNK_SAMPLES * native_rate / sample_rate))
    print(f"⚠️ Mic doesn't support {sample_rate}Hz directly, capturing at its native {native_rate}Hz and resampling")
    return sd.InputStream(
        device=device_index, channels=1, samplerate=native_rate,
        dtype="float32", blocksize=native_chunk,
    ), native_rate, native_chunk


def _resample(chunk, native_rate, target_rate):
    """Lightweight linear-interpolation resample — good enough for VAD/
    Whisper input, not intended as broadcast-quality resampling."""
    n_out = round(len(chunk) * target_rate / native_rate)
    return np.interp(
        np.linspace(0, len(chunk), n_out, endpoint=False),
        np.arange(len(chunk)),
        chunk,
    ).astype(np.float32)


def _legacy_capture(device_index=None):
    """Original speech_recognition energy-threshold capture, kept as a
    fallback so voice input degrades instead of hard-breaking when Silero
    VAD's one-time model fetch can't reach the network."""
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8
    try:
        with sr.Microphone(device_index=device_index) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            return recognizer.listen(source, timeout=8, phrase_time_limit=20)
    except sr.WaitTimeoutError:
        return None
