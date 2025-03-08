import numpy as np
import soundfile as sf
import io
from kokoro import KPipeline

# Initialize Kokoro TTS pipeline
pipeline = KPipeline(lang_code='hi')

# Take Hindi text input
hindi_text = '''विराट कोहली क्रीज पर तैयार हैं… गेंदबाज ने रनअप लिया, और यह तेज़ गेंद… कोहली ने खूबसूरत कवर ड्राइव खेला! गेंद बाउंड्री की ओर दौड़ रही है, कोई फील्डर नहीं रोक पाएगा… चार रन! क्या क्लासिक शॉट खेला है विराट कोहली ने!

अब अगली गेंद… यह एक शॉर्ट बॉल… कोहली ने पुल शॉट खेला, और यह गया छक्के के लिए! गजब की टाइमिंग और पावर! स्टेडियम में दर्शक झूम उठे हैं, विराट कोहली की शानदार बैटिंग देखने लायक है!

गेंदबाज अब दबाव में है… अगली गेंद फुल लेंथ, और कोहली ने सीधा मैदान के बीचों-बीच खेल दिया… यह भी बाउंड्री के पार! लगातार शानदार शॉट्स, और विराट कोहली इस पारी को एक बड़े स्कोर की ओर ले जा रहे हैं!'''

# Generate TTS audio
audio_segments = []
for _, _, audio in pipeline(hindi_text, voice='hf_alpha', speed=1):
    audio_segments.append(audio)

# Combine audio segments into one waveform
audio_combined = np.concatenate(audio_segments)

# Save the audio as MP3
sf.write("output.mp3", audio_combined, 24000, format='MP3')

print("Speech saved as output.mp3")
