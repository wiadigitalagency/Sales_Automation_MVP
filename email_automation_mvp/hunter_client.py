import requests

def get_decision_maker_emails(domain, api_key):
    """
    Searches Hunter.io for decision-maker emails associated with a domain.

    Args:
        domain (str): The domain to search.
        api_key (str): Your Hunter.io API key.

    Returns:
        list: A list of up to 3 decision-maker email addresses, or an empty list if none are found or an error occurs.
    """
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        'domain': domain,
        'api_key': api_key,
        'seniority': 'executive',
        'department': 'executive,management,hr,legal,marketing',
        'limit': 3  # Fetch up to 3 emails to stay within the user's limit
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        if 'data' in data and 'emails' in data['data']:
            return [email['value'] for email in data['data']['emails']]
        else:
            return []

    except requests.exceptions.RequestException as e:
        print(f"Error fetching emails from Hunter.io for domain {domain}: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while processing Hunter.io data for {domain}: {e}")
        return []