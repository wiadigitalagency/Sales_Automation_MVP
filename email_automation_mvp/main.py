import os
import sys

# Add the 'src' directory to the Python path to allow for clean imports
# from the project's root. This is a standard practice for structuring
# Python applications.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from scraper.scraper import main as run_scraper
from sender.sender import main as run_sender

# --- Path Configuration ---
# Define all paths in one central place, relative to the project root.
# This makes the application robust and independent of where it's run from.
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(ROOT_DIR, 'data', 'urls.txt')
EMAIL_TEMPLATE_FILE = os.path.join(ROOT_DIR, 'data', 'email_template.txt')
SCRAPED_RESULTS_FILE = os.path.join(ROOT_DIR, 'results', 'results.csv')
ENRICHED_RESULTS_FILE = os.path.join(ROOT_DIR, 'results', 'results_enriched.csv')


def main():
    """
    Runs the complete email automation workflow.

    This script orchestrates the scraping and sending processes, managing all
    file paths to ensure the application runs correctly.
    """
    print("--- Step 1: Running Scraper and Enrichment ---")
    run_scraper(
        url_file=URL_FILE,
        output_file=SCRAPED_RESULTS_FILE,
        enriched_output_file=ENRICHED_RESULTS_FILE
    )
    print("\n--- Scraper and Enrichment Finished ---")

    print("\n--- Step 2: Running Email Sender ---")
    # The sender uses the initial scraped results, as per the original design.
    run_sender(
        csv_file=SCRAPED_RESULTS_FILE,
        template_file=EMAIL_TEMPLATE_FILE
    )
    print("\n--- Email Sender Finished ---")

if __name__ == "__main__":
    main()