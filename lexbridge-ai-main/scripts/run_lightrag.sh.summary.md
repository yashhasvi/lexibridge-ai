# File: run_lightrag.sh

## Purpose
Starts the LightRAG server, a LLM-based server for interacting with knowledge graphs.

## Key Components
- Sets up environment variables for script execution
- Sources `.env` file (optional) for environment variable overrides
- Exports `EMBEDDING_MODEL` to use the Ollama model instead of HuggingFace's default

## Important Logic
Executes `uv run` command with project-specific configuration:
  - Project directory: `$PRJ/brain_module`
  - Python version: `3.10`
  - Server host and port: `0.0.0.0:9621`

## Dependencies
- Requires `.env` file (optional) in `brain_module/` directory for environment variable overrides
- Requires `uv run` command to be available

## Notes
- The script uses `$PRJ/lightrag_data` as the working directory
- If sourcing `.env` fails, it prints a warning message and continues execution