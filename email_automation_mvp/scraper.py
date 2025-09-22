import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from file_processor import process_file_url

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(SCRIPT_DIR, 'urls.txt')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'results.csv')
MAX_PAGES_PER_DOMAIN = 100
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
}
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

def decode_cf_email(encoded_string):
    try:
        r = int(encoded_string[:2], 16)
        email = ''.join([chr(int(encoded_string[i:i+2], 16) ^ r) for i in range(2, len(encoded_string), 2)])
        return email
    except (ValueError, TypeError):
        return None

def parse_html_for_emails_and_links(html_content, url):
    emails = set()
    page_links = set()
    file_links = set()
    base_domain = urlparse(url).netloc
    soup = BeautifulSoup(html_content, 'lxml')
    file_extensions = ['.pdf', '.docx', '.ppt', '.pptx']

    # 1. Find emails with regex
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
    for cf_span in soup.select('span.__cf_email__'):
        encoded_string = cf_span.get('data-cfemail')
        if encoded_string:
            decoded_email = decode_cf_email(encoded_string)
            if decoded_email:
                emails.add(decoded_email)

    # 3. Find internal page links and document links
    for a_tag in soup.find_all('a', href=True):
        link = urljoin(url, a_tag['href'])
        link = link.split('#')[0]

        if not link.startswith('http'):
            continue

        # Check if the link has a file extension for documents
        if any(link.lower().endswith(ext) for ext in file_extensions):
            file_links.add(link)
        # Check if it's an internal page link to the same domain
        elif urlparse(link).netloc == base_domain:
            page_links.add(link)

    return list(emails), list(page_links), list(file_links)

