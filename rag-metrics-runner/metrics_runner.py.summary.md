# File: metrics_runner.py

## Purpose
Measure and report various metrics from API calls, including latency, confidence, sources, cache hits, intent distribution, model usage, reranker usage, and guardrail flags.

## Key Components
- `call_api` function: makes API call to retrieve data for a given question.
- `QUERIES` list: predefined set of questions to be asked to the API.
- Metrics aggregation logic: calculates various metrics from the retrieved data.

## Important Logic
- The script iterates over the `QUERIES` list and makes an API call for each question using the `call_api` function.
- The retrieved data is stored in the `results` list, which is then used to calculate various metrics such as latency, confidence, sources, cache hits, intent distribution, model usage, reranker usage, and guardrail flags.

## Dependencies
- `requests` library: for making API calls.
- `statistics` library: for calculating mean values of metrics.
- `Counter` class from `collections` library: for counting occurrences of intent, model, and reranker usage.

## Notes
- The script assumes that the API URL and questions are hardcoded in the `QUERIES` list.
- The script prints the calculated metrics to the console.