import requests

def get_hunter_contacts(domain, api_key):
    """
    Searches Hunter.io for all contacts associated with a domain, fetching up to 100.

    Args:
        domain (str): The domain to search.
        api_key (str): Your Hunter.io API key.

    Returns:
        list: A list of dictionaries, each containing contact details (name, email, position),
              or an empty list if none are found or an error occurs.
    """
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        'domain': domain,
        'api_key': api_key,
        'limit': 10  # Fetch up to 10 emails, the maximum for free accounts
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if 'data' in data and 'emails' in data['data']:
            contacts = []
            for email_data in data['data']['emails']:
                # Combine first and last name, handle cases where they might be None
                first_name = email_data.get('first_name', '') or ''
                last_name = email_data.get('last_name', '') or ''
                full_name = f"{first_name} {last_name}".strip()

                contacts.append({
                    'name': full_name,
                    'email': email_data.get('value'),
                    'position': email_data.get('position')
                })
            return contacts
        else:
            return []

    except requests.exceptions.RequestException as e:
        print(f"Error fetching contacts from Hunter.io for domain {domain}: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while processing Hunter.io data for {domain}: {e}")
        return []