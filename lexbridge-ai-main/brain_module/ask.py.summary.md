# File: ask.py

## Purpose
Interactive test script for the Brain Module API. Allows users to ask questions, measure response times, and analyze cache performance.

## Key Components
- `ask` function: sends a question to the Brain Module API using HTTP POST requests.
- `print_result` function: formats and prints the response from the API.
- `load_questions` function: reads questions from a file named "questions.txt".
- `main` function: parses command-line arguments, connects to the API, and runs either single-question or batch modes.

## Important Logic
- The script checks if the Brain Module API is reachable using an HTTP GET request.
- In batch mode, it measures response times for each question and calculates cache hit rates.
- It uses a custom client from `httpx` library with a timeout of 180 seconds to handle slow responses from the API.

## Dependencies
- `httpx`: a modern HTTP client library.
- `argparse`: for parsing command-line arguments.

## Notes
- The script assumes that the Brain Module API is running on `http://127.0.0.1:8001`.
- It uses ANSI escape codes to colorize output in terminals that support it.