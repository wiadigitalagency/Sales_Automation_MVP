# Email Automation MVP

This project is a Minimum Viable Product (MVP) for a simple email automation tool. It consists of two Python scripts: one for scraping websites to find email addresses and another for sending a templated email to the found addresses.

## Features

- **Email Scraper**: Reads a list of websites, visits their contact/about pages, and extracts any email addresses it finds.
- **Email Sender**: Reads the list of scraped emails and sends a personalized email to each one.

This MVP does **not** include AI personalization, automatic follow-ups, or advanced analytics.

## Setup

1.  **Clone the repository** or download the files into a directory.
2.  **Install dependencies**: Make sure you have Python 3 installed. Open your terminal or command prompt, navigate to the project directory, and run:
    ```bash
    pip install -r requirements.txt
    ```

## How to Use

The process is two steps: first you run the scraper, then you run the sender.

### Step 1: Scrape for Emails

1.  **Edit `urls.txt`**: Open the `urls.txt` file and add the websites you want to scrape, with one URL per line. For example:
    ```
    google.com
    github.com
    ```
2.  **Run the scraper**: Navigate to the project directory in your terminal and run the script:
    ```bash
    python scraper.py
    ```
3.  **Check the output**: The script will print its progress. Once finished, it will create a `results.csv` file containing the websites and the emails it found.

### Step 2: Send the Emails

1.  **Review `results.csv`**: It's a good idea to open `results.csv` to see which emails were found. The sender script will only email the valid addresses it finds.
2.  **Edit `email_template.txt`**: Modify the `email_template.txt` file with the content you want to send. You can change the subject and the body. Use the placeholder `[WebsiteName]` in the body, and the script will automatically replace it with the corresponding website URL for personalization.
3.  **Run the sender**: In your terminal, run the sender script:
    ```bash
    python sender.py
    ```
4.  **Enter your credentials**: The script will prompt you for your Gmail address and password.

    > **Important**: If you have 2-Step Verification enabled on your Gmail account, you will need to generate an **App Password** and use that instead of your regular password. You can find instructions on how to do this in your Google Account settings.

5.  **Monitor the process**: The script will log into your account and send the emails one by one, with a 30-second delay between each to avoid being flagged as spam. It will print a confirmation message after each email is sent.

---
This completes the functionality of the MVP. You can now customize the input files and run the scripts to automate your email outreach.
