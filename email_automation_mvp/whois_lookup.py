"""
This module contains functions for looking up WHOIS information for a domain.
It uses a Screenshot + OCR approach with the EasyOCR library.
"""
import re
import os
import easyocr
from playwright.sync_api import Error as PlaywrightError
import logging

# Suppress verbose logging from libraries to keep output clean
logging.getLogger('easyocr').setLevel(logging.ERROR)
logging.getLogger('playwright').setLevel(logging.WARNING)

def parse_whois_ocr(full_text):
    """
    Parses the raw text from OCR to find contact information using a robust block-based logic.
    """
    contacts = []
    lines = full_text.split('\n')
    # This regex is intentionally broad to catch emails with OCR errors (like spaces)
    email_pattern = re.compile(r'([\w\.\-%+]+@[\w\.\- ]+[\w\.]+)')

    contact_blocks = []
    current_block = []
    in_whois_data = False # Flag to start capturing only after the first header

    # --- Robust Block Splitting ---
    for line in lines:
        is_header = re.search(r'^\s*(Administrative Contact|Technical Contact|Registrant):', line, re.I)
        if is_header:
            in_whois_data = True # Start capturing
            if current_block:
                contact_blocks.append(current_block)
            current_block = [line]
        elif in_whois_data: # Only append if we are inside the relevant WHOIS data
            current_block.append(line)
    if current_block: # Append the last block
        contact_blocks.append(current_block)

    # --- Process Each Block Independently ---
    for block in contact_blocks:
        block_text = "\n".join(block)
        name = "Unknown"
        email = None

        # --- Extract Name ---
        if block:
            # Name can be on the same line as the role (e.g., "Registrant: John Doe")
            first_line_parts = block[0].split(':', 1)
            if len(first_line_parts) > 1 and first_line_parts[1].strip():
                name = first_line_parts[1].strip()
            # Or it can be on the next line
            elif len(block) > 1:
                # Basic check to avoid grabbing an address line as a name
                if '@' not in block[1] and 'http' not in block[1] and len(block[1].split()) < 5:
                    name = block[1].strip()

        # --- Extract and Clean Email ---
        email_match = email_pattern.search(block_text)
        if email_match:
            raw_email = email_match.group(0)
            cleaned_email = raw_email.replace(' ', '')

            if '@' in cleaned_email:
                local_part, domain_part = cleaned_email.split('@', 1)
                if '.' not in domain_part:
                    raw_domain_part = raw_email.split('@')[1].strip()
                    if ' ' in raw_domain_part:
                         parts = raw_domain_part.rsplit(' ', 1)
                         cleaned_domain = '.'.join(parts)
                         email = f"{local_part}@{cleaned_domain}"
                    else:
                        email = cleaned_email
                else:
                    email = cleaned_email

        # --- Add Contact if valid ---
        if email and name and name != "Unknown":
            # Filter out organizational names
            if not any(org_word in name for org_word in ['University', 'Computing', 'Center']):
                 if not any(c['email'] == email for c in contacts):
                    contacts.append({'name': name, 'email': email, 'source': 'WHOIS (OCR)'})

    return contacts

def get_whois_data(domain, browser):
    """
    Scrapes WHOIS information by taking a screenshot and using EasyOCR.
    """
    print(f"  -> Performing WHOIS lookup for {domain} (Screenshot + EasyOCR)...")
    found_contacts = []
    url = f"https://www.whois.com/whois/{domain}"
    screenshot_path = f"/tmp/whois_screenshot_{domain}.png"

    page = None
    try:
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 1080})
        page.goto(url, timeout=30000, wait_until='networkidle')

        # More robust selector for WHOIS data element
        whois_data_element = page.locator("pre.df-raw, div.df-block-raw").first

        if whois_data_element.is_visible():
            whois_data_element.screenshot(path=screenshot_path)
            print(f"  -> Screenshot of WHOIS data saved to {screenshot_path}")

            reader = easyocr.Reader(['en'])
            ocr_result = reader.readtext(screenshot_path)
            ocr_text = "\n".join([text for (bbox, text, prob) in ocr_result])

            print("---- START of EasyOCR Text ----")
            print(ocr_text)
            print("---- END of EasyOCR Text ----")

            found_contacts = parse_whois_ocr(ocr_text)

        else:
            print("  -> Could not find WHOIS data element on the page.")

    except PlaywrightError as e:
        print(f"  -> WHOIS lookup failed for {domain} with Playwright. Error: {e}")
    except Exception as e:
        print(f"  -> An unexpected error occurred during WHOIS lookup: {e}")
    finally:
        if page:
            page.close()
        if os.path.exists(screenshot_path):
            try:
                os.remove(screenshot_path)
            except OSError as e:
                print(f"  -> Error removing screenshot file: {e}")

    unique_contacts = []
    seen_emails = set()
    for contact in found_contacts:
        if contact['email'] not in seen_emails:
            unique_contacts.append(contact)
            seen_emails.add(contact['email'])

    if unique_contacts:
        print(f"  -> Found {len(unique_contacts)} contact(s) from WHOIS.")
    else:
        print("  -> No contacts found from WHOIS.")

    return unique_contacts
