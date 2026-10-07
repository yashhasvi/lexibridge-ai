# File: __init__.py

## Purpose
Orchestrates the prompt building, LLM call, citation validation, and post-generation guardrails for generating a BrainResponse.

## Key Components
- `SynthesisEngine` class: responsible for synthesizing answers from re-ranked chunks.
- `build_synthesis_prompt`: builds a synthesis prompt with confidence hint based on the source blocks.
- `LLMClient`: used to make LLM calls for answering questions.
- `validate_citations`: validates and cleans citations in the answer.

## Important Logic
- The `synthesise` method is the main entry point, which builds an answer from top-K re-ranked chunks.
  It applies various guardrails at different layers:
    - Layer 1: retrieval guardrails ( filtering low relevance, score gap, and source diversity).
    - Layer 2: prompt guardrails (confidence hint for LLM synthesis).
    - Layer 3: post-generation guardrails (validation and cleaning of citations).

## Dependencies
- `sentence_compressor`: used for context compression.
- `llm_client`: an instance of the `LLMClient` class.
- Various other classes and functions from the same package.

## Notes
- The code uses Markdown formatting to provide documentation and explanations.