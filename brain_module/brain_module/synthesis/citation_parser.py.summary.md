# File: citation_parser.py

## Purpose
Extract inline citation markers from an LLM answer, map them back to SourceCard objects, and validate that every cited index exists in the source list.

## Key Components

* `_CITATION_RE` regular expression for finding citation indices
* `extract_cited_indices(answer)`: returns a sorted list of unique citation indices found in the input string
* `validate_citations(answer, source_cards, remove_invalid=True)`:
	+ checks that every [N] in the answer maps to a valid source card
	+ removes out-of-range citations from the text if `remove_invalid` is True
	+ returns a cleaned version of the answer and a list of invalid indices
* `citations_to_source_cards(answer, source_cards)`: returns only the SourceCards that are actually cited in the input string

## Important Logic

* The `_CITATION_RE` regular expression is used to find citation indices in the answer string.
* In `validate_citations`, the `extract_cited_indices` function is used to get a set of unique citation indices, which is then compared to the valid indices from the source cards.
* If any invalid indices are found, they are removed from the answer text using a regular expression.

## Dependencies

* `re`: for regular expressions
* `typing`: for type hints
* `SourceCard` class (not shown): represents a single source card with a citation index

## Notes

* The code assumes that the input string contains inline citation markers in the format [N], where N is a positive integer.
* The `remove_invalid` parameter in `validate_citations` allows for the removal of out-of-range citations from the answer text.