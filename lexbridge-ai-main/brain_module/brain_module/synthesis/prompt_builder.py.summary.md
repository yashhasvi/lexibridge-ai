# File: prompt_builder.py

## Purpose
Constructs the multi-source citation prompt for a Language Model (LLM) to answer questions based on multiple sources.

## Key Components
- `_SYSTEM_PROMPT`: A critical set of rules that must be followed by the LLM when answering questions.
- `build_synthesis_prompt`: Function that constructs the message list for the LLM chat API.
- `_format_sources`: Helper function that formats source blocks into a readable string.

## Important Logic
- The `build_synthesis_prompt` function takes in user question, source blocks, and optional hints (answer type and confidence) to generate a prompt for the LLM to answer the question.
- The prompt includes the sources, question, and instructions on how to format the answer with citations.

## Dependencies
None

## Notes
The code is designed to work with Language Models (LLM) that require multi-source citation prompts. It provides a flexible way to generate these prompts based on user questions, source blocks, and optional hints.