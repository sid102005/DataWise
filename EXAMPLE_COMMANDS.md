# DataWise Example Commands & Prompts

This guide provides tested, working prompt commands for each supported format processor.

For a full how-to (start app, test files, every feature checklist), see **[`USAGE_GUIDE.md`](USAGE_GUIDE.md)**.

---

## 1. Image Processor (JPEG, PNG, GIF, BMP, WEBP, TIFF)

### Resize Image
- **Prompt:** `resize this image to 1024x1024`
- **Output:** Resized image with exact (1024, 1024) dimensions.

### Crop Image
- **Prompt:** `crop image to 50, 50, 450, 350`
- **Output:** Extracted sub-region of dimensions 400x300.

### Rotate Image
- **Prompt:** `rotate this image by 90 degrees`
- **Output:** Rotated image with swapped dimensions (e.g. 800x600 -> 600x800) and content relocated.
- **Alternative:** `rotate by 180 degrees`, `rotate by 270 degrees`

### Convert Format
- **Prompt:** `convert image to PNG`
- **Output:** Format converted to PNG (verified by header magic bytes).
- **Alternative:** `convert to webp`, `convert to jpg`

### Compress Image
- **Prompt:** `compress this image with quality 50`
- **Output:** Compressed lossy image with measured file size reduction.

### Extract Metadata
- **Prompt:** `extract image metadata and dimensions`
- **Output:** JSON containing dimensions, color mode, file size, and EXIF tags.

---

## 2. Document Processor (PDF, DOCX, TXT, MD)

### Extract Text
- **Prompt:** `Extract the text from this PDF`
- **Output:** Text extracted from document and normalized.

### Extract Tables
- **Prompt:** `Extract tables from this document`
- **Output:** Extracted table structures.

### Count Words & Headings
- **Prompt:** `Count the words in this document`
- **Output:** Word count and heading hierarchy.

---

## 3. Tabular Processor (CSV, XLSX, JSON)

### Column Operations
- **Prompt:** `remove the Phone column`
- **Prompt:** `add a column called Senior`
- **Prompt:** `rename CustomerID to ClientID`

### Cleaning & Missing Values
- **Prompt:** `clean missing values and drop duplicate rows`

### Aggregation & Visualization
- **Prompt:** `group by Region and sum Sales`
- **Prompt:** `bar chart of purchases by region`

---

## 4. Audio Processor (WAV, MP3) — Phase 12

### Extract Audio Metadata
- **Prompt:** `extract audio metadata`
- **Output:** Sample rate, duration, channels, audio format, and embedded player.

### Trim Audio
- **Prompt:** `trim this audio to first 2 seconds`
- **Output:** New trimmed audio file with duration exactly 2.0s.

### Convert Format & Compress
- **Prompt:** `convert audio to mp3`
- **Prompt:** `compress audio to 128k`
- **Output:** Re-encoded audio file with lower bitrate and reduced file size.

---

## 5. Video Processor (MP4, MOV, AVI, MKV, WEBM) — Phase 12

### Extract Video Metadata
- **Prompt:** `extract video metadata`
- **Output:** Resolution, duration, video codec, audio codec, framerate, and native video player.

### Trim Video
- **Prompt:** `trim this video to first 2 seconds`
- **Output:** Cut video stream of exactly 2.0s duration.

### Extract Video Frame
- **Prompt:** `extract frame at 1 second`
- **Output:** High-resolution PNG image captured at the exact timestamp.

### Resize Video & Extract Audio
- **Prompt:** `resize video to 640x480`
- **Prompt:** `extract audio from this video`
- **Output:** Rescaled video or isolated audio stream in WAV/MP3.

---

## 6. Archive Processor (ZIP, TAR, GZ) — Phase 13

### List Contents & Profile
- **Prompt:** `list contents and profile this archive`
- **Output:** Formatted table of archive entries with detected categories, original sizes, and total uncompressed volume.

### Extract and Process Inner Files
- **Prompt:** `extract and process all files in archive`
- **Output:** Recursive routing of inner files to domain processors, returning an audit table of actions and a safe repackaged result archive.

### Security Defenses (Automatic)
- Files with path traversal (`../../evil.txt`) are rejected with `ZipSlipError`.
- Archives declaring uncompressed volume > 500MB are rejected with `ArchiveBombError`.
- Archives exceeding 10,000 files are rejected with entry count cap error.

---

## 7. Multi-File & Batch Processing — Phase 13

### Batch Image Resize
- **Upload:** Multiple images (`img1.jpg`, `img2.jpg`, `img3.jpg`)
- **Prompt:** `resize all images to 100x100`
- **Output:** Batch summary card, per-file status table, and consolidated `result.zip` containing all resized images.

### Batch Tabular Cleaning
- **Upload:** Multiple CSV files (`data1.csv`, `data2.csv`, `data3.csv`)
- **Prompt:** `clean tabular data and remove missing values`
- **Output:** All datasets cleaned and packed into `result.zip`.

### Heterogeneous / Mixed-Category Batch
- **Upload:** Mixed files (`part1.csv`, `photo.jpg`)
- **Prompt:** `clean tabular data and remove missing values`
- **Output:** `part1.csv` is cleaned successfully; `photo.jpg` is safely excluded as non-applicable; partial success (`1/2 succeeded, 1 excluded`) is honestly reported with full audit trail.
