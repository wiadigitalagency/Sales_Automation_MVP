import re
import spacy
from bs4 import BeautifulSoup
from collections import defaultdict

# Load the spaCy model once
try:
    NLP = spacy.load('en_core_web_sm')
except OSError:
    print("Warning: Spacy model 'en_core_web_sm' not found. Name extraction will be less effective.")
    NLP = None

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

def _deobfuscate_text(text):
    """
    Finds and replaces common email obfuscation patterns in a block of text.
    e.g., "jane [at] example [dot] com" -> "jane@example.com"
    """
    text = text.lower()  # Go to lowercase to catch variations
    # Handle [at] and [dot] with optional spaces
    text = re.sub(r'\s*\[\s*at\s*\]\s*', '@', text)
    text = re.sub(r'\s*\[\s*dot\s*\]\s*', '.', text)
    # Handle (at) and (dot) with optional spaces
    text = re.sub(r'\s*\(\s*at\s*\)\s*', '@', text)
    text = re.sub(r'\s*\(\s*dot\s*\)\s*', '.', text)
    # Handle " at " and " dot "
    text = re.sub(r'\s+at\s+', '@', text)
    text = re.sub(r'\s+dot\s+', '.', text)
    # Remove spaces around the @ symbol that might result from replacement
    text = re.sub(r'\s*@\s*', '@', text)
    return text

def _extract_emails_from_text(text):
    """Helper to find all unique, valid-looking emails in a text block."""
    deobfuscated_text = _deobfuscate_text(text)
    emails = re.findall(EMAIL_REGEX, deobfuscated_text)
    # Filter out emails that are likely image files or other false positives
    return list(set([email for email in emails if not email.endswith(('.png', '.jpg', '.gif', '.jpeg', '.css', '.js'))]))

def _extract_names_and_titles(text):
    """
    Helper to find person names and their potential job titles using spaCy NER and regex.
    Returns a list of dictionaries, e.g., [{'name': 'John Doe', 'title': 'CEO'}].
    """
    if not NLP or not text:
        return []

    # A regex to capture common job titles. This can be expanded.
    # It looks for sequences of capitalized words, possibly including 'and', 'of', etc.
    # and ending in a common job suffix.
    title_keywords = [
        'ceo', 'cto', 'cfo', 'coo', 'cio', 'cmo', 'cso',
        'president', 'vice president', 'vp', 'director', 'manager', 'head', 'lead',
        'engineer', 'developer', 'architect', 'analyst', 'specialist',
        'founder', 'co-founder', 'partner', 'principal', 'owner',
        'editor', 'writer', 'author', 'journalist', 'reporter',
        'recruiter', 'talent acquisition', 'human resources'
    ]
    # This regex is complex: it looks for up to 5 words, likely capitalized, containing a keyword.
    # e.g., "Director of Global Marketing"
    title_regex = re.compile(
        r'((?:[A-Z][a-z-]+\s){0,4}(?:' + '|'.join(title_keywords) + r')(?:\s[A-Z][a-z-]+){0,4})',
        re.IGNORECASE
    )

    persons = []
    doc = NLP(text)

    # Create a set of found names to avoid processing duplicates
    processed_names = set()

    for ent in doc.ents:
        if ent.label_ == 'PERSON':
            name = ent.text.strip()
            # Basic filtering and avoid duplicates
            if not (1 < len(name.split()) < 4 and len(name) < 30) or name in processed_names:
                continue

            processed_names.add(name)
            title = ''

            # Search for a title in the immediate vicinity of the name (e.g., within the same sentence)
            # A simple heuristic: look for a title within 50 chars before or after the name
            start = max(0, ent.start_char - 50)
            end = min(len(text), ent.end_char + 50)
            context = text[start:end]

            title_match = title_regex.search(context)
            if title_match:
                # Clean up the found title
                title = title_match.group(1).strip(' ,-')

            persons.append({'name': name, 'title': title})

    # If no persons were found with spaCy, do a simple regex scan as a fallback
    if not persons:
         # Fallback to the old case study page regex to find at least some titles
        pattern = re.compile(r'(Project Manager|Lead Developer|Engineer|Manager|Director|CEO|CTO|CFO)\s*[:,-]?\s*([A-Z][a-z]+\s[A-Z][a-z]+)')
        matches = pattern.finditer(text)
        for match in matches:
            persons.append({'name': match.group(2).strip(), 'title': match.group(1).strip()})

    return persons

