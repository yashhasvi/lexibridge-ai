# File: `__init__.py`

## Purpose
Defines a public façade for combining intent classification and complexity scoring.

## Key Components
* `QueryRouter`: The main entry-point for routing queries.
* `IntentClassifier` and `ComplexityScorer`: Combined to classify query intent and score complexity.

## Important Logic
* Initializes the `_classifier` and `_scorer` attributes in the `__init__` method.
* The `route` method uses the `_scorer` attribute to plan a FetcherPlan based on the input query string.

## Dependencies
* `.intent_classifier`: Contains IntentClassifier and QueryIntent classes.
* `.complexity_scorer`: Contains ComplexityScorer, FetcherPlan, and FetcherName classes.

## Notes
* The `__all__` variable defines the public API of this module.