import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from .file_processor import process_file_url
from .page_analyzer import analyze_page_content, get_priority_pages
from .whois_lookup import get_whois_data
import time

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(SCRIPT_DIR, 'urls.txt')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'results.csv')
MAX_PAGES_PER_DOMAIN = 100
REQUEST_TIMEOUT = 15
PLAYWRIGHT_TIMEOUT = 30000 # 30 seconds
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1'
}
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
FILE_EXTENSIONS = ['.pdf', '.docx', '.doc', '.ppt', '.pptx', '.xls', '.xlsx']


def decode_cf_email(encoded_string):
    """Decodes Cloudflare-protected email addresses."""
    try:
        r = int(encoded_string[:2], 16)
        email = ''.join([chr(int(encoded_string[i:i+2], 16) ^ r) for i in range(2, len(encoded_string), 2)])
        return email
    except (ValueError, TypeError):
        return None

def parse_html_for_emails_and_links(html_content, url):
    """
    Parses HTML content to extract emails and various types of links.
    """
    emails = set()
    page_links = set()
    file_links = set()
    base_domain = urlparse(url).netloc
    soup = BeautifulSoup(html_content, 'lxml')

    # 1. Find standard emails with regex
    found_emails = re.findall(EMAIL_REGEX, soup.get_text())
    for email in found_emails:
        # Filter out emails that are likely image paths or other false positives
        if not email.lower().endswith(('.png', '.jpg', '.gif', '.jpeg', '.css', '.js', '.svg', '.webp')):
            emails.add(email)

    # 2. Find and decode Cloudflare-protected emails
    for cf_email_tag in soup.find_all('a', href=lambda href: href and '/cdn-cgi/l/email-protection' in href):
        encoded_string = cf_email_tag['href'].split('#')[-1]
        decoded_email = decode_cf_email(encoded_string)
        if decoded_email:
            emails.add(decoded_email)
    for cf_span in soup.select('span.__cf_email__'):
        encoded_string = cf_span.get('data-cfemail')
        if encoded_string:
            decoded_email = decode_cf_email(encoded_string)
            if decoded_email:
                emails.add(decoded_email)

    # 3. Find internal page links and document links
    for a_tag in soup.find_all('a', href=True):
        link = a_tag['href']
        # Try to resolve relative URLs
        try:
            full_link = urljoin(url, link)
        except ValueError:
            continue # Ignore malformed URLs

        # Clean fragment from URL
        full_link = full_link.split('#')[0]

        # Ensure it's a valid, crawlable link
        if not full_link.startswith(('http', 'https')):
            continue

        # Check for document links
        if any(full_link.lower().endswith(ext) for ext in FILE_EXTENSIONS):
            file_links.add(full_link)
        # Check if it's an internal page link to the same or a subdomain
        elif urlparse(full_link).netloc.endswith(base_domain):
            page_links.add(full_link)

    return list(emails), list(page_links), list(file_links)

def get_sitemap_urls(base_url, session=None, browser=None):
    """
    Finds and parses a sitemap to extract all unique URLs.
    Handles sitemap indexes and recursively fetches nested sitemaps.
    """
    sitemap_urls = set()
    urls_to_parse = set()
    parsed_sitemaps = set()

    # 1. Check robots.txt for Sitemap directive
    robots_url = urljoin(base_url, '/robots.txt')
    try:
        content = ""
        status = 0
        if browser:
            page = browser.new_page()
            try:
                response = page.goto(robots_url, timeout=PLAYWRIGHT_TIMEOUT, wait_until='domcontentloaded')
                if response:
                    content = page.content()
                    status = response.status
            finally:
                page.close()
        elif session:
            response = session.get(robots_url, timeout=REQUEST_TIMEOUT, verify=False)
            content = response.text
            status = response.status_code

        if status == 200:
            for line in content.splitlines():
                if line.lower().startswith('sitemap:'):
                    urls_to_parse.add(line.split(':', 1)[1].strip())
    except (requests.RequestException, PlaywrightError) as e:
        print(f"  -> Could not fetch or read robots.txt: {e}")

    # 2. If not in robots.txt, check common sitemap location
    if not urls_to_parse:
        urls_to_parse.add(urljoin(base_url, '/sitemap.xml'))

    # 3. Parse sitemaps (can be recursive for sitemap indexes)
    while urls_to_parse:
        sitemap_url = urls_to_parse.pop()
        if sitemap_url in parsed_sitemaps:
            continue

        print(f"  -> Parsing sitemap: {sitemap_url}")
        parsed_sitemaps.add(sitemap_url)

        try:
            content = b""
            status = 0
            if browser:
                page = browser.new_page()
                try:
                    response = page.goto(sitemap_url, timeout=PLAYWRIGHT_TIMEOUT, wait_until='domcontentloaded')
                    if response:
                        content = page.content().encode('utf-8')
                        status = response.status
                finally:
                    page.close()
            elif session:
                response = session.get(sitemap_url, timeout=REQUEST_TIMEOUT, verify=False)
                content = response.content
                status = response.status_code

            if status != 200:
                continue

            soup = BeautifulSoup(content, 'lxml-xml')
            if soup.find('sitemapindex'):
                for loc in soup.find_all('loc'):
                    urls_to_parse.add(loc.text.strip())
            else:
                for loc in soup.find_all('loc'):
                    sitemap_urls.add(loc.text.strip())

        except (requests.RequestException, PlaywrightError) as e:
            print(f"  -> Failed to fetch or parse sitemap {sitemap_url}: {e}")
        except Exception as e:
            print(f"  -> An unexpected error occurred while parsing {sitemap_url}: {e}")

    print(f"  -> Found {len(sitemap_urls)} URLs in sitemap(s).")
    return list(sitemap_urls)


