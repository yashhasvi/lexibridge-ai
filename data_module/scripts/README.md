# Folder: scripts

## Overview

This folder contains the following files and their summaries.

## Files

### export_to_neo4j_admin.py

# File: export_to_neo4j_admin.py

## Purpose
Export a graph from NetworkX pickle to CSV files that can be imported into Neo4j using the `neo4j-admin` tool.

## Key Components
- The script exports two CSV files: `nodes.csv` and `relationships.csv`.
- These CSV files are used as input for the `neo4j-admin database import full` command.
- The script also creates indexes in Neo4j after import to enable fast lookups.

## Important Logic
- The `export_csv` function loads a NetworkX graph from a pickle file, writes nodes and relationships to CSV files, and logs progress.
- The `run_import` function stops Neo4j, runs the `neo4j-admin database import full` command with the generated CSV files, starts Neo4j again, and waits for it to come online.
- The `create_indexes` function creates indexes in Neo4j after import.

## Dependencies
- NetworkX
- Pickle
- CSV
- Gzip
- Subprocess (for running `neo4j-admin`)
- Neo4j Bolt driver
- Logging

## Notes
- This script requires the `neo4j-admin` tool to be installed and configured on the system.
- The script assumes that a NetworkX graph is stored in a pickle file at a default location (`DEFAULT_GRAPH`) and that the CSV files should be generated at another default location (`DEFAULT_CSV_DIR`). These locations can be overridden using command-line arguments.

---

### export_to_neo4j.py

# File: export_to_neo4j.py

## Purpose
Export a NetworkX graph stored as `graph.pkl.gz` to Neo4j, allowing for two modes: sampling the top-N most-connected nodes and their mutual edges, or exporting every node and edge.

## Key Components
* The script uses Python's `argparse` library to parse command-line arguments, including the path to the graph file, Neo4j connection details, batch size, mode (sample or full), and number of nodes for sampling.
* It loads the graph from the specified file using `pickle`, then builds two payloads: one for nodes and one for edges. The node payload includes entity information, while the edge payload contains relationship data.
* The script connects to Neo4j using the provided connection details and wipes any existing data if necessary.
* It imports the nodes and edges into Neo4j using Cypher queries.

## Important Logic
The key logic in this script is in the `export` function, where it:
	+ Loads the graph from the specified file.
	+ Determines whether to use sample mode or full mode based on user input.
	+ Builds the node payload by iterating over all nodes and creating a dictionary with entity information for each one.
	+ Builds the edge payload by iterating over all edges and creating a dictionary with relationship data for each one.
	+ Connects to Neo4j, wipes any existing data if necessary, and imports the nodes and edges.

## Dependencies
* NetworkX (`graph.pkl.gz`)
* Neo4j driver (via `neo4j` library)
* Python's `argparse` library

## Notes
The script provides two modes: "sample" and "full". Sample mode exports only the top-N most-connected nodes and their mutual edges, while full mode exports every node and edge. The number of nodes to include in sample mode is specified using the `--top-n` argument.

---