def find_contacts_on_press_page(soup, url):
    """
    Analyzes HTML of a press/news page to find spokesperson or media contact details.
    """
    contacts = []
    # Keywords to find sections likely containing media contacts
    keywords = ['media inquiries', 'press contact', 'media contact', 'spokesperson']

    # Find all text on the page
    page_text = soup.get_text(" ", strip=True)

    # Find all emails on the page first
    all_emails = _extract_emails_from_text(page_text)
    if not all_emails:
        return []

    # Search for sentences or small text blocks containing the keywords
    for keyword in keywords:
        # A regex to find the keyword and capture the following text (e.g., up to 200 chars)
        match = re.search(re.escape(keyword) + r'.{0,200}', page_text, re.IGNORECASE)
        if match:
            context_text = match.group(0)
            context_emails = _extract_emails_from_text(context_text)
            found_persons = _extract_names_and_titles(context_text)

            for email in context_emails:
                # If we find names in the same context, associate them
                if found_persons:
                    for person in found_persons:
                        contacts.append({
                            'email': email,
                            'name': person['name'],
                            'title': person['title'],
                            'source': url,
                            'confidence': 'high'
                        })
                else:
                    # If no name is found, just add the email
                    contacts.append({
                        'email': email,
                        'name': '',
                        'title': '',
                        'source': url,
                        'confidence': 'high'
                    })

    return contacts

def find_contacts_on_blog_page(soup, url):
    """
    Analyzes HTML of a blog page to find author names and emails.
    Looks for common author/byline patterns.
    """
    contacts = []
    # Common CSS classes and tags for author information
    author_selectors = [
        '.author', '.post-author', '.byline', '.author-name',
        'a[rel="author"]', 'span.author', 'div.author-info'
    ]

    for selector in author_selectors:
        author_elements = soup.select(selector)
        for element in author_elements:
            element_text = element.get_text(" ", strip=True)
            persons = _extract_names_and_titles(element_text)
            emails = _extract_emails_from_text(element_text)

            # Simple case: email and name in the same small element
            if persons and emails:
                for person in persons:
                    for email in emails:
                        contacts.append({
                            'email': email,
                            'name': person['name'],
                            'title': person['title'],
                            'source': url,
                            'confidence': 'medium'
                        })
            # Case: Found a name, now look for an email nearby
            elif persons:
                # Search within the parent element for an email
                parent_text = element.parent.get_text(" ", strip=True)
                parent_emails = _extract_emails_from_text(parent_text)
                for person in persons:
                    for email in parent_emails:
                         contacts.append({
                             'email': email,
                             'name': person['name'],
                             'title': person['title'],
                             'source': url,
                             'confidence': 'medium'
                         })

    return contacts

def find_contacts_on_case_study_page(soup, url):
    """
    Analyzes HTML of a case study/testimonial page to find mentioned project members.
    This now uses the centralized name and title extraction logic.
    """
    contacts = []
    page_text = soup.get_text(" ", strip=True)

    found_persons = _extract_names_and_titles(page_text)
    all_emails = _extract_emails_from_text(page_text)

    # This is a simple association: if we find any person and any email on the page,
    # assume they might be related. This is low-confidence but better than nothing.
    if found_persons and all_emails:
        for person in found_persons:
            # For each person, just add the first email found on the page.
            # This is a heuristic for case study pages where contact info is sparse.
            contacts.append({
                'email': all_emails[0],
                'name': person['name'],
                'title': person['title'],
                'source': url,
                'confidence': 'low'
            })

    return contacts

def find_contacts_on_jobs_page(soup, url):
    """
    Analyzes HTML of a jobs/careers page to find recruiter contacts and general application emails.
    """
    contacts = []
    page_text = soup.get_text(" ", strip=True)
    all_emails = _extract_emails_from_text(page_text)

    # First, find all generic jobs/careers emails
    for email in all_emails:
        if any(keyword in email for keyword in ['jobs@', 'careers@', 'recruitment@']):
            contacts.append({
                'email': email,
                'name': 'HR/Recruiting',
                'title': 'HR/Recruiting',
                'source': url,
                'confidence': 'high'
            })

    # Look for recruiter names
    # This is tricky, but we can look for keywords like "recruiter", "talent acquisition"
    keywords = ['recruiter', 'talent acquisition', 'contact for this role']
    for keyword in keywords:
        match = re.search(re.escape(keyword) + r'.{0,150}', page_text, re.IGNORECASE)
        if match:
            context_text = match.group(0)
            found_persons = _extract_names_and_titles(context_text)
            context_emails = _extract_emails_from_text(context_text)
            for email in context_emails:
                if found_persons:
                    for person in found_persons:
                        contacts.append({
                            'email': email,
                            'name': person['name'],
                            'title': person['title'] or 'Recruiter', # Use title if found, else default
                            'source': url,
                            'confidence': 'high'
                        })
                else:
                    contacts.append({
                        'email': email,
                        'name': 'Recruiter',
                        'title': 'Recruiter',
                        'source': url,
                        'confidence': 'high'
                    })

    return contacts

