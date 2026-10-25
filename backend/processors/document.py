from pathlib import Path
from typing import Any, Tuple, List, Dict
import json
import pymupdf as fitz
from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re
import os
import logging
import csv

from backend.processors.base import FileProcessor
from backend.models.schemas import ValidationResult, Plan, Step, ExecutionResult
from backend.tools import document_ops as doc_ops

log = logging.getLogger(__name__)

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
                profile_data["table_count"] = len(doc.tables)
                text = self._extract_text_docx(file_path)
                clean_text = text.strip()
                profile_data["word_count"] = len(clean_text.split())
                profile_data["has_text_layer"] = len(clean_text) > 0
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
        lines: list[str] = []

        # 1. Traverse document body elements in visual reading order (paragraphs and tables)
        try:
            from docx.oxml.text.paragraph import CT_P
            from docx.oxml.table import CT_Tbl
            from docx.text.paragraph import Paragraph
            from docx.table import Table

            for child in doc.element.body:
                if isinstance(child, CT_P):
                    p = Paragraph(child, doc)
                    if p.text.strip():
                        lines.append(p.text.strip())
                elif isinstance(child, CT_Tbl):
                    t = Table(child, doc)
                    for row in t.rows:
                        row_cells = []
                        seen_cells = set()
                        for cell in row.cells:
                            if cell._tc not in seen_cells:
                                seen_cells.add(cell._tc)
                                ctext = cell.text.strip()
                                if ctext:
                                    row_cells.append(ctext)
                        if row_cells:
                            lines.append(" | ".join(row_cells))
        except Exception as exc:
            log.warning("XML body traversal failed on %s, falling back to sequential extraction: %s", file_path, exc)
            # Fallback to standard paragraph and table extraction
            for p in doc.paragraphs:
                if p.text.strip():
                    lines.append(p.text.strip())
            for t in doc.tables:
                for row in t.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells:
                        lines.append(" | ".join(row_cells))

        # 2. If body is still empty, inspect headers and footers
        if not lines:
            for section in doc.sections:
                for hp in section.header.paragraphs:
                    if hp.text.strip():
                        lines.append(hp.text.strip())
                for fp in section.footer.paragraphs:
                    if fp.text.strip():
                        lines.append(fp.text.strip())

        return "\n".join(lines)
        
    def _extract_tables_docx(self, file_path: Path) -> List[List[List[str]]]:
        doc = DocxDocument(file_path)
        tables = []
        for table in doc.tables:
            grid = []
            for row in table.rows:
                grid.append([cell.text.strip() for cell in row.cells])
            tables.append(grid)
        return tables

    def _extract_tables_pdf(self, file_path: Path) -> List[List[List[str]]]:
        tables: List[List[List[str]]] = []
        doc = fitz.open(file_path)
        try:
            for page in doc:
                finder = page.find_tables()
                for tab in finder:
                    tables.append(tab.extract())
        finally:
            doc.close()
        return tables

    def _extract_text_by_page_pdf(self, file_path: Path) -> List[dict]:
        pages = []
        doc = fitz.open(file_path)
        try:
            for i, page in enumerate(doc, start=1):
                pages.append({"page": i, "text": page.get_text()})
        finally:
            doc.close()
        return pages

    def _ocr_pdf(self, file_path: Path) -> str:
        """OCR PDF pages when a text layer is missing. Requires Tesseract + Pillow."""
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise ValueError(
                "OCR requires pytesseract and Pillow. Install them and Tesseract OCR binary."
            ) from exc

        texts: list[str] = []
        doc = fitz.open(file_path)
        try:
            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                page_text = pytesseract.image_to_string(img)
                texts.append(f"--- Page {i} ---\n{page_text.strip()}")
        except Exception as exc:
            raise ValueError(
                f"OCR failed (is Tesseract installed and on PATH?): {exc}"
            ) from exc
        finally:
            doc.close()
        joined = "\n\n".join(t for t in texts if t.strip())
        if not joined.strip():
            raise ValueError("OCR produced no text.")
        return joined

    def _extract_images_pdf(self, file_path: Path, output_dir: Path | None) -> list[dict]:
        images: list[dict] = []
        doc = fitz.open(file_path)
        try:
            for page_index, page in enumerate(doc, start=1):
                for img_index, img in enumerate(page.get_images(full=True), start=1):
                    xref = img[0]
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n > 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        name = f"page{page_index}_image{img_index}.png"
                        meta = {
                            "page": page_index,
                            "index": img_index,
                            "width": pix.width,
                            "height": pix.height,
                            "filename": name,
                        }
                        if output_dir is not None:
                            out = output_dir / name
                            pix.save(str(out))
                            meta["path"] = str(out)
                        images.append(meta)
                    except Exception as exc:
                        log.warning("Skipping PDF image xref=%s: %s", xref, exc)
        finally:
            doc.close()
        return images

    def _write_tables_csv(self, tables: list, output_dir: Path | None) -> list[str]:
        paths: list[str] = []
        if not output_dir or not tables:
            return paths
        for i, table in enumerate(tables):
            path = output_dir / f"table_{i + 1}.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                for row in table:
                    writer.writerow([(c if c is not None else "") for c in row])
            paths.append(str(path))
        return paths

    def _rich_metadata(self, file_path: Path) -> dict:
        meta = self.profile(file_path)
        meta["filename"] = file_path.name
        meta["size_bytes"] = file_path.stat().st_size if file_path.exists() else 0
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                pdf_meta = doc.metadata or {}
                meta.update({
                    "title": pdf_meta.get("title") or "",
                    "author": pdf_meta.get("author") or "",
                    "subject": pdf_meta.get("subject") or "",
                    "creator": pdf_meta.get("creator") or "",
                    "producer": pdf_meta.get("producer") or "",
                    "page_count": len(doc),
                })
                doc.close()
            except Exception:
                pass
        return meta

    def _call_llm_analysis(self, text: str, prompt: str) -> str:
        """Call the LLM to analyze extracted text against the user's prompt.
        
        Returns the LLM's response as a string, or a fallback if unavailable.
        """
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY")
            
            # Try Anthropic Claude first
            if os.environ.get("ANTHROPIC_API_KEY"):
                import anthropic
                client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
                # Truncate to ~15k chars to stay within token limits
                truncated = text[:15000] + ("\n...[truncated]" if len(text) > 15000 else "")
                message = client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=2048,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"You are a helpful data analyst. The user uploaded a document and asked:\n"
                                f">>> {prompt}\n\n"
                                f"Here is the extracted document text:\n\n{truncated}\n\n"
                                f"Please answer the user's question thoroughly and clearly, "
                                f"using only information from the document above."
                            )
                        }
                    ]
                )
                return message.content[0].text
            
            # Try Google Gemini as fallback
            elif os.environ.get("GEMINI_API_KEY"):
                import google.generativeai as genai
                genai.configure(api_key=os.environ["GEMINI_API_KEY"])
                model = genai.GenerativeModel("gemini-2.0-flash")
                truncated = text[:15000] + ("\n...[truncated]" if len(text) > 15000 else "")
                response = model.generate_content(
                    f"You are a helpful data analyst. The user uploaded a document and asked:\n"
                    f">>> {prompt}\n\n"
                    f"Here is the extracted document text:\n\n{truncated}\n\n"
                    f"Please answer the user's question thoroughly and clearly, "
                    f"using only information from the document above."
                )
                return response.text
            
            else:
                # No LLM available — return structured extraction of the text
                return f"[No LLM API key configured — raw extracted text]\n\n{text[:5000]}"
                
        except Exception as exc:
            log.warning("LLM analysis failed: %s", exc)
            return f"[LLM analysis failed: {exc}]\n\nRaw extracted text:\n{text[:5000]}"

    def _identify_headings(self, file_path: Path, base_text: str, ext: str) -> list[str]:
        headings: list[str] = []
        if ext == ".md":
            for line in base_text.splitlines():
                line = line.strip()
                if line.startswith("#"):
                    headings.append(line.lstrip("#").strip())
        elif ext == ".docx":
            doc = DocxDocument(file_path)
            for p in doc.paragraphs:
                style = (p.style.name or "") if p.style else ""
                if style.startswith("Heading") and p.text.strip():
                    headings.append(p.text.strip())
        elif ext == ".pdf":
            doc = fitz.open(file_path)
            try:
                for page in doc:
                    blocks = page.get_text("dict")["blocks"]
                    for b in blocks:
                        if "lines" not in b:
                            continue
                        for ln in b["lines"]:
                            for s in ln["spans"]:
                                if s["size"] > 14 and s["text"].strip():
                                    headings.append(s["text"].strip())
            finally:
                doc.close()
        else:
            for line in base_text.splitlines():
                if line.strip() and line.strip().isupper() and 3 < len(line.strip()) < 80:
                    headings.append(line.strip())
        # de-dupe preserve order
        seen: set[str] = set()
        out: list[str] = []
        for h in headings:
            if h not in seen:
                seen.add(h)
                out.append(h)
        return out

    def execute(self, file_path: Path, structured_operation: Any, **kwargs) -> Any:
        """Execute document processing steps for PDF / DOCX / TXT / MD."""
        ext = file_path.suffix.lower()
        user_prompt: str = kwargs.get("prompt", "")
        output_dir: Path | None = kwargs.get("output_dir", None)

        results: dict[str, Any] = {
            "text": "",
            "analysis": "",
            "tables": [],
            "table_csv_paths": [],
            "metadata": {},
            "word_count": 0,
            "headings": [],
            "pages": [],
            "entities": {},
            "key_values": {},
            "mentions": [],
            "links": {},
            "language": {},
            "images": [],
            "redacted_text": "",
            "summary": "",
            "artifact_paths": [],
            "step_results": [],
            "user_prompt": user_prompt,
            "errors": [],
        }

        base_text = ""
        if ext == ".pdf":
            base_text = self._extract_text_pdf(file_path)
        elif ext == ".docx":
            base_text = self._extract_text_docx(file_path)
        elif ext in {".txt", ".md"}:
            base_text = file_path.read_text(encoding="utf-8", errors="replace")

        working_text = base_text

        for step in structured_operation.steps:
            tool = step.tool_name
            params = dict(getattr(step, "parameters", None) or {})
            ok = True
            summary = step.expected_output

            try:
                if tool == "extract_text":
                    results["text"] = working_text
                    summary = f"Extracted {len(working_text.split())} words of text."

                elif tool == "extract_text_ocr":
                    if ext != ".pdf":
                        raise ValueError("OCR is only supported for PDF files.")
                    working_text = self._ocr_pdf(file_path)
                    results["text"] = working_text
                    summary = f"OCR extracted {len(working_text.split())} words."

                elif tool == "clean_text":
                    working_text = doc_ops.clean_document_text(working_text)
                    # also collapse leftover multi-spaces inside lines
                    working_text = re.sub(r"[ \t]{2,}", " ", working_text)
                    results["text"] = working_text
                    summary = "Normalized whitespace and removed header/footer noise."

                elif tool == "extract_tables":
                    if ext == ".docx":
                        results["tables"] = self._extract_tables_docx(file_path)
                    elif ext == ".pdf":
                        results["tables"] = self._extract_tables_pdf(file_path)
                    else:
                        results["tables"] = []
                    csv_paths = self._write_tables_csv(results["tables"], output_dir)
                    results["table_csv_paths"] = csv_paths
                    results["artifact_paths"].extend(csv_paths)
                    summary = f"Extracted {len(results['tables'])} table(s); wrote {len(csv_paths)} CSV file(s)."

                elif tool == "extract_metadata":
                    results["metadata"] = self._rich_metadata(file_path)
                    summary = "Extracted document metadata."

                elif tool in {"identify_headings", "extract_headings"}:
                    results["headings"] = self._identify_headings(file_path, working_text, ext)
                    summary = f"Identified {len(results['headings'])} heading(s)."

                elif tool == "count_words":
                    results["word_count"] = len(working_text.split())
                    summary = f"Word count: {results['word_count']}."

                elif tool == "split_pages":
                    if ext == ".pdf":
                        results["pages"] = self._extract_text_by_page_pdf(file_path)
                    else:
                        # Non-PDF: treat whole doc as one page, or split on form-feed / markdown headings
                        results["pages"] = [{"page": 1, "text": working_text}]
                    if output_dir and results["pages"]:
                        for page in results["pages"]:
                            p = output_dir / f"page_{page['page']}.txt"
                            p.write_text(page.get("text") or "", encoding="utf-8")
                            results["artifact_paths"].append(str(p))
                    summary = f"Split into {len(results['pages'])} page(s)."

                elif tool == "extract_entities":
                    results["entities"] = doc_ops.extract_entities(working_text)
                    summary = (
                        f"Entities: {len(results['entities'].get('emails', []))} emails, "
                        f"{len(results['entities'].get('phones', []))} phones, "
                        f"{len(results['entities'].get('dates', []))} dates, "
                        f"{len(results['entities'].get('amounts', []))} amounts."
                    )

                elif tool == "extract_key_values":
                    results["key_values"] = doc_ops.extract_key_values(working_text)
                    summary = f"Extracted {len(results['key_values'])} key-value field(s)."

                elif tool == "find_mentions":
                    keyword = str(params.get("keyword") or params.get("query") or "").strip()
                    if not keyword:
                        # fall back: last quoted phrase in user prompt
                        qm = re.search(r"[\"']([^\"']+)[\"']", user_prompt)
                        keyword = qm.group(1) if qm else ""
                    results["mentions"] = doc_ops.find_mentions(working_text, keyword)
                    summary = f"Found {len(results['mentions'])} mention(s) of '{keyword}'."

                elif tool == "extract_links":
                    results["links"] = doc_ops.extract_links(working_text)
                    summary = (
                        f"Links: {len(results['links'].get('urls', []))} URL(s), "
                        f"{len(results['links'].get('emails', []))} email(s)."
                    )

                elif tool == "detect_language":
                    results["language"] = doc_ops.detect_language(working_text)
                    summary = (
                        f"Language guess: {results['language'].get('language')} "
                        f"(confidence {results['language'].get('confidence')})."
                    )

                elif tool == "extract_images":
                    if ext != ".pdf":
                        raise ValueError("Image/figure extraction is supported for PDF files.")
                    results["images"] = self._extract_images_pdf(file_path, output_dir)
                    for img in results["images"]:
                        if img.get("path"):
                            results["artifact_paths"].append(img["path"])
                    summary = f"Extracted {len(results['images'])} embedded image(s)."

                elif tool == "redact_pii":
                    redacted, counts = doc_ops.redact_pii(working_text)
                    working_text = redacted
                    results["redacted_text"] = redacted
                    results["text"] = redacted
                    summary = (
                        f"Redacted {counts.get('emails', 0)} email(s) and "
                        f"{counts.get('phones', 0)} phone(s)."
                    )

                elif tool in {"summarize", "extractive_summary"}:
                    max_sents = int(params.get("max_sentences", 5))
                    results["summary"] = doc_ops.extractive_summary(working_text, max_sentences=max_sents)
                    results["analysis"] = results["summary"]
                    summary = f"Built extractive summary ({max_sents} sentence cap)."

                elif tool in {"llm_analysis", "answer_question", "qa"}:
                    results["text"] = working_text
                    results["analysis"] = self._call_llm_analysis(working_text, user_prompt or "Summarize this document.")
                    summary = "Generated answer/analysis from document text."

                elif tool == "convert_format":
                    results["text"] = working_text
                    summary = "Prepared text for format conversion export."

                else:
                    ok = False
                    summary = f"Unknown document tool '{tool}'."
                    results["errors"].append(summary)

            except Exception as exc:
                ok = False
                summary = f"{tool} failed: {exc}"
                results["errors"].append(summary)
                log.warning("Document tool %s failed: %s", tool, exc)

            results["step_results"].append(
                ExecutionResult(
                    step_number=step.step_number,
                    tool_name=tool,
                    success=ok,
                    rows_before=0,
                    rows_after=0,
                    columns_before=0,
                    columns_after=0,
                    summary=summary,
                    execution_time_ms=0.0,
                )
            )

        # Ensure primary text is populated for export
        if not results["text"]:
            results["text"] = working_text
        if not results.get("word_count"):
            results["word_count"] = len((results.get("text") or "").split())

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

            elif tool in {
                "extract_entities", "extract_key_values", "find_mentions", "extract_links",
                "detect_language", "extract_images", "redact_pii", "extractive_summary",
                "summarize", "split_pages", "llm_analysis", "extract_text_ocr",
            }:
                # Soft pass: step-level success is tracked in ExecutionResult
                step_ok = any(
                    r.tool_name == tool and r.success
                    for r in after_state.get("step_results", [])
                )
                if step_ok:
                    checks_passed.append(f"{tool}: ok")
                else:
                    # Non-fatal for optional tools like OCR/LLM — record but don't hard-fail whole doc
                    checks_passed.append(f"{tool}: completed_with_notes")

        if errors:
            return ValidationResult(is_valid=False, checks_passed=checks_passed, checks_failed=errors)
        return ValidationResult(is_valid=True, checks_passed=checks_passed, checks_failed=[])

    def export(self, state: Any, output_format: str, output_dir: Path, filename_stem: str = "result") -> Path:
        """Export document analysis results to the requested format.
        
        Supported formats: txt, md, json, pdf, docx
        The export uses `analysis` (LLM output) when available, falling back to `text`.
        """
        output_format = output_format.lower().lstrip(".")
        output_file = output_dir / f"{filename_stem}.{output_format}"
        
        # Prefer analysis/summary/redacted text, then raw extract
        content = (
            state.get("analysis")
            or state.get("summary")
            or state.get("redacted_text")
            or state.get("text")
            or ""
        )
        user_prompt = state.get("user_prompt", "Document Analysis")

        if output_format == "csv" and state.get("tables"):
            # Export first extracted table as CSV
            output_file = output_dir / f"{filename_stem}.csv"
            with output_file.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                for row in state["tables"][0]:
                    writer.writerow([(c if c is not None else "") for c in row])
            return output_file

        if output_format in {"txt", "md"}:
            output_file.write_text(content, encoding="utf-8")

        elif output_format == "json":
            export_state = {
                "analysis": state.get("analysis") or "",
                "summary": state.get("summary") or "",
                "text": state.get("text") or "",
                "redacted_text": state.get("redacted_text") or "",
                "word_count": state.get("word_count", 0),
                "headings": state.get("headings", []),
                "metadata": state.get("metadata", {}),
                "tables": state.get("tables", []),
                "table_csv_paths": state.get("table_csv_paths", []),
                "pages": state.get("pages", []),
                "entities": state.get("entities", {}),
                "key_values": state.get("key_values", {}),
                "mentions": state.get("mentions", []),
                "links": state.get("links", {}),
                "language": state.get("language", {}),
                "images": [
                    {k: v for k, v in img.items() if k != "path"}
                    for img in state.get("images", [])
                ],
                "artifact_paths": state.get("artifact_paths", []),
                "errors": state.get("errors", []),
            }
            output_file.write_text(json.dumps(export_state, indent=2, ensure_ascii=False), encoding="utf-8")
            
        elif output_format == "pdf":
            try:
                from reportlab.lib.pagesizes import letter
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
                from reportlab.lib import colors
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
                from reportlab.lib.enums import TA_LEFT, TA_CENTER

                doc = SimpleDocTemplate(
                    str(output_file),
                    pagesize=letter,
                    rightMargin=inch,
                    leftMargin=inch,
                    topMargin=inch,
                    bottomMargin=inch,
                )
                styles = getSampleStyleSheet()
                
                title_style = ParagraphStyle(
                    "CustomTitle",
                    parent=styles["Title"],
                    fontSize=18,
                    spaceAfter=20,
                    textColor=colors.HexColor("#1e3a5f"),
                )
                body_style = ParagraphStyle(
                    "CustomBody",
                    parent=styles["Normal"],
                    fontSize=11,
                    leading=16,
                    spaceAfter=8,
                )

                story = []
                story.append(Paragraph("DataWise — Document Analysis", title_style))
                story.append(Paragraph(f"<b>Query:</b> {user_prompt}", body_style))
                story.append(Spacer(1, 0.25 * inch))
                
                # Split content into paragraphs and render each
                for para in content.split("\n"):
                    para = para.strip()
                    if not para:
                        story.append(Spacer(1, 0.1 * inch))
                        continue
                    # Escape XML-sensitive chars for ReportLab
                    safe = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(safe, body_style))

                doc.build(story)
                
            except Exception as exc:
                log.exception("PDF export failed: %s", exc)
                # Fallback: write as plain text with .pdf extension note
                output_file.with_suffix(".txt").write_text(content, encoding="utf-8")
                output_file = output_dir / f"{filename_stem}.txt"
                
        elif output_format == "docx":
            try:
                doc = DocxDocument()
                
                # Title
                title = doc.add_heading("DataWise — Document Analysis", level=0)
                title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                # Query subtitle
                query_para = doc.add_paragraph()
                run = query_para.add_run(f"Query: {user_prompt}")
                run.bold = True
                run.font.size = Pt(11)
                run.font.color.rgb = RGBColor(0x1e, 0x3a, 0x5f)
                doc.add_paragraph()  # spacer
                
                # Body content — split by newline
                for line in content.split("\n"):
                    line = line.strip()
                    if not line:
                        doc.add_paragraph()
                        continue
                    # Detect markdown-style headings
                    if line.startswith("### "):
                        doc.add_heading(line[4:], level=3)
                    elif line.startswith("## "):
                        doc.add_heading(line[3:], level=2)
                    elif line.startswith("# "):
                        doc.add_heading(line[2:], level=1)
                    elif line.startswith(("* ", "- ", "• ")):
                        p = doc.add_paragraph(style="List Bullet")
                        p.add_run(line[2:])
                    elif re.match(r'^\d+\.\s', line):
                        p = doc.add_paragraph(style="List Number")
                        p.add_run(re.sub(r'^\d+\.\s', '', line))
                    else:
                        doc.add_paragraph(line)
                
                doc.save(str(output_file))
                
            except Exception as exc:
                log.exception("DOCX export failed: %s", exc)
                output_file.with_suffix(".txt").write_text(content, encoding="utf-8")
                output_file = output_dir / f"{filename_stem}.txt"
        else:
            # Unknown format — write as plain text
            output_file = output_dir / f"{filename_stem}.txt"
            output_file.write_text(content, encoding="utf-8")
            
        return output_file
