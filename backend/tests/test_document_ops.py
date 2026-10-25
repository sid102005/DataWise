"""Unit tests for deterministic document helpers."""

from backend.tools.document_ops import (
    extract_entities,
    extract_key_values,
    find_mentions,
    redact_pii,
    detect_language,
    extractive_summary,
    clean_document_text,
)


SAMPLE = """
Invoice No: INV-9
Email: alice@example.com
Phone: +1-555-010-2299
Amount: $1,250.00
Date: 2024-03-15
Website: https://example.com/x
Revenue increased. Revenue again.
"""


def test_extract_entities():
    ents = extract_entities(SAMPLE)
    assert "alice@example.com" in ents["emails"]
    assert any("555" in p for p in ents["phones"])
    assert any("example.com" in u for u in ents["urls"])
    assert ents["dates"]
    assert ents["amounts"]


def test_extract_key_values():
    kv = extract_key_values(SAMPLE)
    assert kv.get("Invoice No") == "INV-9"
    assert "alice@example.com" in kv.get("Email", "")


def test_find_mentions():
    hits = find_mentions(SAMPLE, "Revenue")
    assert len(hits) >= 2


def test_redact_pii():
    redacted, counts = redact_pii(SAMPLE)
    assert "[REDACTED_EMAIL]" in redacted
    assert counts["emails"] >= 1


def test_detect_language_english():
    lang = detect_language("The report and the analysis for the project are ready.")
    assert lang["language"] in {"en", "unknown"}


def test_extractive_summary_and_clean():
    text = "First sentence about revenue growth in markets. " * 3 + "Second topic sentence about costs. " * 3
    summary = extractive_summary(text, max_sentences=2)
    assert summary
    cleaned = clean_document_text("A\n\n\nB   C\n1\n1\n1\n")
    assert "A" in cleaned and "B C" in cleaned.replace("  ", " ")
