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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

def decode_cf_email(encoded_string):
    """
    Decodes a Cloudflare-obfuscated email address.
    """
    try:
        r = int(encoded_string[:2], 16)
        email = ''.join([chr(int(encoded_string[i:i+2], 16) ^ r) for i in range(2, len(encoded_string), 2)])
        return email
    except (ValueError, TypeError):
        return None

def find_emails_and_links(session, url, base_domain):
    """
    Fetches a single page, scrapes for emails (including Cloudflare-protected), and internal links.
    Returns a tuple: (list of found emails, list of internal links).
    """
    emails = set()
    links = set()
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()

        # Check if content is HTML before parsing
        if 'text/html' not in response.headers.get('Content-Type', ''):
            return [], []

        soup = BeautifulSoup(response.text, 'lxml')

        # 1. Find emails with regex on the whole text
        found_emails = re.findall(EMAIL_REGEX, soup.get_text())
        for email in found_emails:
            if not email.endswith(('.png', '.jpg', '.gif', '.jpeg', '.css', '.js')):
                emails.add(email)

        # 2. Find and decode Cloudflare-protected emails
        for cf_email_tag in soup.find_all('a', href=lambda href: href and '/cdn-cgi/l/email-protection' in href):
            encoded_string = cf_email_tag['href'].split('#')[-1]
            decoded_email = decode_cf_email(encoded_string)
            if decoded_email:
                emails.add(decoded_email)

        # Also check for spans with data-cfemail
        for cf_span in soup.select('span.__cf_email__'):
            encoded_string = cf_span.get('data-cfemail')
            if encoded_string:
                decoded_email = decode_cf_email(encoded_string)
                if decoded_email:
                    emails.add(decoded_email)


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
    Uses a session to handle cookies and headers, and prioritizes specific pages.
    """
    original_domain = urlparse(base_url).netloc
    print(f"Scraping: {base_url} (Domain: {original_domain})")

    found_data = []
    visited_urls = set()
    pages_crawled = 0

    with requests.Session() as session:
        session.headers.update(HEADERS)

        # 1. Priority Scan
        print("  -> Checking priority pages...")
        priority_paths = ['/contact', '/contact-us', '/about-us', '/about', '/about-me']
        priority_urls = {urljoin(base_url, path) for path in priority_paths}
        priority_urls.add(base_url)

        links_for_general_crawl = set()

        for url in priority_urls:
            if url not in visited_urls and pages_crawled < MAX_PAGES_PER_DOMAIN:
                print(f"  Visiting priority page: {url}")
                visited_urls.add(url)
                pages_crawled += 1
                emails, new_links = find_emails_and_links(session, url, original_domain)
                for email in emails:
                    found_data.append({'email': email, 'source': url})
                links_for_general_crawl.update(new_links)

        # 2. If emails found on priority pages, stop and return them.
        if found_data:
            print(f"  -> Found {len(found_data)} email(s) on priority pages. Halting crawl.")
            return found_data

        # 3. If no emails found, proceed with a general crawl.
        print("  -> No emails on priority pages. Starting general crawl...")
        urls_to_visit = deque()
        for link in links_for_general_crawl:
            if link not in visited_urls:
                urls_to_visit.append(link)
                visited_urls.add(link)

        while urls_to_visit and pages_crawled < MAX_PAGES_PER_DOMAIN:
            current_url = urls_to_visit.popleft()
            pages_crawled += 1

            print(f"  [{pages_crawled}/{MAX_PAGES_PER_DOMAIN}] Visiting: {current_url}")
            emails, new_links = find_emails_and_links(session, current_url, original_domain)

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
