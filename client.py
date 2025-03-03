import asyncio
import websockets
import random
import threading
import time
import io
import signal
import sys

import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad

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

# List of random text statements.
text_statements = [
    "The quick brown fox jumps over the lazy dog.",
    "Hello world, this is a test of the TTS system.",
    "Real-time interaction is the key to success.",
    "Voice activity detection triggers the TTS.",
    "Python makes asynchronous programming easier."
]

# Global VAD event.
speech_started_event = threading.Event()  # True when speech is detected

# Global state for TTS request.
tts_requested = False   # True when a TTS request has been sent and we are waiting for audio.
tts_audio = None        # Stores the TTS audio (WAV bytes) received from the server.

# VAD configuration.
vad_mode = 3                  # Most aggressive mode.
vad = webrtcvad.Vad(vad_mode)
sample_rate = 16000
frame_duration = 30           # in milliseconds
frame_size = int(sample_rate * frame_duration / 1000)

# Noise filtering parameters.
min_speech_frames = 3         # At least this many consecutive speech frames to count as speech.
silence_duration_threshold = 1.0  # Seconds of silence required to mark speech as ended.

# Playback control.
playback_lock = threading.Lock()
playback_active = False       # True when audio playback is currently happening.
playback_thread = None        # Reference to the playback monitor thread

def vad_worker():
    """
    Continuously reads audio from the microphone and uses webrtcvad to detect speech.
    Sets or clears the speech_started_event accordingly.
    """
    speech_frames_counter = 0
    last_voice_time = time.time()
    
    with sd.RawInputStream(samplerate=sample_rate, blocksize=frame_size,
                           dtype='int16', channels=1) as stream:
        while running:
            try:
                data, _ = stream.read(frame_size)
            except Exception as e:
                print(f"Error reading audio: {e}")
                continue
            
            try:
                is_speech = vad.is_speech(bytes(data), sample_rate)
            except Exception as e:
                print(f"VAD error: {e}")
                is_speech = False
            
            if is_speech:
                speech_frames_counter += 1
                last_voice_time = time.time()
                if speech_frames_counter >= min_speech_frames:
                    if not speech_started_event.is_set():
                        speech_started_event.set()
                        print("Speech started")
            else:
                if speech_started_event.is_set() and (time.time() - last_voice_time) > silence_duration_threshold:
                    speech_started_event.clear()
                    speech_frames_counter = 0
                    print("Speech ended")
                if speech_frames_counter > 0:
                    speech_frames_counter -= 1
            time.sleep(0.01)

def start_playback(wav_bytes):
    """
    Starts audio playback using SoundDevice.
    Reads WAV bytes using SoundFile, plays the audio, and spawns a polling thread to monitor playback.
    Instead of using sd.wait(), we compute the duration and poll until that time elapses.
    """
    global playback_active, playback_thread
    try:
        buffer = io.BytesIO(wav_bytes)
        audio_data, sample_rate_audio = sf.read(buffer, dtype='float32')
        # Calculate duration in seconds.
        duration = len(audio_data) / sample_rate_audio
        with playback_lock:
            playback_active = True
        sd.play(audio_data, sample_rate_audio)
        
        # Spawn a daemon thread to monitor playback via polling.
        def monitor():
            global playback_active  # Declare global to access playback_active.
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
    Stops the current playback if it is active.
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
    - When speech is detected and no TTS request is pending, sends a TTS request immediately.
    - When playback is active and the user interrupts, stops playback and immediately sends a new TTS request.
    - When the user stops speaking and TTS audio is available, starts playback.
    """
    global tts_requested, tts_audio
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
                            # Reset state so a new TTS request is sent immediately.
                            tts_requested = False
                            tts_audio = None
                            if speech_started_event.is_set() and not tts_requested:
                                text_to_send = random.choice(text_statements)
                                print(f"Sending text to TTS: {text_to_send}")
                                await websocket.send(text_to_send)
                                tts_audio = await websocket.recv()
                                print("Received TTS audio.")
                                tts_requested = True
                        await asyncio.sleep(0.05)
                        continue

                    # When not playing, if speech is detected and no TTS request is pending, send a TTS request.
                    if speech_started_event.is_set() and not tts_requested:
                        text_to_send = random.choice(text_statements)
                        print(f"Sending text to TTS: {text_to_send}")
                        await websocket.send(text_to_send)
                        tts_audio = await websocket.recv()
                        print("Received TTS audio.")
                        tts_requested = True

                    # Once speech has ended and TTS audio is available, start playback.
                    if (not speech_started_event.is_set()) and tts_audio is not None and not is_playback_active():
                        print("User stopped speaking. Starting playback.")
                        start_playback(tts_audio)
                        # Reset TTS state for the next interaction.
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
    print("Starting VAD client. Speak into your microphone.")
    print(f"VAD aggressiveness: {vad_mode}/3")
    print(f"Min consecutive speech frames: {min_speech_frames}")
    print(f"Silence threshold: {silence_duration_threshold}s")
    
    # Start the VAD worker thread.
    vad_thread = threading.Thread(target=vad_worker, daemon=True)
    vad_thread.start()
    
    try:
        asyncio.run(tts_client())
    except KeyboardInterrupt:
        print("KeyboardInterrupt caught. Exiting.")
        stop_playback_safely()