def get_sitemap_urls(base_url, session=None, browser=None):
    """
    Finds and parses a sitemap to extract all unique URLs.
    Handles sitemap indexes and recursively fetches nested sitemaps.
    Works with both requests.Session and Playwright Browser.
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
                response = page.goto(robots_url, timeout=10000, wait_until='domcontentloaded')
                if response:
                    content = page.content()
                    status = response.status
            finally:
                page.close()
        elif session:
            response = session.get(robots_url, timeout=10)
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
                    response = page.goto(sitemap_url, timeout=10000, wait_until='domcontentloaded')
                    if response:
                        content = page.content().encode('utf-8') # BeautifulSoup expects bytes for XML
                        status = response.status
                finally:
                    page.close()
            elif session:
                response = session.get(sitemap_url, timeout=10)
                content = response.content
                status = response.status_code

            if status != 200:
                continue

            soup = BeautifulSoup(content, 'lxml-xml')

            # Check for sitemap index
            sitemap_tags = soup.find_all('sitemap')
            if sitemap_tags:
                for tag in sitemap_tags:
                    loc = tag.find('loc')
                    if loc:
                        urls_to_parse.add(loc.text.strip())
            else:
                # Standard sitemap
                url_tags = soup.find_all('url')
                for tag in url_tags:
                    loc = tag.find('loc')
                    if loc:
                        sitemap_urls.add(loc.text.strip())

        except (requests.RequestException, PlaywrightError) as e:
            print(f"  -> Failed to fetch or parse sitemap {sitemap_url}: {e}")
        except Exception as e:
            print(f"  -> An unexpected error occurred while parsing {sitemap_url}: {e}")

    print(f"  -> Found {len(sitemap_urls)} URLs in sitemap(s).")
    return list(sitemap_urls)


def find_priority_links(html_content, base_url):
    """
    Parses HTML to find links that likely lead to contact, about, or team pages.
    """
    soup = BeautifulSoup(html_content, 'lxml')
    priority_links = set()
    keywords = [
        'contact', 'about', 'team', 'career', 'jobs', 'support', 'help',
        'press', 'media', 'news', 'impressum', 'legal', 'privacy',
        'contact-us', 'about-us', 'our-team', 'get-in-touch',
        'contacto', 'quienes-somos', 'equipo', 'carrera',
        'kontakt', 'ueber-uns', 'über-uns',
        'contato', 'sobre',
        'contactez-nous', 'a-propos', 'equipe'
    ]

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].lower()
        link_text = a_tag.get_text().lower()

        if any(keyword in href for keyword in keywords) or any(keyword in link_text for keyword in keywords):
            full_url = urljoin(base_url, a_tag['href'])
            # Basic validation to ensure it's a real link
            if urlparse(full_url).scheme in ['http', 'https']:
                priority_links.add(full_url)

    print(f"  -> Found {len(priority_links)} potential priority pages from homepage.")
    return list(priority_links)


def scrape_website(base_url, playwright_browser):
    original_domain = urlparse(base_url).netloc
    print(f"Scraping: {base_url} (Domain: {original_domain})")

    # --- Mode Detection ---
    print("  -> Checking site type (Simple vs JavaScript-heavy)...")
    use_playwright = False
    initial_file_links = []
    try:
        with requests.Session() as initial_session:
            initial_session.headers.update(HEADERS)
            response = initial_session.get(base_url, timeout=10)
            response.raise_for_status()
            html_content = response.text
            initial_emails, initial_links, initial_file_links = parse_html_for_emails_and_links(html_content, base_url)

            if not initial_links and not initial_file_links:
                print("  -> No links found with simple request. Switching to Advanced Mode (Playwright).")
                use_playwright = True
            elif not initial_emails and "email-protection" in html_content:
                print("  -> Email obfuscation detected and no emails found. Switching to Advanced Mode (Playwright).")
                use_playwright = True
            else:
                print("  -> Simple site detected. Using fast mode.")
    except requests.RequestException as e:
        print(f"  -> Initial check failed: {e}. Assuming advanced site.")
        use_playwright = True

    # --- Start Crawl ---
    found_data = []
    visited_urls = set()
    pages_crawled = 0
    processed_file_urls = set()

    session = requests.Session() if not use_playwright else None
    if session:
        session.headers.update(HEADERS)

    page = playwright_browser.new_page() if use_playwright else None
    priority_urls = set()

    # Process any file links found during mode detection
    for file_url in initial_file_links:
        if file_url not in processed_file_urls:
            file_emails, file_names = process_file_url(file_url)
            names_str = ", ".join(file_names)
            for email in file_emails:
                found_data.append({'email': email, 'name': names_str, 'source': file_url})
            processed_file_urls.add(file_url)

    try:
        # --- Homepage Fetch and Priority Link Discovery ---
        homepage_html = ""
        if use_playwright:
            page.goto(base_url, timeout=20000)
            homepage_html = page.content()
        elif 'html_content' in locals(): # Use content from initial check if available
            homepage_html = html_content
        else: # Fetch if initial check was skipped
            response = session.get(base_url, timeout=10)
            response.raise_for_status()
            homepage_html = response.text

        priority_urls = set(find_priority_links(homepage_html, base_url))
        priority_urls.add(base_url) # Ensure homepage is always scanned

        # 1. Priority Scan
        print("  -> Checking priority pages...")
        links_for_general_crawl = set()

        for url in sorted(list(priority_urls)):
            if url in visited_urls or pages_crawled >= MAX_PAGES_PER_DOMAIN:
                continue

            print(f"  Visiting priority page: {url}")
            visited_urls.add(url)
            pages_crawled += 1

            try:
                html_content = ""
                if use_playwright:
                    page.goto(url, timeout=20000)
                    html_content = page.content()
                else:
                    response = session.get(url, timeout=10)
                    response.raise_for_status()
                    html_content = response.text

                emails, page_links, file_links = parse_html_for_emails_and_links(html_content, url)
                for email in emails:
                    found_data.append({'email': email, 'name': '', 'source': url})
                links_for_general_crawl.update(page_links)

                # Process file links found on priority page
                for file_url in file_links:
                    if file_url not in processed_file_urls:
                        file_emails, file_names = process_file_url(file_url)
                        names_str = ", ".join(file_names)
                        for email in file_emails:
                            found_data.append({'email': email, 'name': names_str, 'source': file_url})
                        processed_file_urls.add(file_url)

            except (requests.RequestException, PlaywrightError) as e:
                print(f"   -> Could not access {url}. Error: {e}")

        # 2. Conditional continuation
        # Check for emails before continuing to full crawl
        if any(item['email'] for item in found_data):
            print(f"  -> Found {len([item for item in found_data if item['email']])} email(s) on priority pages. Halting crawl for this domain.")
            return found_data

        # 3. Sitemap Crawl
        print("  -> No emails on priority pages. Attempting sitemap crawl...")
        sitemap_urls = []
        if use_playwright:
            sitemap_urls = get_sitemap_urls(base_url, browser=playwright_browser)
        else:
            sitemap_urls = get_sitemap_urls(base_url, session=session)

        urls_to_visit_set = set(sitemap_urls) if sitemap_urls else links_for_general_crawl
        urls_to_visit = deque(list(urls_to_visit_set - visited_urls)) # Use list to make it orderable

        if sitemap_urls:
            print(f"  -> Proceeding with {len(urls_to_visit)} URLs from sitemap.")
        else:
            print("  -> No sitemap found or parsed. Proceeding with general link crawl...")


        # 4. Main Crawl (unified for sitemap or general links)
        while urls_to_visit and pages_crawled < MAX_PAGES_PER_DOMAIN:
            current_url = urls_to_visit.popleft()
            if current_url in visited_urls:
                continue

            # Ensure we only crawl pages within the original domain
            current_netloc = urlparse(current_url).netloc.replace('www.', '')
            normalized_original_domain = original_domain.replace('www.', '')
            if current_netloc != normalized_original_domain:
                continue

            print(f"  [{pages_crawled + 1}/{MAX_PAGES_PER_DOMAIN}] Visiting: {current_url}")
            visited_urls.add(current_url)
            pages_crawled += 1

            try:
                html_content = ""
                if use_playwright:
                    page.goto(current_url, timeout=20000)
                    html_content = page.content()
                else:
                    response = session.get(current_url, timeout=10)
                    response.raise_for_status()
                    html_content = response.text

                emails, page_links, file_links = parse_html_for_emails_and_links(html_content, current_url)
                for email in emails:
                    found_data.append({'email': email, 'name': '', 'source': current_url})

                # Process file links found on this page
                for file_url in file_links:
                    if file_url not in processed_file_urls:
                        file_emails, file_names = process_file_url(file_url)
                        names_str = ", ".join(file_names)
                        for email in file_emails:
                            found_data.append({'email': email, 'name': names_str, 'source': file_url})
                        processed_file_urls.add(file_url)

                # In sitemap mode, we don't add new links to the queue
                if not sitemap_urls:
                    for link in page_links:
                        if link not in visited_urls:
                            urls_to_visit.append(link)

            except (requests.RequestException, PlaywrightError) as e:
                print(f"   -> Could not access {current_url}. Error: {e}")

    finally:
        if page:
            page.close()
        if session:
            session.close()

    return found_data

def main():
    if not os.path.exists(URL_FILE):
        print(f"Error: Input file '{URL_FILE}' not found.")
        return

    with open(URL_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(f"Error: Input file '{URL_FILE}' is empty.")
        return

    print(f"Found {len(urls)} base URLs to process.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        all_results = []
        for base_url in urls:
            if not urlparse(base_url).scheme:
                base_url = 'https://' + base_url

            scraped_data = scrape_website(base_url, browser)

            if scraped_data:
                for item in scraped_data:
                    all_results.append({
                        'Website': urlparse(base_url).netloc,
                        'Found_Email': item['email'],
                        'Found_Name': item.get('name', ''),
                        'Source_URL': item['source']
                    })
            else:
                all_results.append({
                    'Website': urlparse(base_url).netloc,
                    'Found_Email': 'No email found',
                    'Found_Name': '',
                    'Source_URL': base_url
                })

        browser.close()

    if all_results:
        # Define column order for the CSV
        columns = ['Website', 'Found_Email', 'Found_Name', 'Source_URL']
        df = pd.DataFrame(all_results)

        # Guard against empty dataframe if all results were "No email found"
        if 'Found_Name' not in df.columns:
            df['Found_Name'] = ''

        # Reorder columns to ensure 'Found_Name' is included correctly
        df = df[columns]

        # Prioritize entries with names by sorting before dropping duplicates
        df['name_len'] = df['Found_Name'].str.len()
        df.sort_values(by='name_len', ascending=False, inplace=True)
        df.drop(columns=['name_len'], inplace=True)

        df.drop_duplicates(subset=['Website', 'Found_Email'], inplace=True)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"\nScraping complete. Results saved to '{OUTPUT_FILE}'.")
    else:
        print("\nScraping complete. No data to save.")

if __name__ == "__main__":
    main()
