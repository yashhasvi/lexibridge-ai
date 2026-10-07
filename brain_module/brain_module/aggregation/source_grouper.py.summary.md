# File: source_grouper.py

## Purpose
Groups chunks by their `source` field for downstream display.

## Key Components
- `group_by_source` function groups chunks by source name.
- `source_summary` function generates a string summarizing the number of chunks from each source.

## Important Logic
The `group_by_source` function uses a defaultdict to group chunks by source, and then converts it back to a regular dict. The `source_summary` function sorts the groups by key (source name) and joins the parts with commas.

## Dependencies
- `collections` module for defaultdict.
- `typing` module for type hints.

## Notes
This code is designed to be used in conjunction with other components, such as the ResponseFormatter, to display source information coherently. The synthesis prompt can reference each source coherently using this data.