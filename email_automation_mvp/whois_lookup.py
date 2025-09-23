"""
This module contains functions for looking up WHOIS information for a domain.
"""
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
}

def parse_whois_text(text):
    """Parses raw WHOIS text to extract contact information."""
    contacts = []

    # Regex to find contact blocks (Admin, Tech, etc.)
    contact_patterns = re.compile(r"(Administrative Contact:|Technical Contact:|Registrant:)\n([\s\S]*?)(?=\n\n|Domain record|----------------)", re.IGNORECASE)

    email_regex = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

    for match in contact_patterns.finditer(text):
        contact_type = match.group(1).strip(':')
        contact_details = match.group(2)

        name_match = re.search(r'^\s*(.*?)\n', contact_details)
        name = name_match.group(1).strip() if name_match else "N/A"

        emails = re.findall(email_regex, contact_details)

        for email in emails:
            contacts.append({
                'email': email,
                'name': name,
                'source': f'WHOIS ({contact_type})'
            })

    return contacts

def get_whois_data(domain):
    """
    Scrapes WHOIS information for a given domain from whois.com.
    """
    print(f"  -> Performing WHOIS lookup for {domain}...")
    found_contacts = []
    url = f"https://www.whois.com/whois/{domain}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        # Check for raw text format (common for .edu)
        raw_text_pre = soup.find('pre', class_='df-raw')
        if raw_text_pre:
            # Replace image-obfuscated emails before getting text
            for img in raw_text_pre.find_all('img', class_='email'):
                img.replace_with("protected-email") # Use a valid email username placeholder

            whois_text = raw_text_pre.get_text()
            found_contacts = parse_whois_text(whois_text)
        else:
            # Fallback to structured div format
            contact_blocks = soup.find_all('div', class_='df-block')
            for block in contact_blocks:
                heading = block.find('div', class_='df-heading')
                if not heading:
                    continue

                contact_type = ""
                if "Registrant Contact" in heading.text:
                    contact_type = "Registrant"
                elif "Admin Contact" in heading.text:
                    contact_type = "Admin"
                elif "Technical Contact" in heading.text:
                    contact_type = "Technical"
                elif "Registrar Information" in heading.text:
                    abuse_email_row = block.find(lambda tag: tag.name == 'div' and 'Abuse Email' in tag.text and 'df-label' in tag.get('class', []))
                    if abuse_email_row:
                        email_div = abuse_email_row.find_next_sibling('div', class_='df-value')
                        if email_div and email_div.text:
                            found_contacts.append({
                                'email': email_div.text.strip(),
                                'name': 'Abuse Contact',
                                'source': 'WHOIS'
                            })

                if contact_type:
                    name_row = block.find(lambda tag: tag.name == 'div' and 'Name:' in tag.text and 'df-label' in tag.get('class', []))
                    email_row = block.find(lambda tag: tag.name == 'div' and 'Email:' in tag.text and 'df-label' in tag.get('class', []))

                    name = "N/A"
                    if name_row:
                        name_div = name_row.find_next_sibling('div', class_='df-value')
                        if name_div:
                            name = name_div.text.strip()

                    email = "N/A"
                    if email_row:
                        email_div = email_row.find_next_sibling('div', class_='df-value')
                        if email_div:
                            if email_div.find('img'):
                                # This case is for the div-based layout
                                email_text = "protected-email" + email_div.get_text(separator='').strip()
                                if '@' in email_text:
                                     found_contacts.append({'email': email_text, 'name': name, 'source': f'WHOIS ({contact_type})'})
                            else:
                                email = email_div.text.strip()

                    if email != "N/A" and not email.startswith("Protected"):
                        found_contacts.append({
                            'email': email,
                            'name': name,
                            'source': f'WHOIS ({contact_type})'
                        })

    except requests.RequestException as e:
        print(f"  -> WHOIS lookup failed for {domain}. Error: {e}")
    except Exception as e:
        print(f"  -> An unexpected error occurred during WHOIS lookup: {e}")

    if found_contacts:
        print(f"  -> Found {len(found_contacts)} contact(s) from WHOIS.")
    else:
        print("  -> No contacts found from WHOIS.")

    return found_contacts
