import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- Configuration ---
# Get the absolute path of the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(SCRIPT_DIR, 'urls.txt')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'results.csv')
PAGES_TO_CHECK = ['/contact', '/contact-us', '/about-us', '/about']
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# Regex to find email addresses
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

def find_emails_on_page(url):
    """Fetches a single page and scrapes it for email addresses."""
    emails = set()
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.text, 'lxml')
        found_emails = re.findall(EMAIL_REGEX, soup.get_text())
        for email in found_emails:
            # Simple filter to avoid common false positives
            if not email.endswith(('.png', '.jpg', '.gif', '.jpeg')):
                emails.add(email)
    except requests.RequestException as e:
        print(f"   -> Could not access {url}. Error: {e}")
    return list(emails)

def scrape_website(base_url):
    """
    Scrapes a website for email addresses by checking a predefined list of pages.
    """
    print(f"Scraping: {base_url}")
    # Ensure base_url has a scheme
    if not urlparse(base_url).scheme:
        base_url = 'https://' + base_url

    all_found_emails = set()

    # First, check the homepage itself
    homepage_emails = find_emails_on_page(base_url)
    all_found_emails.update(homepage_emails)

    # Then check other common pages
    for page in PAGES_TO_CHECK:
        url_to_check = urljoin(base_url, page)
        page_emails = find_emails_on_page(url_to_check)
        all_found_emails.update(page_emails)

    return list(all_found_emails)

def main():
    """
    Main function to run the scraper.
    Reads URLs from a file, scrapes them, and saves results to a CSV.
    """
    if not os.path.exists(URL_FILE):
        print(f"Error: Input file '{URL_FILE}' not found.")
        print("Please create it and add one website URL per line.")
        return

    with open(URL_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(f"Error: Input file '{URL_FILE}' is empty.")
        return

    print(f"Found {len(urls)} URLs to process.")

    results = []
    for url in urls:
        emails = scrape_website(url)
        if emails:
            for email in emails:
                results.append({'Website': url, 'Found_Email': email})
        else:
            results.append({'Website': url, 'Found_Email': 'No email found'})

    if results:
        df = pd.DataFrame(results)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"\nScraping complete. Results saved to '{OUTPUT_FILE}'.")
    else:
        print("\nScraping complete. No data to save.")

if __name__ == "__main__":
    main()
