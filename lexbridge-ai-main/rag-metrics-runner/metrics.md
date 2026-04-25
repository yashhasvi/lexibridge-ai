# Metrics Snapshot (M1 Pro Environment)

## Environment
- Hardware: Apple M1 Pro
- Constraint: CPU-bound inference (Ollama + cross-encoder reranker)

## Results

### Latency
- Avg: 14.7 sec
- Min: 4.6 sec
- Max: 25.9 sec

### Confidence
- Avg: 0.8258
- Issue: Not calibrated (values exceed 1.0)

### Retrieval
- Avg Sources: 2.4

### Cache
- Hit Rate: 20%

### Guardrails
- Low Alignment: 60%

---

## Interpretation

- Latency is primarily due to hardware constraints, not architectural inefficiency.
- Confidence scores are not normalized and require calibration.
- Retrieval depth is limited, impacting multi-hop reasoning.
- Cache efficiency is low and can be improved.
- Guardrail failures indicate weak grounding between query and retrieved context.

---

## Action Items

1. Normalize confidence scores
2. Improve retrieval (increase top_k, hybrid search)
3. Add semantic caching
4. Reduce reranker cost (conditional usage)
5. Improve grounding to reduce guardrail flags
