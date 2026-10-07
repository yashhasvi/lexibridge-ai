# extract_conferences.py

from bs4 import BeautifulSoup
import csv
import os

INPUT_FILE = "input.html"
OUTPUT_FILE = "conferences.csv"


def load_existing_links(csv_file):
    """Load existing links to avoid duplicates"""
    links = set()
    if os.path.isfile(csv_file):
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) >= 4:
                    links.add(row[3])
    return links


def extract_data(html_file):
    """Parse HTML and extract conference data"""
    with open(html_file, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    rows = soup.find_all("tr")
    data = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        # DATE
        date = cols[0].get_text(strip=True)

        # NAME + LINK
        conf_tag = cols[1].find("a")
        name = conf_tag.get_text(strip=True) if conf_tag else ""
        link = conf_tag.get("href", "") if conf_tag else ""

        # LOCATION
        location_tag = cols[2].find("a")
        location = location_tag.get_text(strip=True) if location_tag else ""
        location = " ".join(location.split())

        data.append([date, name, location, link])

    return data


def append_to_csv(data, csv_file):
    """Append new rows to CSV, avoid duplicates"""
    existing_links = load_existing_links(csv_file)
    new_data = [row for row in data if row[3] not in existing_links]

    file_exists = os.path.isfile(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["Date", "Conference", "Location", "Link"])

        writer.writerows(new_data)

    print(f"✅ Added {len(new_data)} new rows (skipped {len(data) - len(new_data)} duplicates)")


def main():
    data = extract_data(INPUT_FILE)
    append_to_csv(data, OUTPUT_FILE)


if __name__ == "__main__":
    main()
