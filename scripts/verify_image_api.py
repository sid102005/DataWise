import requests
from pathlib import Path
import json
from PIL import Image
import io

BASE_URL = "http://127.0.0.1:8000/api"

def run_image_verification():
    sample_jpg = Path("tests/fixtures/images/sample.jpg")
    print(f"Uploading {sample_jpg} (Original size: 800x600) and requesting resize to 1024x1024...")
    
    with open(sample_jpg, "rb") as f:
        files = {"file": (sample_jpg.name, f, "image/jpeg")}
        data = {
            "prompt": "resize this image to 1024x1024",
            "export_format": "jpg"
        }
        res = requests.post(f"{BASE_URL}/pipeline/run", files=files, data=data)
        
    print(f"HTTP Status: {res.status_code}")
    res_data = res.json()
    print("Full API Response JSON:")
    print(json.dumps(res_data, indent=2))
    
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res_data["status"] == "success", f"Expected success status, got {res_data['status']}"
    assert res_data["validation"]["is_valid"] is True
    assert "resize_dimensions_exact: 1024x1024" in res_data["validation"]["checks_passed"]
    
    session_id = res_data["session_id"]
    download_url = res_data["download_url"]
    print(f"\nDownloading exported image from: {download_url}...")
    dl_res = requests.get(f"http://127.0.0.1:8000{download_url}")
    assert dl_res.status_code == 200, f"Download failed with status {dl_res.status_code}"
    
    # Reopen exported file with Pillow and check actual dimensions and format
    downloaded_img = Image.open(io.BytesIO(dl_res.content))
    print("\n--- REOPENED EXPORTED IMAGE DETAILS ---")
    print(f"Format: {downloaded_img.format}")
    print(f"Dimensions: {downloaded_img.size}")
    print(f"Color Mode: {downloaded_img.mode}")
    print("---------------------------------------")
    
    assert downloaded_img.size == (1024, 1024), f"Expected (1024, 1024), got {downloaded_img.size}"
    assert downloaded_img.format == "JPEG", f"Expected JPEG, got {downloaded_img.format}"
    print("\nSUCCESS: End-to-end image resize operation verified with exact 1024x1024 dimensions!")

if __name__ == "__main__":
    run_image_verification()
