# VAD-TTS
This project demonstrates a real-time interactive text-to-speech (TTS) system using a server–client architecture over WebSockets. The system integrates the Kokoro TTS model (hexgrad/Kokoro-82M) from Hugging Face to generate speech from text, and it uses voice activity detection (VAD) to manage real-time interactions.

The project consists of two main components:

- `Server (server.py)`
The server hosts a WebSocket API that listens for text requests, synthesizes speech using the Kokoro TTS pipeline, and returns synthesized audio in WAV format.

- `Client (client.py)`
The client continuously captures microphone input with PyAudio and applies VAD (using webrtcvad) to detect when the user starts or stops speaking. When speech is detected, a random text statement is sent to the server. When the user stops speaking, the client receives and plays back the synthesized audio. If the user speaks during playback, the system interrupts the audio to handle the new input in real time.



## Installing required packages
In your terminal run the following commands to download the required packages:
```bash
sudo apt-get update
sudo apt-get install -y portaudio19-dev libasound2-dev espeak-ng build-essential
```
Setup your virtual environment using the below commands:
```bash
python3 -m venv myenv
source myenv/bin/activate
```
Now, once you are in the virtual environment, install required python dependencies using the following commands:
```bash
pip install -r requirements.txt 
```

## Usage
Now, since you have installed all the required packages, you are good to go.

First start the server:
```bash
python3 server.py
```
Wait until the server shows a message called it's running.

Now, connect a client:
```bash
python3 client.py
```

