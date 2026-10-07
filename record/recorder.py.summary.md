# File: recorder.py

## Purpose
A microphone recorder that captures audio from the system mic and saves it to a file.

## Key Components
- The `Recorder` class, which is a buffered microphone recorder.
- The `start()`, `stop()`, and `save()` methods for controlling recording and saving audio.
- A context manager interface (`with Recorder(): ...`) for easy recording.

## Important Logic
The `record()` method blocks until the user stops it with Ctrl-C. It can optionally save the recorded audio to a file automatically. The `start()` method begins capturing audio, while the `stop()` method stops and returns the full recording as an array.

## Dependencies
- The `sounddevice` and `soundfile` libraries for audio capture and writing.
- PortAudio (for macOS: install with `brew install portaudio`, Debian: install with `sudo apt install libportaudio2`).

## Notes
- This module pairs well with the `transcribe_chunked()` function from the `audio` module to perform transcription on recorded audio.