import time

from habitat.voice.microphone_listener import MicrophoneListener
from habitat.voice.speech_to_text import SpeechToText
from habitat.voice.emotion_detector import EmotionDetector
from habitat.agents.researcher_agent import ResearcherAgent
from habitat.memory.memory_manager import MemoryManager


class VoiceInterface:

    def __init__(self):

        self.listener = MicrophoneListener()
        self.transcriber = SpeechToText()
        self.emotion = EmotionDetector()
        self.agent = ResearcherAgent()
        self.memory = MemoryManager()

        self.WAKE_WORD = "habitat"

    def run(self):

        print("\nChase AI Habitat Voice System")
        print("Say 'Habitat' before your request.")
        print("Say 'exit habitat' to stop.\n")

        while True:

            try:

                # record microphone input
                audio_file = self.listener.record(duration=4)

                # transcribe speech
                text = self.transcriber.transcribe(audio_file)

                if not text.strip():
                    continue

                text_lower = text.lower()

                # exit condition
                if "exit habitat" in text_lower:
                    print("Shutting down Habitat voice interface.")
                    break

                # wake word filter
                if self.WAKE_WORD not in text_lower:
                    continue

                # detect emotion
                emotion = self.emotion.detect(audio_file)

                print("\nYou said:", text)
                print("Detected emotion:", emotion)

                # remove wake word from prompt
                cleaned_text = text_lower.replace(self.WAKE_WORD, "").strip()

                if not cleaned_text:
                    continue

                # agent reasoning
                response = self.agent.run(cleaned_text)

                print("\nHabitat Response:\n")
                print(response)
                print("\n")

                # store interaction memory
                try:
                    self.memory.store_memory(
                        content=f"Voice Interaction | User: {cleaned_text} | Emotion: {emotion} | Response: {response}",
                        summary="voice interaction",
                        source="voice_interface"
                    )
                except Exception:
                    pass

                time.sleep(1)

            except KeyboardInterrupt:
                print("\nVoice interface stopped.")
                break

            except Exception as e:
                print("\nVoice system error:", e)
                time.sleep(2)