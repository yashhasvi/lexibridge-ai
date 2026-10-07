# File: run_brain_module.sh

## Purpose
Starts the Brain Module API using Uvicorn.

## Key Components
- Sets up Python environment with necessary modules and paths.
- Checks for optional audio dependencies (whisper, pydub, edge-tts) if specified.
- Verifies that ffmpeg is installed on the system.
- Starts the Brain Module API using Uvicorn in development mode with automatic reload if specified.

## Important Logic
- Uses `uv sync` to check for optional audio dependencies and installs them if needed.
- Uses `exec uv run` to start the Uvicorn server with the specified settings.

## Dependencies
- `bash`
- `uv`
- `ffmpeg`

## Notes
- This script assumes that it is running from within a Git repository with a valid `PRJ` (project root) directory.
- The `BRAIN_AUDIO_BOOTSTRAP` and `BRAIN_DEV_RELOAD` environment variables can be used to control the behavior of this script.