# File: extract_table.py

## Purpose
Extract conferences' data from an HTML table and save it to a CSV file.

## Key Components

* `extract_data(html_file)`: Parse HTML and extract conference data.
* `append_to_csv(data, csv_file)`: Append new rows to the CSV file while avoiding duplicates.
* `load_existing_links(csv_file)`: Load existing links from the CSV file to avoid duplicates.

## Important Logic

* The script uses BeautifulSoup to parse the HTML table and extract conference data.
* It uses a set to keep track of existing links in the CSV file, ensuring that no duplicate rows are added.
* The `append_to_csv` function appends new rows to the CSV file while maintaining the header row.

## Dependencies

* `beautifulsoup4`: For parsing HTML tables.
* `csv`: For reading and writing CSV files.
* `os`: For working with file paths and checking if a file exists.

## Notes

* The script assumes that the input HTML file has a table structure similar to the one parsed by BeautifulSoup.
* The output CSV file will be updated with new rows, while existing links are skipped to avoid duplicates.