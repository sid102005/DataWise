from pathlib import Path
from typing import Any, Tuple, List, Dict
import pymupdf as fitz
from docx import Document as DocxDocument
import re

from backend.processors.base import FileProcessor
from backend.models.schemas import ValidationResult, Plan, Step

class DocumentProcessor(FileProcessor):
    
    def __init__(self):
        self._cache: dict = {}
        
    def cleanup(self, session_id: str) -> None:
        # Clear any cached items related to this session/file
        # (For now our cache just uses file_path as key, so we can clear all or iterate)
        keys_to_delete = [k for k in self._cache.keys() if session_id in str(k)]
        for k in keys_to_delete:
            del self._cache[k]
    
    def profile(self, file_path: Path, session_id: str = "") -> dict:
        ext = file_path.suffix.lower()
        profile_data = {
            "file_format": ext.lstrip("."),
            "page_count": 0,
            "paragraph_count": 0,
            "word_count": 0,
            "has_text_layer": False
        }
        
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                profile_data["page_count"] = len(doc)
                text = ""
                for page in doc:
                    text += page.get_text()
                
                # If we get meaningful text out of the PDF, it has a text layer
                clean_text = text.strip()
                if len(clean_text) > 10:
                    profile_data["has_text_layer"] = True
                    profile_data["word_count"] = len(clean_text.split())
                doc.close()
            except Exception:
                pass
                
        elif ext == ".docx":
            try:
                doc = DocxDocument(file_path)
                profile_data["paragraph_count"] = len(doc.paragraphs)
                text = " ".join([p.text for p in doc.paragraphs])
                profile_data["word_count"] = len(text.split())
                profile_data["has_text_layer"] = True
            except Exception:
                pass
                
        elif ext in {".txt", ".md"}:
            try:
                text = file_path.read_text(encoding="utf-8")
                profile_data["word_count"] = len(text.split())
                profile_data["has_text_layer"] = True
            except Exception:
                pass
                
        return profile_data

    def validate_input(self, file_path: Path, operation: Any) -> Tuple[bool, str]:
        # Basic validation: ensure file exists
        if not file_path.exists():
            return False, "File not found"
            
        return True, ""
        
    def _extract_text_pdf(self, file_path: Path) -> str:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        
        if not text.strip():
            return "No extractable text, OCR unavailable"
        return text

    def _extract_text_docx(self, file_path: Path) -> str:
        doc = DocxDocument(file_path)
        text = []
        for p in doc.paragraphs:
            if p.text.strip():
                text.append(p.text.strip())
        return "\n".join(text)
        
    def _extract_tables_docx(self, file_path: Path) -> List[List[List[str]]]:
        doc = DocxDocument(file_path)
        tables = []
        for table in doc.tables:
            grid = []
            for row in table.rows:
                grid.append([cell.text.strip() for cell in row.cells])
            tables.append(grid)
        return tables

    def execute(self, file_path: Path, structured_operation: Any, **kwargs) -> Any:
        # structured_operation is a Plan
        ext = file_path.suffix.lower()
        
        # We will execute each step sequentially.
        # Since document processing might just return extracted text or tables, 
        # we accumulate results in a dict.
        
        results = {
            "text": "",
            "tables": [],
            "metadata": {},
            "word_count": 0,
            "headings": [],
            "step_results": []
        }
        
        # Pre-load text if needed for general operations
        base_text = ""
        if ext == ".pdf":
            base_text = self._extract_text_pdf(file_path)
        elif ext == ".docx":
            base_text = self._extract_text_docx(file_path)
        elif ext in {".txt", ".md"}:
            base_text = file_path.read_text(encoding="utf-8", errors="replace")
            
        for step in structured_operation.steps:
            tool = step.tool_name
            
            if tool == "extract_text":
                results["text"] = base_text
                
            elif tool == "extract_text_ocr":
                # OCR is disabled
                raise ValueError("OCR is not supported on this system (Tesseract missing).")
                
            elif tool == "extract_tables":
                if ext == ".docx":
                    results["tables"] = self._extract_tables_docx(file_path)
                elif ext == ".pdf":
                    # PDF table extraction using PyMuPDF (simple heuristic)
                    doc = fitz.open(file_path)
                    for page in doc:
                        tabs = page.find_tables()
                        for tab in tabs:
                            results["tables"].append(tab.extract())
                    doc.close()
                else:
                    results["tables"] = []
                    
            elif tool == "extract_metadata":
                results["metadata"] = self.profile(file_path)
                
            elif tool == "convert_format":
                # text is already extracted. the export method will handle saving it to target_format
                results["text"] = base_text
                
            elif tool == "clean_text":
                # whitespace normalization
                cleaned = re.sub(r'\s+', ' ', base_text).strip()
                results["text"] = cleaned
                
            elif tool == "count_words":
                results["word_count"] = len(base_text.split())
                
            elif tool == "identify_headings":
                if ext == ".md":
                    headings = []
                    for line in base_text.splitlines():
                        line = line.strip()
                        if line.startswith("#"):
                            headings.append(line.lstrip("#").strip())
                    results["headings"] = headings
                elif ext == ".docx":
                    doc = DocxDocument(file_path)
                    headings = []
                    for p in doc.paragraphs:
                        if p.style.name.startswith("Heading"):
                            headings.append(p.text.strip())
                    results["headings"] = headings
                elif ext == ".pdf":
                    # Heuristic based heading detection for PDF (e.g. font size > 12)
                    doc = fitz.open(file_path)
                    headings = []
                    for page in doc:
                        blocks = page.get_text("dict")["blocks"]
                        for b in blocks:
                            if "lines" in b:
                                for l in b["lines"]:
                                    for s in l["spans"]:
                                        if s["size"] > 14 and s["text"].strip():
                                            headings.append(s["text"].strip())
                    doc.close()
                    results["headings"] = headings

            from backend.models.schemas import ExecutionResult
            import time
            results["step_results"].append(
                ExecutionResult(
                    step_number=step.step_number,
                    tool_name=tool,
                    success=True,
                    rows_before=0,
                    rows_after=0,
                    columns_before=0,
                    columns_after=0,
                    summary=step.expected_output,
                    execution_time_ms=0.0
                )
            )
                    
        return results

    def validate_output(self, before_state: Any, after_state: Any, structured_operation: Any, **kwargs) -> ValidationResult:
        # before_state is typically file_path
        # after_state is the `results` dictionary from execute()
        
        errors = []
        checks_passed = []
        ext = before_state.suffix.lower()
        
        for step in structured_operation.steps:
            tool = step.tool_name
            
            if tool == "extract_text":
                text = after_state.get("text", "")
                profile = self.profile(before_state)
                has_text = profile.get("has_text_layer", False)
                
                if text == "No extractable text, OCR unavailable" or not has_text:
                    errors.append(f"extract_text failed: source {ext} has no extractable text layer and OCR is unavailable.")
                elif not text or len(text.strip()) == 0:
                    errors.append(f"extract_text returned empty string but source {ext} has a text layer.")
                else:
                    checks_passed.append("extracted_text_non_empty: true")
                    
            elif tool == "clean_text":
                text = after_state.get("text", "")
                if not text or text == "No extractable text, OCR unavailable":
                    errors.append("clean_text failed: no valid text available to normalize.")
                elif re.search(r'\s{2,}', text):
                    errors.append("clean_text failed: multiple consecutive whitespace characters detected.")
                else:
                    checks_passed.append("whitespace_normalized: true")
                    
            elif tool == "extract_tables":
                tables = after_state.get("tables", [])
                if len(tables) == 0 and ext == ".docx":
                    doc = DocxDocument(before_state)
                    if len(doc.tables) > 0:
                        errors.append(f"extract_tables returned 0 tables but source DOCX contains {len(doc.tables)} tables.")
                    else:
                        checks_passed.append("tables_extracted: true (0 tables in document)")
                else:
                    checks_passed.append(f"tables_extracted: true ({len(tables)} tables)")
                        
            elif tool == "count_words":
                base_text = ""
                if ext == ".pdf":
                    base_text = self._extract_text_pdf(before_state)
                elif ext == ".docx":
                    base_text = self._extract_text_docx(before_state)
                elif ext in {".txt", ".md"}:
                    base_text = before_state.read_text(encoding="utf-8", errors="replace")
                
                expected_count = len(base_text.split())
                actual_count = after_state.get("word_count", 0)
                if expected_count != actual_count:
                    errors.append(f"count_words mismatch: extracted {actual_count}, verified {expected_count}")
                else:
                    checks_passed.append(f"word_count_verified: {actual_count}")

            elif tool == "identify_headings":
                headings = after_state.get("headings", [])
                checks_passed.append(f"headings_identified: {len(headings)} headings found")

            elif tool == "extract_metadata":
                metadata = after_state.get("metadata", {})
                if not metadata:
                    errors.append("extract_metadata failed: metadata is empty")
                else:
                    checks_passed.append("metadata_extracted: true")

            elif tool == "convert_format":
                text = after_state.get("text", "")
                if not text or text == "No extractable text, OCR unavailable":
                    errors.append("convert_format failed: no valid text to convert")
                else:
                    checks_passed.append("format_converted_text_ready: true")
                    
        if errors:
            return ValidationResult(is_valid=False, checks_passed=checks_passed, checks_failed=errors)
        return ValidationResult(is_valid=True, checks_passed=checks_passed, checks_failed=[])

    def export(self, state: Any, output_format: str, output_dir: Path, filename_stem: str = "result") -> Path:
        output_format = output_format.lower().lstrip(".")
        output_file = output_dir / f"result.{output_format}"
        
        if output_format in {"txt", "md"}:
            output_file.write_text(state.get("text", ""), encoding="utf-8")
        elif output_format == "json":
            import json
            output_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
            
        return output_file
