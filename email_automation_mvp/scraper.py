import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(SCRIPT_DIR, 'urls.txt')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'results.csv')
MAX_PAGES_PER_DOMAIN = 20  # Limit the number of pages to crawl per website
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

def find_emails_and_links(url, base_domain):
    """
    Fetches a single page, scrapes it for email addresses and internal links.
    Returns a tuple: (list of found emails, list of internal links).
    """
    emails = set()
    links = set()
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        # Check if content is HTML before parsing
        if 'text/html' not in response.headers.get('Content-Type', ''):
            return [], []

        soup = BeautifulSoup(response.text, 'lxml')

        # Find emails
        found_emails = re.findall(EMAIL_REGEX, soup.get_text())
        for email in found_emails:
            if not email.endswith(('.png', '.jpg', '.gif', '.jpeg', '.css', '.js')):
                emails.add(email)

        # Find internal links
        for a_tag in soup.find_all('a', href=True):
            link = urljoin(url, a_tag['href'])
            # Clean link (remove fragment)
            link = link.split('#')[0]
            # Check if it's a valid, same-domain link
            if urlparse(link).netloc == base_domain and link.startswith('http'):
                links.add(link)

    except requests.RequestException as e:
        print(f"   -> Could not access {url}. Error: {e}")

    return list(emails), list(links)

def scrape_website(base_url):
    """
    Crawls a website starting from the base_url to find email addresses.
    """
    original_domain = urlparse(base_url).netloc
    print(f"Scraping: {base_url} (Domain: {original_domain})")

    urls_to_visit = deque([base_url])
    visited_urls = set([base_url])
    found_data = [] # List of {'email': email, 'source': url}

    pages_crawled = 0
    while urls_to_visit and pages_crawled < MAX_PAGES_PER_DOMAIN:
        current_url = urls_to_visit.popleft()
        pages_crawled += 1

        print(f"  [{pages_crawled}/{MAX_PAGES_PER_DOMAIN}] Visiting: {current_url}")

        emails, new_links = find_emails_and_links(current_url, original_domain)

        for email in emails:
            found_data.append({'email': email, 'source': current_url})

        for link in new_links:
            if link not in visited_urls:
                visited_urls.add(link)
                urls_to_visit.append(link)

    return found_data

def main():
    """
    Main function to run the scraper.
    Reads URLs, crawls them, and saves results to a CSV.
    """
    if not os.path.exists(URL_FILE):
        print(f"Error: Input file '{URL_FILE}' not found.")
        return

    with open(URL_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(f"Error: Input file '{URL_FILE}' is empty.")
        return

    print(f"Found {len(urls)} base URLs to process.")

    all_results = []
    for base_url in urls:
        # Ensure base_url has a scheme
        if not urlparse(base_url).scheme:
            base_url = 'https://' + base_url

        scraped_data = scrape_website(base_url)

        if scraped_data:
            # Use a set to store unique email-source pairs for this website
            unique_emails_for_site = set()
            for item in scraped_data:
                # Add the base website URL to the results
                if (item['email']) not in unique_emails_for_site:
                    all_results.append({
                        'Website': urlparse(base_url).netloc,
                        'Found_Email': item['email'],
                        'Source_URL': item['source']
                    })
                    unique_emails_for_site.add(item['email'])
        else:
            all_results.append({
                'Website': urlparse(base_url).netloc,
                'Found_Email': 'No email found',
                'Source_URL': base_url
            })

    if all_results:
        df = pd.DataFrame(all_results)
        # Remove duplicate emails found across different source URLs for the same website
        df.drop_duplicates(subset=['Website', 'Found_Email'], inplace=True)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"\nScraping complete. Results saved to '{OUTPUT_FILE}'.")
    else:
        print("\nScraping complete. No data to save.")

if __name__ == "__main__":
    main()
