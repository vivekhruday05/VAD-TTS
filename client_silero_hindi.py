import asyncio
import io
import random
import threading
import time
import sys
import signal

import numpy as np
import sounddevice as sd
import soundfile as sf
import websockets
import pyaudio
from pydub import AudioSegment
import simpleaudio as sa
import torch

# -------------------------------
# Load Silero VAD model from Torch Hub
# -------------------------------
model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad', force_reload=False)
(get_speech_timestamps, _, _, _, _) = utils

# Global running flag.
running = True

# Register a signal handler to catch Ctrl+C.
def signal_handler(sig, frame):
    global running
    print("Ctrl+C pressed. Shutting down gracefully.")
    running = False
    stop_playback_safely()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

text_statements = [
    "जल्दी उठो, सूरज निकल रहा है।",
    "यह एक परीक्षण वाक्य है।",
    "वास्तविक समय में इंटरैक्शन महत्वपूर्ण है।",
    "वॉयस एक्टिविटी डिटेक्शन टीटीएस को ट्रिगर करता है।",
    "पायथन प्रोग्रामिंग बहुत मजेदार है।"
]

# Global VAD event.
import threading
speech_started_event = threading.Event()  # Set when speech is detected

# VAD and audio configuration.
sample_rate = 16000
frame_duration = 30           # in milliseconds
frame_size = int(sample_rate * frame_duration / 1000)

# Buffering parameters for Silero VAD.
vad_window_duration = 0.3     # seconds: window size for inference
required_samples = int(sample_rate * vad_window_duration)
overlap_duration = 0.05       # seconds: overlap between consecutive windows
overlap_samples = int(sample_rate * overlap_duration)

# Playback control.
playback_lock = threading.Lock()
playback_active = False       # True when audio playback is active.
playback_thread = None        # Reference to the playback monitor thread

def vad_worker():
    """
    Continuously reads audio from the microphone and uses Silero VAD to detect speech.
    Audio is accumulated into a buffer for a window (default 300ms), then the VAD model
    is run with a threshold that is dynamically set based on whether audio playback is active.
    
    When playback is active, a higher threshold is used (e.g. 0.5) to avoid picking up
    the playback audio. When no playback is active, a lower threshold (e.g. 0.3) is used
    to be more sensitive to quieter speech.
    """
    global running
    buffer = np.array([], dtype=np.int16)
    
    with sd.RawInputStream(samplerate=sample_rate, blocksize=frame_size,
                           dtype='int16', channels=1) as stream:
        while running:
            try:
                data, _ = stream.read(frame_size)
            except Exception as e:
                print(f"Error reading audio: {e}")
                continue

            # Append incoming data to the buffer
            frame = np.frombuffer(data, dtype=np.int16)
            buffer = np.concatenate((buffer, frame))
            
            if len(buffer) >= required_samples:
                # Dynamically adjust the threshold based on playback state.
                with playback_lock:
                    if playback_active:
                        effective_threshold = 0.85  # Less sensitive during playback.
                    else:
                        effective_threshold = 0.5  # More sensitive when no playback.
                
                # Run Silero VAD with the effective threshold and a short minimum speech duration.
                speech_timestamps = get_speech_timestamps(
                    buffer,
                    model,
                    sampling_rate=sample_rate,
                    threshold=effective_threshold,
                    min_speech_duration_ms=100
                )
                if len(speech_timestamps) > 0:
                    if not speech_started_event.is_set():
                        speech_started_event.set()
                        print("Speech started")
                else:
                    if speech_started_event.is_set():
                        speech_started_event.clear()
                        print("Speech ended")
                
                # Keep only the last few samples for overlap continuity.
                buffer = buffer[-overlap_samples:]
            time.sleep(0.01)

