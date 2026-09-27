import requests
from pathlib import Path
import time
import json

BASE_URL = "http://127.0.0.1:8000/api"

def run_document_extraction():
    sample_pdf = Path("tests/fixtures/documents/sample.pdf")
    
    print(f"Uploading {sample_pdf} and running extraction...")
    with open(sample_pdf, "rb") as f:
        files = {"file": (sample_pdf.name, f, "application/pdf")}
        data = {
            "prompt": "Extract the text from this PDF",
            "export_format": "txt"
        }
        res = requests.post(f"{BASE_URL}/pipeline/run", files=files, data=data)
    
    if res.status_code != 200:
        print(f"Pipeline failed: {res.text}")
        return
        
    res_data = res.json()
    session_id = res_data["session_id"]
    print(f"Session ID: {session_id}")
    print("Pipeline Success. Output:")
    print(json.dumps(res_data, indent=2))
    
    # 3. Download the result.txt
    print("Downloading result...")
    # The regex allows result.txt? Let's check _ALLOWED_FILENAME_RE in routes.py
    # wait, the regex allows result.(csv|xlsx|json) and *.png
    # I need to update the regex in routes.py to allow result.txt and result.md!
    res = requests.get(f"{BASE_URL}/pipeline/download/{session_id}/result.txt")
    if res.status_code != 200:
        print(f"Download failed: {res.text}")
        return
        
    content = res.text
    print("\n--- REOPENED EXPORTED TEXT ---")
    print(content)
    print("------------------------------")
    
    # Verify expected strings
    expected_strings = ["PDF Heading", "first page of the PDF", "second page"]
    missing = [s for s in expected_strings if s not in content]
    if missing:
        print(f"FAIL: Missing substrings {missing}")
    else:
        print("SUCCESS: All expected substrings found in exported file.")

if __name__ == "__main__":
    run_document_extraction()
