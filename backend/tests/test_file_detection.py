import pytest
from pathlib import Path
from backend.core.file_detection import detect_file, FileCategory
from backend.processors.registry import get_processor, UnsupportedFileTypeError

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_detect_legitimate_csv():
    res = detect_file(FIXTURES_DIR / "sample.csv")
    assert res.detected_category == FileCategory.TABULAR

def test_detect_legitimate_xlsx():
    res = detect_file(FIXTURES_DIR / "sample.xlsx")
    assert res.detected_category == FileCategory.TABULAR

def test_detect_legitimate_json():
    res = detect_file(FIXTURES_DIR / "sample.json")
    assert res.detected_category == FileCategory.TABULAR

def test_detect_mismatched_extension(tmp_path):
    # A text file renamed to CSV
    mismatched_file = tmp_path / "fake.csv"
    # Actually just a plain string without tabular structure, or better yet, some random PDF bytes
    mismatched_file.write_bytes(b"%PDF-1.4\n1 0 obj...")
    
    res = detect_file(mismatched_file)
    # Magic bytes say PDF -> DOCUMENT
    # Extension says CSV -> TABULAR
    # Magic bytes should override
    assert res.detected_category == FileCategory.DOCUMENT

def test_detect_json_masquerading_as_csv(tmp_path):
    mismatched_file = tmp_path / "fake.csv"
    mismatched_file.write_bytes(b'{"key": "value"}')
    
    res = detect_file(mismatched_file)
    # Starts with '{', magic heuristics pick up TABULAR (for JSON)
    # Ext is CSV (TABULAR). Both agree on TABULAR.
    assert res.detected_category == FileCategory.TABULAR

def test_registry_unsupported_type():
    with pytest.raises(UnsupportedFileTypeError):
        get_processor(FileCategory.PRESENTATION)

def test_detect_legitimate_md(tmp_path):
    md_file = tmp_path / "sample.md"
    md_file.write_text("# Hello World")
    res = detect_file(md_file)
    assert res.detected_category == FileCategory.DOCUMENT

def test_detect_rejects_legacy_doc(tmp_path):
    from backend.core.exceptions import FileValidationError
    doc_file = tmp_path / "legacy.doc"
    doc_file.touch()
    with pytest.raises(FileValidationError) as exc:
        detect_file(doc_file)
    assert "Legacy Word format (.doc) detected but rejected" in str(exc.value)

def test_detect_rejects_legacy_docm(tmp_path):
    from backend.core.exceptions import FileValidationError
    docm_file = tmp_path / "macro.docm"
    docm_file.touch()
    with pytest.raises(FileValidationError) as exc:
        detect_file(docm_file)
    assert "Legacy Word format (.docm) detected but rejected" in str(exc.value)
