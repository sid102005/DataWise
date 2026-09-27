import requests
import json
import pandas as pd
from pathlib import Path

# Path to the sample csv fixture
sample_csv = Path("tests/fixtures/sample.csv")

def verify_request(prompt: str, expected_col: str, should_exist: bool):
    print(f"\n--- Testing Prompt: '{prompt}' ---")
    
    with open(sample_csv, "rb") as f:
        resp = requests.post(
            "http://127.0.0.1:8000/api/pipeline/run",
            files={"file": ("sample.csv", f, "text/csv")},
            data={"prompt": prompt, "export_format": "csv"}
        )
    
    if resp.status_code != 200:
        print(f"FAILED: HTTP {resp.status_code}")
        print(resp.text)
        return
        
    data = resp.json()
    if data.get("status") != "success":
        print(f"FAILED: Pipeline status was {data.get('status')}")
        print(json.dumps(data, indent=2))
        return
        
    session_id = data.get("session_id")
    print(f"Session ID: {session_id}")
    
    # Download the result file
    download_url = f"http://127.0.0.1:8000/api/pipeline/download/{session_id}/result.csv"
    download_resp = requests.get(download_url)
    
    if download_resp.status_code != 200:
        print(f"FAILED to download result.csv: HTTP {download_resp.status_code}")
        return
        
    # Read the downloaded CSV bytes directly into pandas
    from io import BytesIO
    df = pd.read_csv(BytesIO(download_resp.content))
    columns = list(df.columns)
    
    print(f"Reopened File Columns: {columns}")
    
    exists = expected_col in columns
    if should_exist:
        assert exists, f"Expected {expected_col} to exist, but it was missing!"
        print("SUCCESS: Target column exists as expected.")
    else:
        assert not exists, f"Expected {expected_col} to be removed, but it still exists!"
        print("SUCCESS: Target column does not exist as expected.")

if __name__ == "__main__":
    verify_request("remove the Region column", "Region", False)
    verify_request("add a column called Senior", "Senior", True)
