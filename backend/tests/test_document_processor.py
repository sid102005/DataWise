import pytest
import json
from pathlib import Path
from backend.processors.document import DocumentProcessor
from backend.models.schemas import Plan, Step, ValidationResult

FIXTURES_DIR = Path("tests/fixtures/documents")
EXPECTED = json.loads((FIXTURES_DIR / "expected_values.json").read_text(encoding="utf-8"))

@pytest.fixture
def doc_proc():
    return DocumentProcessor()

def create_plan(tool_name: str) -> Plan:
    return Plan(
        plan_id="p-1",
        session_id="s-1",
        objectives=[],
        steps=[
            Step(
                step_number=1,
                tool_name=tool_name,
                description=f"Run {tool_name}",
                parameters={},
                expected_output="Success"
            )
        ]
    )

def test_extract_text_txt(doc_proc):
    file_path = FIXTURES_DIR / "sample.txt"
    plan = create_plan("extract_text")
    result = doc_proc.execute(file_path, plan)
    assert EXPECTED["sample.txt"]["text"] in result["text"]

def test_extract_text_md(doc_proc):
    file_path = FIXTURES_DIR / "sample.md"
    plan = create_plan("extract_text")
    result = doc_proc.execute(file_path, plan)
    assert EXPECTED["sample.md"]["text"] in result["text"]

def test_extract_text_docx(doc_proc):
    file_path = FIXTURES_DIR / "sample.docx"
    plan = create_plan("extract_text")
    result = doc_proc.execute(file_path, plan)
    for sub in EXPECTED["sample.docx"]["substrings"]:
        assert sub in result["text"]

def test_extract_text_pdf(doc_proc):
    file_path = FIXTURES_DIR / "sample.pdf"
    plan = create_plan("extract_text")
    result = doc_proc.execute(file_path, plan)
    for sub in EXPECTED["sample.pdf"]["substrings"]:
        assert sub in result["text"]

def test_extract_tables_docx(doc_proc):
    file_path = FIXTURES_DIR / "sample.docx"
    plan = create_plan("extract_tables")
    result = doc_proc.execute(file_path, plan)
    tables = result["tables"]
    assert len(tables) > 0
    assert tables[0] == EXPECTED["sample.docx"]["table"]

def test_count_words_txt(doc_proc):
    file_path = FIXTURES_DIR / "sample.txt"
    plan = create_plan("count_words")
    result = doc_proc.execute(file_path, plan)
    assert result["word_count"] == EXPECTED["sample.txt"]["word_count"]

def test_count_words_md(doc_proc):
    file_path = FIXTURES_DIR / "sample.md"
    plan = create_plan("count_words")
    result = doc_proc.execute(file_path, plan)
    assert result["word_count"] == EXPECTED["sample.md"]["word_count"]

def test_identify_headings_md(doc_proc):
    file_path = FIXTURES_DIR / "sample.md"
    plan = create_plan("identify_headings")
    result = doc_proc.execute(file_path, plan)
    assert result["headings"] == EXPECTED["sample.md"]["headings"]

def test_identify_headings_docx(doc_proc):
    file_path = FIXTURES_DIR / "sample.docx"
    plan = create_plan("identify_headings")
    result = doc_proc.execute(file_path, plan)
    assert result["headings"] == EXPECTED["sample.docx"]["headings"]

def test_profile_scanned_pdf(doc_proc):
    file_path = FIXTURES_DIR / "sample_scanned.pdf"
    profile = doc_proc.profile(file_path)
    assert profile["has_text_layer"] == False

def test_ocr_not_supported(doc_proc):
    file_path = FIXTURES_DIR / "sample_scanned.pdf"
    plan = create_plan("extract_text_ocr")
    with pytest.raises(ValueError) as exc:
        doc_proc.execute(file_path, plan)
    assert "OCR is not supported" in str(exc.value)

def test_validation_failure_scanned_pdf_extract_text(doc_proc):
    # This proves validation catches a failure. 
    # If the file has a text layer, extract_text MUST return text.
    # We will pass a bad after_state pretending extract_text failed on sample.pdf 
    file_path = FIXTURES_DIR / "sample.pdf"
    plan = create_plan("extract_text")
    # Pretend it returned empty text
    bad_result = {"text": ""}
    
    validation = doc_proc.validate_output(file_path, bad_result, plan)
    assert validation.is_valid == False
    assert "returned empty string but source .pdf has a text layer" in validation.checks_failed[0]

def test_end_to_end_export(doc_proc, tmp_path):
    file_path = FIXTURES_DIR / "sample.pdf"
    plan = create_plan("extract_text")
    result = doc_proc.execute(file_path, plan)
    
    output_file = doc_proc.export(result, "txt", tmp_path)
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    for sub in EXPECTED["sample.pdf"]["substrings"]:
        assert sub in content
