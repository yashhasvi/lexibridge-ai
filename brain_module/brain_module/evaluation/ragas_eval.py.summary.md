# File: ragas_eval.py

## Purpose
Evaluates the quality of BrainResponse using the Ragas library.

## Key Components
- `RagasEvaluator` class: Wraps the Ragas library to evaluate BrainResponse quality.
- `_brain_response_to_ragas_row`: Converts a BrainResponse to Ragas EvaluationDataset row format.
- `evaluate_one`: Evaluates a single BrainResponse and returns metric scores.
- `evaluate_dataset`: Evaluates a batch of responses and returns metric scores.

## Important Logic
- The evaluator loads the Ragas metrics and evaluates the BrainResponse quality using the `_run_ragas` method.
- The `_load_metrics` method is used to load the Ragas metrics, and if they are not available, it returns empty scores with a warning message.

## Dependencies
- `ragas`: Required for evaluation
- `datasets`: Required for Ragas evaluation

## Notes
- If Ragas is not installed or the LLM model is not configured, the evaluator returns empty scores with a warning message.
- The evaluator uses asynchronous methods to evaluate BrainResponse quality.