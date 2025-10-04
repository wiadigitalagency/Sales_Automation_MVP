import requests
import time

def get_hunter_contacts(domain, api_key_manager):
    """
    Searches Hunter.io for contacts, handling API key rotation.

    Args:
        domain (str): The domain to search.
        api_key_manager (ApiKeyManager): The manager for handling API keys.

    Returns:
        list: A list of dictionaries with contact details, or an empty list.
    """
    url = "https://api.hunter.io/v2/domain-search"

    while True:
        api_key = api_key_manager.get_key()
        if not api_key:
            print("No more API keys available to try.")
            return []

        params = {
            'domain': domain,
            'api_key': api_key,
            'limit': 10
        }

        try:
            response = requests.get(url, params=params)

            # Check for errors that should trigger a key rotation
            if response.status_code in [401, 429]: # 401: Unauthorized (invalid key), 429: Credits exhausted
                print(f"API key {api_key[:8]}... failed with status {response.status_code}.")
                if not api_key_manager.rotate_key():
                    return [] # All keys have been exhausted
                time.sleep(1) # Brief pause before retrying with the new key
                continue # Retry the loop with the new key

            response.raise_for_status() # Raise an exception for other, non-rotation errors
            data = response.json()

            if 'data' in data and 'emails' in data['data']:
                contacts = []
                for email_data in data['data']['emails']:
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
                return [] # No data found, successful request

        except requests.exceptions.RequestException as e:
            print(f"Error fetching contacts from Hunter.io for domain {domain}: {e}")
            return [] # Network or other request error, stop trying for this domain
        except Exception as e:
            print(f"An unexpected error occurred processing {domain}: {e}")
            return []

    return [] # Should not be reached, but as a fallback