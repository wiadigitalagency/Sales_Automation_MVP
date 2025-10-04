import os
import smtplib
import ssl
import time
import pandas as pd
import getpass
from email.message import EmailMessage

# --- Configuration ---
DELAY_SECONDS = 30
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465  # For SSL

def main(csv_file, template_file):
    """
    Main function to run the email sender.
    Reads scraped emails, personalizes a template, and sends the emails.
    """
    # --- 1. Check for necessary files ---
    if not os.path.exists(csv_file):
        print(f"Error: Input file '{csv_file}' not found. Please run the scraper first.")
        return
    if not os.path.exists(template_file):
        print(f"Error: Email template file '{template_file}' not found.")
        return

    # --- 2. Get User Credentials ---
    sender_email = input("Enter your Gmail address: ")
    password = getpass.getpass("Enter your Gmail password (or App Password): ")

    # --- 3. Read Template and Data ---
    with open(template_file, 'r') as f:
        template_content = f.read()

    # Extract subject from the template
    try:
        subject_line, body_template = template_content.split('\n', 1)
        if subject_line.lower().startswith('subject: '):
            subject = subject_line[len('subject: '):].strip()
        else:
            # If "Subject: " prefix is missing, use the first line as subject
            subject = subject_line
            body_template = template_content
    except ValueError:
        subject = "Inquiry" # Default subject
        body_template = template_content


    df = pd.read_csv(csv_file)
    # Filter out entries with no valid email
    df.dropna(subset=['Found_Email'], inplace=True)
    df = df[df['Found_Email'] != 'No email found']
    df = df[df['Found_Email'].str.contains('@')]

    if df.empty:
        print("No valid emails found in the CSV file to send.")
        return

    print(f"\nFound {len(df)} emails to send.")

    # --- 4. Send Emails ---
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            print("Logging into Gmail...")
            server.login(sender_email, password)
            print("Login successful.")

            for index, row in df.iterrows():
                recipient_email = row['Found_Email']
                website_name = row['Website']

                # Personalize the email body
                body = body_template.replace('[WebsiteName]', website_name)

                # Create the email message
                msg = EmailMessage()
                msg.set_content(body)
                msg['Subject'] = subject
                msg['From'] = sender_email
                msg['To'] = recipient_email

                try:
                    print(f"Sending email to {recipient_email}...")
                    server.send_message(msg)
                    print(f"   -> Email sent successfully.")
                except smtplib.SMTPException as e:
                    print(f"   -> Failed to send email to {recipient_email}. Error: {e}")

                if index < len(df) - 1:
                    print(f"Waiting for {DELAY_SECONDS} seconds before next email...")
                    time.sleep(DELAY_SECONDS)

    except smtplib.SMTPAuthenticationError:
        print("\nAuthentication failed. Please check your email and password.")
        print("Note: You might need to use a Google App Password if you have 2-Step Verification enabled.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

    print("\nEmail sending process finished.")

