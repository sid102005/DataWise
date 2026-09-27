"""Integration tests for multi-file and batch processing across categories."""

import io
import json
from pathlib import Path
import zipfile
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.main import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "batch"
ARCHIVES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "archives"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestBatchProcessing:
    """Test suite for batch processing semantics, partial success, and mixed types."""

    def test_batch_image_resize_produces_independent_outputs(self, client: TestClient):
        """Upload 3 JPGs, request batch resize to 100x100, verify all 3 via Pillow."""
        img1 = FIXTURES_DIR / "img1.jpg"
        img2 = FIXTURES_DIR / "img2.jpg"
        img3 = FIXTURES_DIR / "img3.jpg"

        with open(img1, "rb") as f1, open(img2, "rb") as f2, open(img3, "rb") as f3:
            files = [
                ("files", ("img1.jpg", f1.read(), "image/jpeg")),
                ("files", ("img2.jpg", f2.read(), "image/jpeg")),
                ("files", ("img3.jpg", f3.read(), "image/jpeg")),
            ]
            resp = client.post(
                "/api/pipeline/run",
                files=files,
                data={"prompt": "Resize all images to 100x100"},
            )

        assert resp.status_code == 200, f"Error: {resp.text}"
        body = resp.json()

        assert body["status"] == "success"
        assert body["batch_summary"] is not None
        summary = body["batch_summary"]
        assert summary["total_files"] == 3
        assert summary["succeeded_count"] == 3
        assert summary["failed_count"] == 0
        assert summary["excluded_count"] == 0

        # Check per-file results
        results = body["batch_results"]
        assert len(results) == 3
        for r in results:
            assert r["status"] == "success"
            assert r["validation_passed"] is True

        # Download packaged ZIP
        download_url = body["download_url"]
        assert download_url is not None
        dl_resp = client.get(download_url)
        assert dl_resp.status_code == 200

        # Reopen ZIP and verify all 3 images with Pillow independently
        zip_buf = io.BytesIO(dl_resp.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            namelist = zf.namelist()
            assert len(namelist) == 3
            for name in namelist:
                with zf.open(name) as img_data:
                    with Image.open(img_data) as img:
                        assert img.size == (100, 100), f"File {name} had size {img.size}, expected (100, 100)"

    def test_mixed_type_batch_honesty(self, client: TestClient):
        """Upload 2 CSVs + 1 JPG with tabular instruction: processes 2 CSVs and reports JPG excluded."""
        mixed_dir = FIXTURES_DIR / "mixed"
        csv1 = mixed_dir / "part1.csv"
        csv2 = mixed_dir / "part2.csv"
        jpg1 = mixed_dir / "photo.jpg"

        with open(csv1, "rb") as f1, open(csv2, "rb") as f2, open(jpg1, "rb") as f3:
            files = [
                ("files", ("part1.csv", f1.read(), "text/csv")),
                ("files", ("part2.csv", f2.read(), "text/csv")),
                ("files", ("photo.jpg", f3.read(), "image/jpeg")),
            ]
            resp = client.post(
                "/api/pipeline/run",
                files=files,
                data={"prompt": "Clean tabular data and remove missing values"},
            )

        assert resp.status_code == 200, f"Error: {resp.text}"
        body = resp.json()

        assert body["status"] == "partial_success"
        summary = body["batch_summary"]
        assert summary["total_files"] == 3
        assert summary["succeeded_count"] == 2
        assert summary["excluded_count"] == 1
        assert summary["failed_count"] == 0

        # Verify photo.jpg is honestly reported as excluded
        results = {r["filename"]: r for r in body["batch_results"]}
        assert results["photo.jpg"]["status"] == "excluded"
        assert "excluded" in results["photo.jpg"]["reason"].lower()
        assert results["photo.jpg"]["validation_passed"] is None

        # Verify CSVs succeeded
        assert results["part1.csv"]["status"] == "success"
        assert results["part2.csv"]["status"] == "success"

        # Download result archive
        dl_resp = client.get(body["download_url"])
        assert dl_resp.status_code == 200

    def test_batch_cross_category_archive_end_to_end(self, client: TestClient):
        """End-to-end API test with sample.zip containing CSV + JPG + TXT."""
        sample_zip = ARCHIVES_DIR / "sample.zip"
        with open(sample_zip, "rb") as f:
            resp = client.post(
                "/api/pipeline/run",
                files={"file": ("sample.zip", f.read(), "application/zip")},
                data={"prompt": "List all contents and inspect files in this archive"},
            )

        assert resp.status_code == 200, f"Error: {resp.text}"
        body = resp.json()
        assert body["status"] == "success"
        assert body["total_rows"] == 3
        assert len(body["preview_rows"]) == 3

        # Reopen output archive
        dl_resp = client.get(body["download_url"])
        assert dl_resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
            assert len(zf.namelist()) == 3

    def test_batch_partial_failure_reporting(self, client: TestClient):
        """When 1 file fails and 1 succeeds, status is partial_success and both are reported."""
        mixed_dir = FIXTURES_DIR / "mixed"
        valid_csv = mixed_dir / "part1.csv"
        corrupt_csv_bytes = b"\x00\x01\x02\x03\x04binary garbage that is not csv"

        with open(valid_csv, "rb") as f1:
            files = [
                ("files", ("part1.csv", f1.read(), "text/csv")),
                ("files", ("broken.csv", corrupt_csv_bytes, "text/csv")),
            ]
            resp = client.post(
                "/api/pipeline/run",
                files=files,
                data={"prompt": "Clean tabular data"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "partial_success"
        summary = body["batch_summary"]
        assert summary["total_files"] == 2
        assert summary["succeeded_count"] == 1
        assert summary["failed_count"] == 1

        results = {r["filename"]: r for r in body["batch_results"]}
        assert results["part1.csv"]["status"] == "success"
        assert results["broken.csv"]["status"] == "failed"

    def test_batch_no_files_returns_400(self, client: TestClient):
        """Calling run endpoint with no files returns 400."""
        resp = client.post(
            "/api/pipeline/run",
            data={"prompt": "Do something"},
        )
        assert resp.status_code == 400

