"""
This module contains functions for looking up WHOIS information for a domain.
It uses a Screenshot + OCR approach to bypass anti-scraping measures.

NOTE: This module relies on a globally available `read_image_file` function
that can perform OCR on a local image file. This function is not part of
the standard Python library and must be provided by the execution environment.
"""
import re
import os
from playwright.sync_api import Error as PlaywrightError

def parse_ocr_text(text):
    """
    Parses the raw text from OCR to find contact information.
    This parser is designed to be tolerant of common OCR errors.
    """
    contacts = []
    # Regex to find emails, tolerant of common OCR mistakes (e.g., spaces)
    email_regex = r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"

    # Split the text into lines for easier processing
    lines = text.split('\n')

    current_contact_type = None
    current_name = "N/A"

    for i, line in enumerate(lines):
        line_lower = line.lower()

        # Identify the start of a contact block
        if "administrative contact" in line_lower:
            current_contact_type = "Administrative"
            if (i + 1) < len(lines):
                current_name = lines[i+1].strip()
            continue
        elif "technical contact" in line_lower:
            current_contact_type = "Technical"
            if (i + 1) < len(lines):
                current_name = lines[i+1].strip()
            continue
        elif "registrant:" in line_lower:
            current_contact_type = "Registrant"
            if (i + 1) < len(lines):
                current_name = lines[i+1].strip()
            continue

        # If we are inside a contact block, look for an email
        if current_contact_type:
            emails = re.findall(email_regex, line)
            for email in emails:
                contacts.append({
                    'email': email,
                    'name': current_name,
                    'source': f'WHOIS ({current_contact_type})'
                })
                # Reset after finding, assuming one email per contact block
                current_contact_type = None
                current_name = "N/A"

    return contacts

def get_whois_data(domain, browser):
    """
    Scrapes WHOIS information by taking a screenshot and using OCR.
    """
    print(f"  -> Performing WHOIS lookup for {domain} (Screenshot + OCR)...")

    url = f"https://www.whois.com/whois/{domain}"
    # Using /tmp for temporary screenshot file
    screenshot_path = f"/tmp/whois_screenshot_{domain}.png"

    page = None
    try:
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 1080})
        page.goto(url, timeout=30000, wait_until='networkidle')

        # Find the element containing the WHOIS data
        # First, try the <pre> tag used for .edu domains
        whois_data_element = page.query_selector("pre.df-raw")
        if not whois_data_element:
             # Fallback for the standard div-based layout
             whois_data_element = page.query_selector("div.whois-data")

        if whois_data_element:
            whois_data_element.screenshot(path=screenshot_path)
            print(f"  -> Screenshot of WHOIS data saved to {screenshot_path}")

            # This tool is expected to be in the environment, as per user instructions.
            ocr_image = read_image_file(screenshot_path)
            ocr_text = ocr_image.text

            # Clean up the screenshot file
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)

            return parse_ocr_text(ocr_text)
        else:
            print("  -> Could not find WHOIS data element on the page.")
            return []

    except PlaywrightError as e:
        print(f"  -> WHOIS lookup failed for {domain} with Playwright. Error: {e}")
        return []
    except NameError as e:
        print(f"  -> OCR tool 'read_image_file' not found in environment. Cannot perform WHOIS lookup. {e}")
        return []
    except Exception as e:
        print(f"  -> An unexpected error occurred during WHOIS lookup: {e}")
        return []
    finally:
        if page:
            page.close()
        # Final cleanup of screenshot file in case of error
        if os.path.exists(screenshot_path):
            try:
                os.remove(screenshot_path)
            except OSError as e:
                print(f"  -> Error removing screenshot file: {e}")
