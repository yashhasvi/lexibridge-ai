"""
RagasEvaluator — wraps the Ragas library to evaluate BrainResponse quality.

Metrics computed:
  - faithfulness:         Is every claim in the answer supported by the contexts?
  - context_precision:   Are the retrieved contexts relevant to the question?
  - answer_relevancy:    Does the answer actually address the question?

Usage::

    evaluator = RagasEvaluator()

    # Single response
    scores = await evaluator.evaluate_one(brain_response)

    # Batch (dataset)
    report = await evaluator.evaluate_dataset(
        questions=["What is X?", ...],
        responses=[brain_resp1, brain_resp2, ...],
    )
"""
from __future__ import annotations

import logging
from typing import Any

from ..response.schema import BrainResponse

logger = logging.getLogger(__name__)


def _brain_response_to_ragas_row(response: BrainResponse) -> dict[str, Any]:
    """Convert a BrainResponse to the Ragas EvaluationDataset row format."""
    return {
        "question": response.question,
        "answer": response.answer,
        "contexts": [s.excerpt for s in response.sources],
        "ground_truth": "",  # not available at inference time
    }


class RagasEvaluator:
    """
    Thin wrapper around ragas.evaluate().

    If Ragas is not installed or the LLM is not configured, the evaluator
    returns empty scores with a warning rather than raising.
    """

    def __init__(self, llm_model: str = "gpt-4o") -> None:
        self._llm_model = llm_model
        self._metrics: list[Any] | None = None

    def _load_metrics(self) -> list[Any]:
        if self._metrics is not None:
            return self._metrics
        try:
            from ragas.metrics import (  # type: ignore[import-untyped]
                answer_relevancy,
                context_precision,
                faithfulness,
            )
            self._metrics = [faithfulness, context_precision, answer_relevancy]
            logger.info("Ragas metrics loaded.")
        except ImportError:
            logger.warning("ragas not installed — evaluation disabled. pip install ragas")
            self._metrics = []
        return self._metrics

    async def evaluate_one(
        self,
        response: BrainResponse,
    ) -> dict[str, float]:
        """Evaluate a single BrainResponse. Returns metric_name → score dict."""
        metrics = self._load_metrics()
        if not metrics:
            return {}

        return await self._run_ragas(
            questions=[response.question],
            answers=[response.answer],
            contexts=[[s.excerpt for s in response.sources]],
        )

    async def evaluate_dataset(
        self,
        questions: list[str],
        responses: list[BrainResponse],
    ) -> dict[str, float]:
        """Evaluate a batch of responses — more efficient than calling evaluate_one repeatedly."""
        metrics = self._load_metrics()
        if not metrics:
            return {}

        return await self._run_ragas(
            questions=questions,
            answers=[r.answer for r in responses],
            contexts=[[s.excerpt for s in r.sources] for r in responses],
        )

    async def _run_ragas(
        self,
        questions: list[str],
        answers: list[str],
        contexts: list[list[str]],
    ) -> dict[str, float]:
        try:
            from datasets import Dataset  # type: ignore[import-untyped]
            from ragas import evaluate  # type: ignore[import-untyped]
        except ImportError:
            return {}

        data = {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": [""] * len(questions),
        }
        dataset = Dataset.from_dict(data)

        try:
            result = evaluate(dataset, metrics=self._metrics)  # type: ignore[arg-type]
            scores: dict[str, float] = {}
            for metric in self._metrics:
                name = metric.name if hasattr(metric, "name") else str(metric)
                val = result.get(name)
                if val is not None:
                    scores[name] = round(float(val), 4)
            logger.info("Ragas evaluation complete: %s", scores)
            return scores
        except Exception as exc:
            logger.error("Ragas evaluation failed: %s", exc)
            return {}
