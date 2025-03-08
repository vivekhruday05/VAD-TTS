import numpy as np
import soundfile as sf
import io
from kokoro import KPipeline

# Initialize Kokoro TTS pipeline
pipeline = KPipeline(lang_code='hi')

# Take Hindi text input
hindi_text = input("Enter Hindi text: ")

# Generate TTS audio
audio_segments = []
for _, _, audio in pipeline(hindi_text, voice='af_heart', speed=1):
    audio_segments.append(audio)

# Combine audio segments into one waveform
audio_combined = np.concatenate(audio_segments)

# Save the audio as MP3
sf.write("output.mp3", audio_combined, 24000, format='MP3')

print("Speech saved as output.mp3")
