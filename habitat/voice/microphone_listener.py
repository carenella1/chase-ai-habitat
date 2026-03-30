import sounddevice as sd
import numpy as np
import wave


class MicrophoneListener:

    def record(self, filename="input.wav", duration=5, fs=16000):

        print("Listening...")

        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
        sd.wait()

        recording = np.squeeze(recording)

        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(fs)
            wf.writeframes((recording * 32767).astype(np.int16).tobytes())

        return filename