# File: config.ts

## Purpose
Configures API and Whisper settings for the Brain API (FastAPI) application.

## Key Components
- `API_BASE_URL`: URL of the API server, defaults to `http://localhost:8001` if not set.
- `FORCE_BROWSER_SPEECH`: Optional flag to use browser Web Speech API instead of server Whisper.
- `WHISPER_MODEL`, `WHISPER_TRANSLATE_MODEL`, and `WHISPER_SOURCE_LANGUAGE_HINT`: Configurable Whisper model settings for speech recognition and translation.
- `DEV_MOCK_API`: Flag to enable in-memory mock API payloads for development.

## Important Logic
Configurations are loaded from environment variables (`.env` files) and defaults are applied if variables are not set.

## Dependencies
Environment variables: VITE_API_BASE_URL, VITE_FORCE_BROWSER_SPEECH, VITE_WHISPER_MODEL, VITE_WHISPER_TRANSLATE_MODEL, VITE_DEV_MOCK_API

## Notes
The file uses `import.meta.env` to load environment variables and provide default values if they are not set.