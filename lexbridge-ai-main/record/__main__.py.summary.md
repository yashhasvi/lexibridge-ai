# File: `__main__.py`

## Purpose
A command-line interface (CLI) entry point for recording audio from the system microphone and saving it to a WAV file.

## Key Components
- `argparse`: Used for parsing command-line arguments.
- `record_to_file` function: Responsible for recording audio to a file.
- Audio module (`audio.py`) used for transcription after recording.

## Important Logic
- Recording logic is handled by the `record_to_file` function, which takes in parameters such as output path, duration, sample rate, device, and whether to show a live RMS level bar.
- Transcription logic is handled by the `transcribe_chunked` function from the audio module (`audio.py`), which processes the recorded file.

## Dependencies
- `argparse`
- Audio module (`audio.py`)
- OpenAI Whisper + PyDub (for transcription)

## Notes
- This script can be run with various options, including recording for a specified duration, selecting an input device, and listing available audio devices.
- Transcription requires the audio module to be installed and accessible.