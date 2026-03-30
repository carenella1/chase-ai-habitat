from transformers import pipeline


class EmotionDetector:

    def __init__(self):

        self.classifier = pipeline(
            "audio-classification",
            model="superb/wav2vec2-base-superb-er"
        )

    def detect(self, audio_file):

        result = self.classifier(audio_file)

        return result[0]["label"]