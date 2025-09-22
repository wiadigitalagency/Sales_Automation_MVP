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

def _extract_emails_from_text(text):
    """Helper to find all unique, valid-looking emails in a text block."""
    emails = re.findall(EMAIL_REGEX, text)
    # Filter out emails that are likely image files or other false positives
    return list(set([email for email in emails if not email.endswith(('.png', '.jpg', '.gif', '.jpeg', '.css', '.js'))]))

def _extract_names_from_text(text):
    """Helper to find person names using spaCy NER."""
    if not NLP or not text:
        return []
    doc = NLP(text)
    names = [ent.text.strip() for ent in doc.ents if ent.label_ == 'PERSON']
    # Basic filtering for common sense names
    return list(set([name for name in names if 1 < len(name.split()) < 4 and len(name) < 30]))

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
            context_names = _extract_names_from_text(context_text)

            for email in context_emails:
                # If we find names in the same context, associate them
                if context_names:
                    for name in context_names:
                        contacts.append({'email': email, 'name': name, 'source': url})
                else:
                    # If no name is found, just add the email
                    contacts.append({'email': email, 'name': '', 'source': url})

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
            names = _extract_names_from_text(element_text)
            emails = _extract_emails_from_text(element_text)

            # Simple case: email and name in the same small element
            if names and emails:
                for name in names:
                    for email in emails:
                        contacts.append({'email': email, 'name': name, 'source': url})
            # Case: Found a name, now look for an email nearby
            elif names:
                # Search within the parent element for an email
                parent_text = element.parent.get_text(" ", strip=True)
                parent_emails = _extract_emails_from_text(parent_text)
                for name in names:
                    for email in parent_emails:
                         contacts.append({'email': email, 'name': name, 'source': url})

    return contacts

def find_contacts_on_case_study_page(soup, url):
    """
    Analyzes HTML of a case study/testimonial page to find mentioned project members.
    Looks for job titles next to names.
    """
    contacts = []
    page_text = soup.get_text(" ", strip=True)

    # Regex to find job titles/roles followed by what looks like a name
    # e.g., "Project Manager: John Doe", "Lead Developer, Jane Smith"
    pattern = re.compile(r'(Project Manager|Lead Developer|Engineer|Manager|Director|CEO|CTO|CFO)\s*[:,-]?\s*([A-Z][a-z]+\s[A-Z][a-z]+)')

    matches = pattern.finditer(page_text)
    for match in matches:
        name = match.group(2).strip()
        # Look for emails in the vicinity of the found name
        search_area = page_text[max(0, match.start() - 100):min(len(page_text), match.end() + 100)]
        emails = _extract_emails_from_text(search_area)
        for email in emails:
            contacts.append({'email': email, 'name': name, 'source': url})

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
            contacts.append({'email': email, 'name': 'HR/Recruiting', 'source': url})

    # Look for recruiter names
    # This is tricky, but we can look for keywords like "recruiter", "talent acquisition"
    keywords = ['recruiter', 'talent acquisition', 'contact for this role']
    for keyword in keywords:
        match = re.search(re.escape(keyword) + r'.{0,150}', page_text, re.IGNORECASE)
        if match:
            context_text = match.group(0)
            context_names = _extract_names_from_text(context_text)
            context_emails = _extract_emails_from_text(context_text)
            for email in context_emails:
                if context_names:
                    for name in context_names:
                        contacts.append({'email': email, 'name': name, 'source': url})
                else:
                    contacts.append({'email': email, 'name': 'Recruiter', 'source': url})

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
    }

    # Use a single set to store all found contacts to avoid duplicates from different analyzers on the same page
    found_contacts_set = set()

    for keywords, analyzer_func in page_type_map.items():
        if any(keyword in url for keyword in keywords):
            print(f"  -> Analyzing page: {url} (Detected type: {keywords[0]})")
            try:
                new_contacts = analyzer_func(soup, url)
                for contact in new_contacts:
                    # Use a tuple to make the dict hashable for the set
                    contact_tuple = (contact['email'], contact.get('name', ''))
                    if contact_tuple not in found_contacts_set:
                        contacts.append(contact)
                        found_contacts_set.add(contact_tuple)
            except Exception as e:
                print(f"  -> Error analyzing {url} with {analyzer_func.__name__}: {e}")

    if contacts:
        print(f"  -> Found {len(contacts)} potential contact(s) on {url}")

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
