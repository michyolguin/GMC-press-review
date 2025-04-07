import os
import json
import io
import fitz  # PyMuPDF
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime, timezone

# -- Search keywords --
RESEARCHERS = [
    "Vincent Chetail", "Alessandro Monsutti", "Sung Min Rho", "Martina Viarengo",
    "Davide Rodogno", "Gopalan Balachandran", "Delidji Eric Degila", "Minhua Ling",
    "Umut Yildirim", "Ravinder Bhavnani", "Valerio Simoni", "Jérémie Voirol",
    "Mariana Ferolla Vallandro Do Valle", "Michele Benazzo",
    "Global Migration Centre", "GMC", "Centre migration", "migration centre"
]

# -- Auth with Google Drive API --
creds_info = json.loads(os.environ['GCP_SERVICE_ACCOUNT_KEY'])
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

# -- Helper: Get last processed time --
def get_last_run_timestamp():
    if not os.path.exists("data/last_run.json"):
        return "2000-01-01T00:00:00Z"
    with open("data/last_run.json", "r") as f:
        return json.load(f).get("last_run", "2000-01-01T00:00:00Z")

# -- Helper: Save latest timestamp --
def save_last_run_timestamp(timestamp):
    with open("data/last_run.json", "w") as f:
        json.dump({"last_run": timestamp}, f)

# -- Helper: Get new PDF files since last run --
def get_new_pdfs(since_timestamp):
    results = service.files().list(
        q=f"mimeType='application/pdf' and trashed = false and createdTime > '{since_timestamp}'",
        orderBy='createdTime',
        fields="files(id, name, createdTime)"
    ).execute()
    return results.get('files', [])

# -- Download PDF content --
def download_pdf(file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

# -- Extract entries --
def extract_entries_from_pdf(pdf_data):
    entries = []
    doc = fitz.open(stream=pdf_data, filetype="pdf")
    for page in doc:
        text = page.get_text()
        print("---- PAGE TEXT ----")
        print(text)
        print("---- END TEXT ----")
        links = [l.get('uri') for l in page.get_links() if l.get('uri', '').startswith("https://")]
        if any(name.lower() in text.lower() for name in RESEARCHERS) and links:
            for link in links:
                title_line = next((line for line in text.split('\n') if len(line.strip()) > 10), "Untitled Article")
                matched = next((r for r in RESEARCHERS if r.lower() in text.lower()), "Unknown")
                entries.append({
                    "title": title_line.strip(),
                    "date": datetime.today().strftime("%d %B %Y"),
                    "outlet": "Unknown",
                    "researcher": matched,
                    "link": link
                })
    return entries

# -- Append new entries --
def update_entries_json(entries):
    path = "data/entries.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    combined = existing + entries
    with open(path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

# -- MAIN SCRIPT --
if __name__ == "__main__":
    last_run = get_last_run_timestamp()
    new_pdfs = get_new_pdfs(last_run)

    all_new_entries = []
    latest_time = last_run

    for pdf in new_pdfs:
        print(f"Processing: {pdf['name']}")
        data = download_pdf(pdf['id'])
        entries = extract_entries_from_pdf(data)
        all_new_entries.extend(entries)
        if pdf['createdTime'] > latest_time:
            latest_time = pdf['createdTime']

    if all_new_entries:
        update_entries_json(all_new_entries)
        save_last_run_timestamp(latest_time)
        print(f"✅ Added {len(all_new_entries)} new entries.")
    else:
        print("ℹ️ No new entries found")
