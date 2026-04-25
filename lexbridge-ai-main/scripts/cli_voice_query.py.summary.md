# File: cli_voice_query.py

## Purpose
Command-line interface (CLI) for voice query functionality, allowing users to record their voice, transcribe it using Whisper, and then ask a question to the Brain API.

## Key Components
* Record audio from the user's microphone
* Transcribe the recorded audio using the Whisper model
* Send the transcription to the Brain API as a question

## Important Logic
The script uses the `argparse` library to parse command-line arguments, including:
	+ Recording duration
	+ Brain API base URL
	+ Whisper model size
	+ Sound device index (optional)
It then attempts to record audio from the user's microphone using PortAudio and save it as a WAV file. After transcription is complete, it sends the transcription to the Brain API via HTTP POST request.

## Dependencies
* `httpx` library for sending HTTP requests
* `record` module for recording audio (imported from `record/requirements.txt`)
* `audio.chunk` module for transcribing recorded audio (imported from `audio/requirements.txt`)
* PortAudio and FFmpeg libraries for audio processing

## Notes
The script requires the user to run it from the repository root with a virtual environment activated.