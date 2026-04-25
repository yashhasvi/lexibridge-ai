# File: llm_client.py

## Purpose
The purpose of this file is to provide a unified interface for interacting with different Large Language Model (LLM) backends.

## Key Components
- The `LLMClient` class serves as the base class for all LLM clients.
- Supported backends include OpenAI, Ollama, vLLM, TGI, and LiteLLM.

## Important Logic
The file defines two main methods:
  - `complete`: Generates text based on a prompt. This method is asynchronous and can be used to generate both single responses and streams of responses.
  - `stream`: Generates tokens as they arrive from the LLM. This method defaults to calling `complete` but provides more fine-grained control for streaming.

## Dependencies
- `openai` library for interacting with OpenAI's API.
- `httpx` library for making HTTP requests in Ollama backend.

## Notes
The code includes support for multiple backends and provides a unified interface for using these models. The file also includes environment variables to configure the vLLM server and TGI endpoints.