def start_playback(wav_bytes):
    """
    Starts audio playback using SoundDevice.
    Reads WAV bytes using SoundFile, plays the audio, and spawns a polling thread to monitor playback.
    """
    global playback_active, playback_thread
    try:
        buffer = io.BytesIO(wav_bytes)
        audio_data, sample_rate_audio = sf.read(buffer, dtype='float32')
        duration = len(audio_data) / sample_rate_audio
        with playback_lock:
            playback_active = True
        sd.play(audio_data, sample_rate_audio)
        
        # Monitor playback in a separate daemon thread.
        def monitor():
            global playback_active
            start_time = time.time()
            while time.time() - start_time < duration and running:
                time.sleep(0.1)
                with playback_lock:
                    if not playback_active:
                        return
            with playback_lock:
                playback_active = False
        
        playback_thread = threading.Thread(target=monitor, daemon=True)
        playback_thread.start()
    except Exception as e:
        print(f"Playback error: {e}")
        with playback_lock:
            playback_active = False

def stop_playback_safely():
    """
    Stops the current playback if active.
    """
    global playback_active
    with playback_lock:
        if playback_active:
            try:
                sd.stop()
            except Exception as e:
                print(f"Error stopping playback: {e}")
            playback_active = False

def is_playback_active():
    """Return the current playback state in a thread-safe manner."""
    with playback_lock:
        return playback_active

async def tts_client():
    """
    Connects to the TTS server via WebSockets.
    - When speech is detected and no TTS request is pending, sends a TTS request.
    - If playback is active and the user interrupts, stops playback and sends a new request.
    - Once speech ends and TTS audio is received, starts playback.
    """
    global tts_requested, tts_audio
    tts_requested = False
    tts_audio = None
    uri = "ws://localhost:8765"
    reconnect_delay = 5  # seconds

    while running:
        try:
            async with websockets.connect(uri) as websocket:
                print("Connected to TTS server.")
                while running:
                    # If playback is active, check for interruption.
                    if is_playback_active():
                        if speech_started_event.is_set():
                            print("Interrupting playback due to user speech.")
                            stop_playback_safely()
                            tts_requested = False
                            tts_audio = None
                            if speech_started_event.is_set() and not tts_requested:
                                text_to_send = random.choice(text_statements)
                                print(f"Sending TTS request: {text_to_send}")
                                await websocket.send(text_to_send)
                                tts_audio = await websocket.recv()
                                print("Received TTS audio.")
                                tts_requested = True
                        await asyncio.sleep(0.05)
                        continue

                    # When not playing, if speech is detected and no TTS request is pending, send a TTS request.
                    if speech_started_event.is_set() and not tts_requested:
                        text_to_send = random.choice(text_statements)
                        print(f"Sending TTS request: {text_to_send}")
                        await websocket.send(text_to_send)
                        tts_audio = await websocket.recv()
                        print("Received TTS audio.")
                        tts_requested = True

                    # Once speech has ended and TTS audio is available, start playback.
                    if (not speech_started_event.is_set()) and tts_audio is not None and not is_playback_active():
                        print("User stopped speaking. Starting playback.")
                        start_playback(tts_audio)
                        tts_requested = False
                        tts_audio = None

                    await asyncio.sleep(0.05)
        except websockets.exceptions.ConnectionClosed:
            print(f"Connection to server lost. Reconnecting in {reconnect_delay} seconds...")
            await asyncio.sleep(reconnect_delay)
        except Exception as e:
            print(f"Error: {e}. Reconnecting in {reconnect_delay} seconds...")
            await asyncio.sleep(reconnect_delay)

if __name__ == "__main__":
    print("Starting Silero VAD client. Speak into your microphone.")
    print(f"Using a VAD window of {vad_window_duration}s with {overlap_duration}s overlap.")
    
    # Start the Silero VAD worker thread.
    vad_thread = threading.Thread(target=vad_worker, daemon=True)
    vad_thread.start()
    
    try:
        asyncio.run(tts_client())
    except KeyboardInterrupt:
        print("KeyboardInterrupt caught. Exiting.")
        stop_playback_safely()
