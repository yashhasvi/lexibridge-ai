# File: devMockPayload.ts

## Purpose
Temporary payload for frontend development without the brain_module running.

## Key Components
- `buildMockGenerateAnswerResponse` function that generates a response based on user input and mock data.
- `MockSourcePayload` interface representing a source with metadata.
- `MockGenerateAnswerShape` interface representing the generate answer shape with various fields.

## Important Logic
The function `buildMockGenerateAnswerResponse` uses regular expressions to determine whether the user's question is a greeting or factual. It then returns a response object containing the question, answer (greeting or factual), sources, and other metadata. The mock data includes various sources from Wikipedia, Stack Exchange, ArXiv, GitHub, and more.

## Dependencies
- `VITE_DEV_MOCK_API` environment variable to enable dev mode.
- Various external libraries and frameworks for frontend development.

## Notes
This file is intended for development purposes only and should not be used in production. It provides a temporary payload for testing and debugging the frontend without requiring the brain_module to run.