"""Generate Phase 13 archive and batch test fixtures."""

import gzip
import io
import json
from pathlib import Path
import struct
import tarfile
import zipfile
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVES_DIR = REPO_ROOT / "tests" / "fixtures" / "archives"
BATCH_DIR = REPO_ROOT / "tests" / "fixtures" / "batch"


def generate_archives():
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Legitimate sample.zip (CSV + JPG + TXT)
    sample_csv_content = b"id,product,price\n1,Widget,19.99\n2,Gadget,29.99\n3,Doodad,9.99\n"
    sample_txt_content = b"This is a notes document inside a zip archive.\nLine 2.\n"

    img_buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(73, 109, 137))
    img.save(img_buf, format="JPEG")
    sample_jpg_content = img_buf.getvalue()

    sample_zip_path = ARCHIVES_DIR / "sample.zip"
    with zipfile.ZipFile(sample_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.csv", sample_csv_content)
        zf.writestr("image.jpg", sample_jpg_content)
        zf.writestr("notes.txt", sample_txt_content)

    # 2. Malicious zip-slip archive
    zip_slip_path = ARCHIVES_DIR / "zip_slip.zip"
    with zipfile.ZipFile(zip_slip_path, "w") as zf:
        zf.writestr("../../evil.txt", b"malicious traversal payload")

    # 3. Hand-crafted archive bomb (declared size 700 MB in central directory)
    bomb_path = ARCHIVES_DIR / "archive_bomb.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bomb.txt", b"tiny data")
    raw_data = bytearray(buf.getvalue())
    cd_idx = raw_data.find(b"PK\x01\x02")
    # Set declared uncompressed size = 700 MB (734003200 bytes)
    declared_size = 700 * 1024 * 1024
    if cd_idx != -1:
        struct.pack_into("<I", raw_data, cd_idx + 24, declared_size)
    struct.pack_into("<I", raw_data, 22, declared_size)  # local header
    with open(bomb_path, "wb") as f:
        f.write(raw_data)

    # 4. Legitimate sample.tar
    sample_tar_path = ARCHIVES_DIR / "sample.tar"
    with tarfile.open(sample_tar_path, "w") as tf:
        csv_info = tarfile.TarInfo(name="data.csv")
        csv_info.size = len(sample_csv_content)
        tf.addfile(csv_info, io.BytesIO(sample_csv_content))

        txt_info = tarfile.TarInfo(name="notes.txt")
        txt_info.size = len(sample_txt_content)
        tf.addfile(txt_info, io.BytesIO(sample_txt_content))

    # 5. Legitimate sample.gz (gzipped CSV)
    sample_gz_path = ARCHIVES_DIR / "sample.gz"
    with gzip.open(sample_gz_path, "wb") as gf:
        gf.write(sample_csv_content)

    # Expected values for archives
    expected_archives = {
        "sample.zip": {
            "entry_count": 3,
            "entries": ["data.csv", "image.jpg", "notes.txt"],
            "contained_categories": ["tabular", "image", "document"],
            "security_valid": True,
        },
        "zip_slip.zip": {
            "entry_count": 1,
            "entries": ["../../evil.txt"],
            "security_valid": False,
            "expected_error": "Path traversal entry detected",
        },
        "archive_bomb.zip": {
            "entry_count": 1,
            "declared_uncompressed_bytes": declared_size,
            "security_valid": False,
            "expected_error": "Declared uncompressed size",
        },
        "sample.tar": {
            "entry_count": 2,
            "entries": ["data.csv", "notes.txt"],
            "contained_categories": ["tabular", "document"],
            "security_valid": True,
        },
        "sample.gz": {
            "entry_count": 1,
            "entries": ["sample"],
            "security_valid": True,
        },
    }
    with open(ARCHIVES_DIR / "expected_values.json", "w") as f:
        json.dump(expected_archives, f, indent=2)


def generate_batch_fixtures():
    BATCH_DIR.mkdir(parents=True, exist_ok=True)

    # Images for batch resize (3 JPGs, 200x200 each)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i, color in enumerate(colors, 1):
        img = Image.new("RGB", (200, 200), color=color)
        img.save(BATCH_DIR / f"img{i}.jpg", format="JPEG")

    # CSVs for batch processing (3 CSVs)
    csv_rows = [
        "id,val\n1,10\n2,20\n",
        "id,val\n3,30\n4,40\n",
        "id,val\n5,50\n6,60\n",
    ]
    for i, content in enumerate(csv_rows, 1):
        with open(BATCH_DIR / f"data{i}.csv", "w") as f:
            f.write(content)

    # Mismatched batch: 2 CSVs + 1 JPG
    mixed_dir = BATCH_DIR / "mixed"
    mixed_dir.mkdir(parents=True, exist_ok=True)
    with open(mixed_dir / "part1.csv", "w") as f:
        f.write("id,item\n101,Keyboard\n")
    with open(mixed_dir / "part2.csv", "w") as f:
        f.write("id,item\n102,Mouse\n")
    mixed_img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    mixed_img.save(mixed_dir / "photo.jpg", format="JPEG")

    # Expected values for batch
    expected_batch = {
        "images": {
            "files": ["img1.jpg", "img2.jpg", "img3.jpg"],
            "count": 3,
            "original_size": [200, 200],
            "batch_operation": "resize to 100x100",
            "expected_size": [100, 100],
        },
        "tabular": {
            "files": ["data1.csv", "data2.csv", "data3.csv"],
            "count": 3,
            "total_rows": 6,
        },
        "mixed": {
            "files": ["part1.csv", "part2.csv", "photo.jpg"],
            "tabular_files": ["part1.csv", "part2.csv"],
            "non_tabular_files": ["photo.jpg"],
            "expected_excluded": "photo.jpg",
        },
    }
    with open(BATCH_DIR / "expected_values.json", "w") as f:
        json.dump(expected_batch, f, indent=2)


if __name__ == "__main__":
    generate_archives()
    generate_batch_fixtures()
    print("Successfully generated archive and batch fixtures.")
