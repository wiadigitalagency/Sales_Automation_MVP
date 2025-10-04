import os
from dotenv import load_dotenv

load_dotenv()

class ApiKeyManager:
    """
    Manages a list of Hunter.io API keys, allowing for rotation when a key runs out of credits.
    """
    def __init__(self):
        """
        Initializes the ApiKeyManager by loading keys from the environment variables.
        """
        api_keys_str = os.getenv("HUNTER_API_KEYS")
        if not api_keys_str:
            self.keys = []
        else:
            self.keys = [key.strip() for key in api_keys_str.split(',')]

        self.current_key_index = 0
        print(f"Loaded {len(self.keys)} API key(s).")

    def get_key(self):
        """
        Gets the current API key.

        Returns:
            str: The current API key, or None if no keys are available.
        """
        if not self.keys or self.current_key_index >= len(self.keys):
            return None
        return self.keys[self.current_key_index]

    def rotate_key(self):
        """
        Rotates to the next API key in the list.

        Returns:
            bool: True if it successfully rotated to a new key, False if all keys have been used.
        """
        self.current_key_index += 1
        if self.current_key_index < len(self.keys):
            print(f"API key limit reached. Rotating to key #{self.current_key_index + 1}...")
            return True
        else:
            print("All API keys have been exhausted.")
            return False