# File: formatter.py

## Purpose
Converts a `BrainResponse` object to various output formats, including dict/JSON, Markdown, and plain text.

## Key Components
- `ResponseFormatter`: A stateless class that contains methods for formatting responses.
- `to_dict()`, `to_json()`, `to_markdown()`, and `to_plain_text()`: Methods for converting responses to different output formats.

## Important Logic
The class uses the `asdict()` function from the `dataclasses` module to convert `BrainResponse` objects to dictionaries. It also utilizes the `json` module to handle JSON serialization.

## Dependencies
- `pydantic`
- `dataclasses`
- `typing`

## Notes
This module is designed to be used in conjunction with other modules that work with brain responses, such as those from the `schema` module.