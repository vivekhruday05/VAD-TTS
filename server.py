import asyncio
import io
import numpy as np
import soundfile as sf
import websockets
from kokoro import KPipeline

# Initialize the Kokoro TTS pipeline.
pipeline = KPipeline(lang_code='a')

async def tts_handler(websocket):
    """Handler for TTS websocket connections"""
    try:
        async for message in websocket:
            print(f"Received text: {message}")
            try:
                # Generate TTS audio segments using Kokoro.
                audio_segments = []
                for i, (gs, ps, audio) in enumerate(pipeline(message, voice='af_heart', speed=1)):
                    audio_segments.append(audio)
                
                # Concatenate all audio segments into one waveform.
                audio_combined = np.concatenate(audio_segments)
                
                # Write the waveform to a bytes buffer as a WAV file.
                buffer = io.BytesIO()
                sf.write(buffer, audio_combined, 24000, format='WAV')
                wav_bytes = buffer.getvalue()
                
                # Send the synthesized WAV audio to the client.
                await websocket.send(wav_bytes)
                print("Sent TTS audio.")
            except Exception as e:
                print(f"Error processing TTS request: {e}")
                # Send an error message or empty response if TTS fails
                await websocket.send(b"")
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected.")
    except Exception as e:
        print(f"Error in TTS handler: {e}")

async def main():
    try:
        async with websockets.serve(
            lambda websocket: tts_handler(websocket), 
            "localhost", 
            8765
        ) as server:
            print("TTS server running on ws://localhost:8765")
            await asyncio.Future()  # Run forever
    except Exception as e:
        print(f"Server error: {e}")
        # Give the server a chance to restart
        await asyncio.sleep(5)
        return await main()  # Recursively restart the server

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down...")
    except Exception as e:
        print(f"Fatal server error: {e}")
