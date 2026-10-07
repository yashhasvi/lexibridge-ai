# File: enrich_playwright.py

## Purpose
Enriches a CSV file with conference data from event websites by parsing HTML content and extracting relevant details.

## Key Components
* `parse_html` function extracts data from HTML pages using BeautifulSoup.
* `process_row` function uses Playwright to navigate to each URL, wait for Cloudflare, and extract data from the page.
* `enrich_csv` function reads the input CSV file, processes each row in parallel using ThreadPoolExecutor, and writes the enriched rows to a new output CSV file.

## Important Logic
* The script uses multiple threads to process each row of the input CSV file in parallel.
* Each thread opens its own browser instance to navigate to each URL, which helps avoid issues with shared state between threads.
* The script waits for 5 attempts for Cloudflare to pass before proceeding to extract data from the page.

## Dependencies
* `playwright-sync-api` library is used for web scraping and automation.
* `bs4` (BeautifulSoup) library is used for HTML parsing.
* `csv` library is used for reading and writing CSV files.
* `concurrent.futures` library is used for parallel processing.

## Notes
* The script assumes that the input CSV file has at least 5 columns: URL, event ID, start date, end date, and deadline.
* The script preserves the original order of the rows in the output CSV file.