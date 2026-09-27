import requests
from pathlib import Path
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_api_call(pdf_path: Path, prompt: str = "Extract the text from this PDF"):
    print(f"\n==========================================")
    print(f"Testing {pdf_path.name} with prompt: '{prompt}'")
    print(f"==========================================")
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        data = {
            "prompt": prompt,
            "export_format": "txt"
        }
        res = requests.post(f"{BASE_URL}/pipeline/run", files=files, data=data)
    
    print(f"HTTP Status: {res.status_code}")
    res_data = res.json()
    print("Full API Response JSON:")
    print(json.dumps(res_data, indent=2))
    return res_data

if __name__ == "__main__":
    fixtures_dir = Path("tests/fixtures/documents")
    sample_pdf = fixtures_dir / "sample.pdf"
    scanned_pdf = fixtures_dir / "sample_scanned.pdf"
    
    res_sample = test_api_call(sample_pdf)
    res_scanned = test_api_call(scanned_pdf)
