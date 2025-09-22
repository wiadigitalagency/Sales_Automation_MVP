"""
This module contains functions for looking up WHOIS information for a domain.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
}

def get_whois_data(domain):
    """
    Scrapes WHOIS information for a given domain from whois.com.

    Args:
        domain (str): The domain name to look up.

    Returns:
        list: A list of dictionaries, where each dictionary contains
              'email', 'name', and 'source' for each contact found.
    """
    print(f"  -> Performing WHOIS lookup for {domain}...")
    found_contacts = []
    url = f"https://www.whois.com/whois/{domain}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

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
                 # Special case for the abuse email
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
                        # Email might be protected by an image
                        if email_div.find('img'):
                            email = f"Protected ({contact_type})"
                        else:
                            email = email_div.text.strip()

                if email != "N/A" and not email.startswith("Protected"):
                    found_contacts.append({
                        'email': email,
                        'name': name,
                        'source': 'WHOIS'
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
