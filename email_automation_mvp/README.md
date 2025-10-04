# Email Automation MVP

This project is a simple yet powerful email automation tool. It scrapes websites for contact information, enriches the data using the Hunter.io API, and sends personalized emails.

## Features

- **Modular Scraper**: Crawls websites from a provided list to find email addresses, names, and contact details from text, files, and obfuscated sources.
- **Hunter.io Enrichment**: Uses the Hunter.io API to find senior-level contacts for each domain, prioritizing titles like "Founder" and "CEO".
- **Templated Email Sender**: Sends personalized emails using a template, automatically substituting the target's website name.
- **Professional Structure**: The code is organized into a scalable structure, separating logic (`src`), input data (`data`), and output files (`results`).

## Project Structure

The project is organized into the following directories:

-   `src/`: Contains all the Python source code.
    -   `scraper/`: The website scraping and data extraction logic.
    -   `sender/`: The email sending logic.
    -   `utils/`: Shared utilities like the Hunter.io client and API key manager.
-   `data/`: Contains input files for the application.
    -   `urls.txt`: A list of websites to scrape.
    -   `email_template.txt`: The template for the emails you want to send.
-   `results/`: Contains the output CSV files.
    -   `results.csv`: The initial list of emails found by the scraper.
    -   `results_enriched.csv`: The top-ranked contacts found via Hunter.io.
-   `main.py`: The main entry point to run the application.

## Setup

1.  **Clone the Repository**:
    ```bash
    git clone <repository_url>
    cd email_automation_mvp
    ```

2.  **Install Dependencies**: Make sure you have Python 3 installed.
    ```bash
    pip install -r requirements.txt
    ```
    You may also need to download the spaCy language model:
    ```bash
    python -m spacy download en_core_web_sm
    ```

3.  **Configure API Keys**:
    -   Create a file named `.env` in the root directory of the project.
    -   Add your Hunter.io API keys to this file. You can include multiple keys, separated by commas.
    ```env
    HUNTER_API_KEYS=key1,key2,key3
    ```
    If you don't provide any keys, the enrichment step will be skipped.

## How to Use

The entire workflow is managed by the `main.py` script.

1.  **Add Target Websites**: Open `data/urls.txt` and add the websites you want to scrape, one URL per line.
    ```
    example.com
    another-example.com
    ```

2.  **Customize Your Email**: Open `data/email_template.txt` to define the subject and body of your email. Use the placeholder `[WebsiteName]` for personalization.
    ```
    Subject: A question about [WebsiteName]

    Hello,

    I was browsing [WebsiteName] and had a quick question...
    ```

3.  **Run the Application**:
    ```bash
    python main.py
    ```

The script will execute the following steps automatically:
-   **Scrape Websites**: It will crawl the URLs, save the initial findings to `results/results.csv`, and then use Hunter.io to find more contacts, saving them to `results/results_enriched.csv`.
-   **Send Emails**: It will then prompt you for your Gmail credentials and send emails based on the contents of `results.csv`.

    > **Important**: If you have 2-Step Verification enabled on your Gmail account, you will need to generate an **App Password** and use that instead of your regular password.

4.  **Review the Results**: Check the `results/` folder to see the data that was collected.