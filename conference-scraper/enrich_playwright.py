import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time

INPUT_CSV = "conferences.csv"
OUTPUT_CSV = "conferences_enriched.csv"

MAX_WORKERS = 3  # 🔥 IMPORTANT: keep low


# ----------------------------
# Parse HTML
# ----------------------------
def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "event_id": "",
        "start_date": "",
        "end_date": "",
        "deadline": "",
        "venue": "",
        "about": "",
        "email": "",
        "website": "",
        "contact": "",
        "organizer": "",
        "price": "",
    }

    cards = soup.find_all("div", class_="group/card")

    for card in cards:
        title_tag = card.find("h3")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        value = card.get_text(" ", strip=True).replace(title, "").strip()

        if "Event Serial ID" in title:
            data["event_id"] = value
        elif "Starting Date" in title:
            data["start_date"] = value
        elif "Ending Date" in title:
            data["end_date"] = value
        elif "Abstracts Deadline" in title:
            data["deadline"] = value
        elif "Venue" in title:
            data["venue"] = value
        elif "Event Enquiry Email Address" in title:
            data["email"] = value
        elif "Website" in title:
            link = card.find("a")
            data["website"] = link["href"] if link else ""
        elif "Contact Person" in title:
            data["contact"] = value
        elif "Organized by" in title:
            data["organizer"] = value
        elif "Price" in title:
            data["price"] = value

    # ABOUT
    about_section = soup.find("h3", string="About the Event/Conference")
    if about_section:
        parent = about_section.find_parent("div")
        if parent:
            p = parent.find("p")
            if p:
                data["about"] = p.get_text(strip=True)

    return data


# ----------------------------
# Worker (OWN browser per thread)
# ----------------------------

def process_row(row):
    url = row[3]
    print(f"🔍 {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # 🔥 IMPORTANT
            context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
            page = context.new_page()

            page.goto(url, timeout=60000)

            # 🔥 Wait for Cloudflare to pass
            for _ in range(5):
                content = page.content()

                if "Just a moment" not in content:
                    break

                print("⏳ Waiting for Cloudflare...")
                time.sleep(3)

            # Now wait for actual content
            page.wait_for_selector("text=Event Serial ID", timeout=30000)

            html = page.content()

            browser.close()

        details = parse_html(html)

        return row + [
            details["event_id"],
            details["start_date"],
            details["end_date"],
            details["deadline"],
            details["venue"],
            details["about"],
            details["email"],
            details["website"],
            details["contact"],
            details["organizer"],
            details["price"],
        ]

    except Exception as e:
        print(f"❌ Failed: {url} → {e}")
        return row + [""] * 11

# ----------------------------
# Main
# ----------------------------
def enrich_csv():
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[0]
    rows = reader[1:]

    new_cols = [
        "EventID", "StartDate", "EndDate", "Deadline",
        "VenueDetail", "About", "Email", "Website",
        "Contact", "Organizer", "Price"
    ]

    if len(header) < 5:
        header += new_cols

    enriched_rows = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_row, row) for row in rows]

        for future in as_completed(futures):
            enriched_rows.append(future.result())

    # preserve order
    enriched_rows.sort(key=lambda x: rows.index(x[:4]))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(enriched_rows)

    print("\n✅ Done!")


if __name__ == "__main__":
    enrich_csv()
