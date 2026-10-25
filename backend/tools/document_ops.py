"""Deterministic document text helpers (no LLM).

Used by DocumentProcessor for entity extraction, key-value parsing,
PII redaction, language heuristics, and extractive summary.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}\b"
)
_URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.I)
_AMOUNT_RE = re.compile(
    r"(?:(?:USD|INR|EUR|GBP|Rs\.?|₹|\$|€|£)\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b"
    r"|\b\d+(?:\.\d{2})?\s*(?:USD|INR|EUR|GBP)\b",
    re.I,
)
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4})\b",
    re.I,
)
_KV_RE = re.compile(
    r"^[\s>*\-]*([A-Za-z][A-Za-z0-9 /_\-]{1,40})\s*[:=\-]\s*(.+?)\s*$",
    re.M,
)

_EN_STOP = {
    "the", "and", "for", "that", "with", "this", "from", "have", "are", "was",
    "were", "been", "will", "would", "could", "should", "about", "into", "your",
}
_ES_STOP = {"que", "los", "las", "del", "una", "por", "para", "con", "como", "más"}
_FR_STOP = {"les", "des", "une", "pour", "dans", "avec", "que", "est", "pas", "sur"}
_DE_STOP = {"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "mit", "auf"}


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract emails, phones, URLs, dates, and money-like amounts."""
    def _uniq(values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for v in values:
            key = v.strip()
            if not key or key.lower() in seen:
                continue
            seen.add(key.lower())
            out.append(key)
        return out

    phones = []
    for m in _PHONE_RE.findall(text or ""):
        digits = re.sub(r"\D", "", m)
        if 7 <= len(digits) <= 15:
            phones.append(m.strip())

    return {
        "emails": _uniq(_EMAIL_RE.findall(text or "")),
        "phones": _uniq(phones),
        "urls": _uniq(_URL_RE.findall(text or "")),
        "dates": _uniq(_DATE_RE.findall(text or "")),
        "amounts": _uniq(_AMOUNT_RE.findall(text or "")),
    }


def extract_key_values(text: str) -> dict[str, str]:
    """Parse simple Label: value / Label = value lines from document text."""
    found: dict[str, str] = {}
    for m in _KV_RE.finditer(text or ""):
        key = re.sub(r"\s+", " ", m.group(1)).strip(" .-_")
        val = m.group(2).strip()
        if len(key) < 2 or len(val) < 1:
            continue
        # Skip markdown headings mistaken as KV
        if key.startswith("#"):
            continue
        found[key] = val
    return found


def find_mentions(text: str, keyword: str, window: int = 120) -> list[dict[str, Any]]:
    """Find keyword occurrences with surrounding context snippets."""
    if not text or not keyword or not keyword.strip():
        return []
    pattern = re.compile(re.escape(keyword.strip()), re.I)
    hits: list[dict[str, Any]] = []
    for i, m in enumerate(pattern.finditer(text), start=1):
        start = max(0, m.start() - window)
        end = min(len(text), m.end() + window)
        snippet = text[start:end].replace("\n", " ").strip()
        hits.append({
            "index": i,
            "match": m.group(0),
            "start": m.start(),
            "end": m.end(),
            "snippet": snippet,
        })
    return hits


def extract_links(text: str) -> dict[str, list[str]]:
    """Extract URLs and email addresses (references)."""
    ents = extract_entities(text)
    return {"urls": ents["urls"], "emails": ents["emails"]}


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    """Mask emails and phone numbers in text."""
    counts = {"emails": 0, "phones": 0}
    out = text or ""

    def _mask_email(m: re.Match[str]) -> str:
        counts["emails"] += 1
        return "[REDACTED_EMAIL]"

    def _mask_phone(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 7 <= len(digits) <= 15:
            counts["phones"] += 1
            return "[REDACTED_PHONE]"
        return m.group(0)

    out = _EMAIL_RE.sub(_mask_email, out)
    out = _PHONE_RE.sub(_mask_phone, out)
    return out, counts


def detect_language(text: str) -> dict[str, Any]:
    """Very lightweight language guess from common function words."""
    tokens = re.findall(r"[A-Za-zÀ-ÿ]{2,}", (text or "").lower())
    if not tokens:
        return {"language": "unknown", "confidence": 0.0, "token_count": 0}

    scores = {
        "en": sum(1 for t in tokens if t in _EN_STOP),
        "es": sum(1 for t in tokens if t in _ES_STOP),
        "fr": sum(1 for t in tokens if t in _FR_STOP),
        "de": sum(1 for t in tokens if t in _DE_STOP),
    }
    lang, score = max(scores.items(), key=lambda kv: kv[1])
    conf = score / max(len(tokens), 1)
    if score == 0:
        return {"language": "unknown", "confidence": 0.0, "token_count": len(tokens)}
    return {"language": lang, "confidence": round(conf, 4), "token_count": len(tokens), "scores": scores}


def extractive_summary(text: str, max_sentences: int = 5) -> str:
    """Simple extractive summary: top sentences by word frequency (no LLM)."""
    raw = (text or "").strip()
    if not raw:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if not sentences:
        return raw[:500]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    words = re.findall(r"[a-zA-Z]{3,}", raw.lower())
    freq = Counter(w for w in words if w not in _EN_STOP)
    ranked: list[tuple[float, int, str]] = []
    for i, sent in enumerate(sentences):
        sw = re.findall(r"[a-zA-Z]{3,}", sent.lower())
        score = sum(freq.get(w, 0) for w in sw) / max(len(sw), 1)
        ranked.append((score, i, sent))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    chosen = sorted(ranked[:max_sentences], key=lambda x: x[1])
    return " ".join(s for _, _, s in chosen)


def clean_document_text(text: str) -> str:
    """Normalize whitespace and drop obvious repeated header/footer noise lines."""
    if not text:
        return ""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    # Drop very short repeated lines that look like running headers/page numbers
    counts = Counter(ln for ln in lines if ln)
    cleaned: list[str] = []
    for ln in lines:
        if not ln:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if len(ln) <= 40 and counts[ln] >= 3 and re.fullmatch(r"[\w\s\.\-/]+", ln):
            continue
        if re.fullmatch(r"\d{1,4}", ln):  # lone page numbers
            continue
        cleaned.append(ln)
    out = "\n".join(cleaned)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
