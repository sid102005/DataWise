import json
import struct
import zlib
from pathlib import Path
from PIL import Image, ImageDraw

def generate_fixtures():
    fixtures_dir = Path("tests/fixtures/images")
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    width = 800
    height = 600
    
    # 1. Base RGB image
    # Background: (240, 240, 240)
    img = Image.new("RGB", (width, height), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    
    # Markers in 4 corners:
    # Top-Left: Solid RED (255, 0, 0)
    draw.rectangle([0, 0, 99, 99], fill=(255, 0, 0))
    # Top-Right: Solid GREEN (0, 255, 0)
    draw.rectangle([width - 100, 0, width - 1, 99], fill=(0, 255, 0))
    # Bottom-Left: Solid BLUE (0, 0, 255)
    draw.rectangle([0, height - 100, 99, height - 1], fill=(0, 0, 255))
    # Bottom-Right: Solid YELLOW (255, 255, 0)
    draw.rectangle([width - 100, height - 100, width - 1, height - 1], fill=(255, 255, 0))
    
    # Center pattern (lines and circles) so there is entropy for compression tests
    for i in range(100, 500, 20):
        draw.line([(i, 150), (i + 200, 450)], fill=(i % 255, (i * 2) % 255, (i * 3) % 255), width=3)
    draw.ellipse([300, 200, 500, 400], outline=(50, 50, 50), width=4)
    
    # Save standard formats
    img.save(fixtures_dir / "sample.jpg", format="JPEG", quality=95)
    img.save(fixtures_dir / "sample.png", format="PNG")
    img.save(fixtures_dir / "sample.bmp", format="BMP")
    img.save(fixtures_dir / "sample.webp", format="WEBP", quality=95)
    img.save(fixtures_dir / "sample.tiff", format="TIFF")
    
    # GIF format requires palette (P) mode or quantize
    gif_img = img.quantize(colors=256)
    gif_img.save(fixtures_dir / "sample.gif", format="GIF")
    
    # 2. Extension spoofing fixture: fake_image.jpg (text file with .jpg extension)
    (fixtures_dir / "fake_image.jpg").write_text(
        "This is an ASCII text file pretending to be a JPEG image.\nMagic bytes do not match JPEG signature.",
        encoding="utf-8"
    )
    
    # 3. Corrupted / malformed fixture: malformed_image.jpg
    # Starts with valid JPEG SOI and JFIF header, then truncated garbage
    malformed_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00" + b"\x00" * 30
    (fixtures_dir / "malformed_image.jpg").write_bytes(malformed_bytes)
    
    # 4. Decompression bomb fixture: bomb_image.png (IHDR claiming 100,000 x 100,000 = 10B pixels, 73 bytes file)
    ihdr_data = struct.pack(">IIBBBBB", 100_000, 100_000, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xffffffff)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc
    raw_data = zlib.compress(b"")
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + raw_data) & 0xffffffff)
    idat_chunk = struct.pack(">I", len(raw_data)) + b"IDAT" + raw_data + idat_crc
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xffffffff)
    iend_chunk = struct.pack(">I", 0) + b"IEND" + iend_crc
    bomb_bytes = b"\x89PNG\r\n\x1a\n" + ihdr_chunk + idat_chunk + iend_chunk
    (fixtures_dir / "bomb_image.png").write_bytes(bomb_bytes)
    
    # 5. Write expected_values.json
    expected_values = {
        "sample.jpg": {
            "width": 800,
            "height": 600,
            "format": "JPEG",
            "mode": "RGB",
            "top_left_marker": "RED"
        },
        "sample.png": {
            "width": 800,
            "height": 600,
            "format": "PNG",
            "mode": "RGB",
            "top_left_marker": "RED"
        },
        "sample.gif": {
            "width": 800,
            "height": 600,
            "format": "GIF",
            "mode": "P",
            "top_left_marker": "RED"
        },
        "sample.bmp": {
            "width": 800,
            "height": 600,
            "format": "BMP",
            "mode": "RGB",
            "top_left_marker": "RED"
        },
        "sample.webp": {
            "width": 800,
            "height": 600,
            "format": "WEBP",
            "mode": "RGB",
            "top_left_marker": "RED"
        },
        "sample.tiff": {
            "width": 800,
            "height": 600,
            "format": "TIFF",
            "mode": "RGB",
            "top_left_marker": "RED"
        },
        "fake_image.jpg": {
            "is_valid_image": False,
            "reason": "Text file with image extension"
        },
        "malformed_image.jpg": {
            "is_valid_image": False,
            "reason": "Truncated / corrupted JPEG stream"
        },
        "bomb_image.png": {
            "is_valid_image": False,
            "reason": "Decompression bomb claiming 100,000 x 100,000 pixels"
        }
    }
    
    (fixtures_dir / "expected_values.json").write_text(json.dumps(expected_values, indent=2), encoding="utf-8")
    print("Successfully generated all fixtures and expected_values.json.")

if __name__ == "__main__":
    generate_fixtures()