def find_general_contacts(soup, url):
    """
    A general-purpose analyzer for finding contacts on any page.
    - Prioritizes mailto links for reliable name-email association.
    - Scans the entire page for any other emails and looks for nearby names.
    """
    contacts = []
    processed_emails = set()

    # 1. High-confidence extraction: Find all mailto links
    mailto_links = soup.select('a[href^="mailto:"]')
    for link in mailto_links:
        email = link['href'].replace('mailto:', '').split('?')[0]
        if email and email not in processed_emails:
            name = link.get_text(" ", strip=True)
            # Basic validation to ensure the link text could be a name
            if name and '@' not in name:
                contacts.append({
                    'email': email,
                    'name': name,
                    'title': '',
                    'source': url,
                    'confidence': 'high'
                })
                processed_emails.add(email)

    # 2. General scan: Find all other emails on the page
    page_text = soup.get_text(" ", strip=True)
    all_emails = _extract_emails_from_text(page_text)

    remaining_emails = [email for email in all_emails if email not in processed_emails]

    for email in remaining_emails:
        # For remaining emails, try to find a nearby name
        # Create a smaller search area around the email to find associated names
        try:
            email_index = page_text.find(email)
            search_radius = 150  # characters
            start = max(0, email_index - search_radius)
            end = min(len(page_text), email_index + len(email) + search_radius)
            context_text = page_text[start:end]

            found_persons = _extract_names_and_titles(context_text)
            if found_persons:
                # If names are found, associate the first one. This is a heuristic.
                person = found_persons[0]
                contacts.append({
                    'email': email,
                    'name': person['name'],
                    'title': person['title'],
                    'source': url,
                    'confidence': 'medium'
                })
            else:
                # If no name is found, add the email without a name
                contacts.append({
                    'email': email,
                    'name': '',
                    'title': '',
                    'source': url,
                    'confidence': 'low'
                })

            processed_emails.add(email)

        except Exception:
            # If there's any issue finding the email index, just add the email
            if email not in processed_emails:
                 contacts.append({
                     'email': email,
                     'name': '',
                     'title': '',
                     'source': url,
                     'confidence': 'low'
                 })
                 processed_emails.add(email)

    return contacts

def analyze_page_content(html_content, url):
    """
    Orchestrator function that determines the page type and calls the appropriate analyzer.
    Returns a list of found contacts.
    """
    contacts = []
    soup = BeautifulSoup(html_content, 'lxml')

    # Use a dictionary to map keywords to functions
    page_type_map = {
        ('press', 'news', 'media'): find_contacts_on_press_page,
        ('blog',): find_contacts_on_blog_page,
        ('case-study', 'testimonial', 'customer-story'): find_contacts_on_case_study_page,
        ('careers', 'jobs', 'join-us'): find_contacts_on_jobs_page,
        ('contact', 'about', 'team'): find_general_contacts,
    }

    # Use a single set to store all found contacts to avoid duplicates
    found_contacts_set = set()

    # Helper function to add unique contacts
    def add_unique_contacts(new_contacts):
        for contact in new_contacts:
            # The deduplication key now includes the title to allow for richer data to be added.
            contact_tuple = (contact['email'], contact.get('name', ''), contact.get('title', ''))
            if contact_tuple not in found_contacts_set:
                contacts.append(contact)
                found_contacts_set.add(contact_tuple)

    # First, run specific analyzers based on URL keywords
    specific_analyzer_run = False
    for keywords, analyzer_func in page_type_map.items():
        if any(keyword in url for keyword in keywords):
            print(f"  -> Analyzing page: {url} (Detected type: {keywords[0]})")
            try:
                # We run the specific analyzer, e.g., find_contacts_on_press_page
                # Note: find_general_contacts is also in the map, so it runs here if keywords match
                found = analyzer_func(soup, url)
                add_unique_contacts(found)
                specific_analyzer_run = True
            except Exception as e:
                print(f"  -> Error analyzing {url} with {analyzer_func.__name__}: {e}")

    # Now, always run the general analyzer as a fallback/addition,
    # but only if it wasn't the one already run as a "specific" analyzer.
    # This avoids running it twice on pages like /about-us.
    is_general_page = any(keyword in url for keyword in ('contact', 'about', 'team'))
    if not is_general_page:
        print(f"  -> Running general analysis on: {url}")
        try:
            general_contacts = find_general_contacts(soup, url)
            add_unique_contacts(general_contacts)
        except Exception as e:
            print(f"  -> Error during general analysis on {url}: {e}")


    if contacts:
        print(f"  -> Found {len(contacts)} total potential contact(s) on {url}")

    return contacts

def parse_autoresponse_email(email_text_content):
    """
    Parses the raw text of an email autoresponse to find the sender's email.
    This is a helper utility for the semi-automated process of capturing email
    formats by submitting a contact form and analyzing the reply.

    Usage:
    1. Manually submit a contact form on the target website.
    2. When the auto-reply arrives, copy its full raw content (including headers).
    3. Pass the content to this function.

    Args:
        email_text_content (str): The full raw text of the email.

    Returns:
        list: A list of unique email addresses found in the 'From' or 'Reply-To' headers.
    """
    emails = []
    # Look for 'From:' or 'Reply-To:' lines and extract the email
    for line in email_text_content.splitlines():
        if line.lower().startswith('from:') or line.lower().startswith('reply-to:'):
            found = _extract_emails_from_text(line)
            if found:
                emails.extend(found)

    if emails:
        print(f"  -> Found potential contact email(s) in autoresponse: {list(set(emails))}")

    return list(set(emails))