def get_site_type(url):
    """Check if a site is JavaScript-heavy or simple HTML."""
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS, verify=False)
        response.raise_for_status()
        html = response.text
        # Simple check: if there's very little JS or links, it might need Playwright.
        # Or if we see clear signs of a JS framework.
        if len(re.findall(r'<script', html, re.IGNORECASE)) > 10 or "react" in html.lower():
            return "advanced"
        return "simple"
    except requests.RequestException:
        return "advanced" # Default to advanced if a simple request fails

def scrape_website(base_url, use_playwright):
    """Main function to scrape a single website."""
    original_domain = urlparse(base_url).netloc
    print(f"Scraping: {base_url} (Domain: {original_domain})")

    found_data = []

    # --- Crawling Setup ---
    q = deque([base_url])
    visited = {base_url}
    pages_scraped = 0

    # --- Priority Pages ---
    print("  -> Finding priority pages...")
    try:
        # Use requests for this initial check as it's faster
        response = requests.get(base_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
        response.raise_for_status()
        priority_links = get_priority_pages(response.text, base_url)
        # Add homepage and priority links to the front of the queue
        for link in reversed(priority_links):
            if link not in visited:
                q.appendleft(link)
                visited.add(link)
        print(f"  -> Found {len(priority_links)} potential priority pages.")
    except requests.RequestException as e:
        print(f"  -> Could not fetch homepage for priority links: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # --- WHOIS Lookup (Corrected Position) ---
        whois_contacts = get_whois_data(original_domain, browser)
        if whois_contacts:
            found_data.extend(whois_contacts)

        page = browser.new_page()

        while q and pages_scraped < MAX_PAGES_PER_DOMAIN:
            url = q.popleft()
            pages_scraped += 1

            progress = (pages_scraped / MAX_PAGES_PER_DOMAIN) * 100
            print(f"Progress: |{'█' * int(progress/2)}{'-' * (50 - int(progress/2))}| {progress:.1f}% Complete", end='\r')


            try:
                if use_playwright:
                    page.goto(url, wait_until='networkidle', timeout=PLAYWRIGHT_TIMEOUT)
                    html_content = page.content()
                else:
                    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
                    response.raise_for_status()
                    html_content = response.text

                emails, page_links, file_links = parse_html_for_emails_and_links(html_content, url)

                # General Analysis
                page_contacts = analyze_page_content(html_content, url)
                print(f"  -> Running general analysis on: {url}")
                if page_contacts:
                    print(f"  -> Found {len(page_contacts)} total potential contact(s) on {url}")
                    found_data.extend(page_contacts)

                for email in emails:
                    if not any(d.get('email') == email for d in found_data):
                        found_data.append({'email': email, 'name': '', 'source': url})

                for link in page_links:
                    if link not in visited:
                        visited.add(link)
                        q.append(link)

                for file_url in file_links:
                    if file_url not in visited:
                        visited.add(file_url)
                        print(f"  -> Processing document link: {file_url}")
                        try:
                            file_emails, file_names = process_file_url(file_url)
                            for email in file_emails:
                                if not any(d.get('email') == email for d in found_data):
                                    found_data.append({'email': email, 'name': ", ".join(file_names), 'source': file_url})
                        except Exception as e:
                            print(f"  -> Failed to download {file_url}. Error: {e}")

                # Halt condition
                if len(found_data) > 20: # Stop if we have a good number of contacts
                    print("\n  -> Sufficient contacts found. Halting crawl for this domain.")
                    break

                time.sleep(1) # Be respectful

            except PlaywrightError as e:
                print(f"\n  -> Playwright error on {url}: {e}")
            except requests.RequestException as e:
                print(f"\n  -> Request error on {url}: {e}")
            except Exception as e:
                print(f"\n  -> An unexpected error occurred on {url}: {e}")

        browser.close()
        print() # Newline after progress bar
    return found_data


def main():
    """Main function to run the scraper."""
    if not os.path.exists(URL_FILE):
        print(f"Error: Input file '{URL_FILE}' not found.")
        return

    with open(URL_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not urls:
        print(f"Input file '{URL_FILE}' is empty or all URLs are commented out.")
        return

    print(f"Found {len(urls)} base URLs to process.")

    final_results = []

    for url in urls:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Site type detection
        site_type = get_site_type(url)
        print(f"\n-> Site type for {url} detected as: {site_type}")

        scraped_data = scrape_website(url, use_playwright=(site_type == 'advanced'))

        for item in scraped_data:
            final_results.append({
                'Website': urlparse(url).netloc,
                'Found_Email': item.get('email'),
                'Found_Name': item.get('name', ''),
                'Source_URL': item.get('source', url)
            })

    if final_results:
        df = pd.DataFrame(final_results)
        # Clean up data before saving
        df.drop_duplicates(subset=['Website', 'Found_Email'], inplace=True)
        df.sort_values(by=['Website', 'Found_Name'], inplace=True)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"\nScraping complete. Results saved to '{OUTPUT_FILE}'.")
    else:
        print("\nScraping complete. No data was found.")

if __name__ == "__main__":
    main()
