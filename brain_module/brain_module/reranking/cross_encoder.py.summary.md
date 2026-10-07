# File: cross_encoder.py

## Purpose
Re-ranks candidate chunks against a query using a cross-encoder model, returning the top-K.

## Key Components
* `CrossEncoderReranker` class:
	+ Re-ranks candidates based on cross-encoder scores
	+ Supports lazy loading of models
* `_load_cross_encoder` function: loads a cross-encoder model from a given name
* `_sigmoid` function: normalizes cross-encoder scores to [0, 1] via sigmoid

## Important Logic
* `rerank` method:
	+ Takes query and candidates as input
	+ Uses cross-encoder to score candidates and returns top-K
	+ Falls back to RRF score if cross-encoder prediction fails

## Dependencies
* `sentence_transformers.cross_encoder`
* `numpy`

## Notes
* Two models are available: default `cross-encoder/ms-marco-MiniLM-L-6-v2` and alternative `BAAI/bge-reranker-v2-m3` (multilingual, higher quality)