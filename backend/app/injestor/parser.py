from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

from docling.document_converter import DocumentConverter


class PDFParser:
    @staticmethod
    def parse_upload(file_bytes: bytes, filename: str) -> dict:
        pdf_sha256 = hashlib.sha256(file_bytes).hexdigest()
        temp_file = Path(tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name)
        temp_file.write_bytes(file_bytes)
        full_text = ""
        try:
            try:
                converter = DocumentConverter()
                result = converter.convert(str(temp_file))
                document = getattr(result, "document", None)
                if document is not None:
                    export_fn = getattr(document, "export_to_markdown", None)
                    if callable(export_fn):
                        full_text = str(export_fn()) or ""
                    if not full_text:
                        full_text = str(getattr(document, "text", "") or "")
            except Exception:
                pass
        finally:
            temp_file.unlink(missing_ok=True)

        if not full_text:
            full_text = file_bytes.decode("utf-8", errors="ignore") or f"Uploaded file: {filename}"

        title = PDFParser._extract_title(full_text) or filename
        abstract = PDFParser._extract_abstract(full_text)
        sections = PDFParser._extract_sections(full_text)
        evidence = [{
            "source": "paper",
            "section": "document",
            "file_path": filename,
            "exact_text": (abstract or title or full_text[:200]),
        }]
        return {
            "title": title,
            "abstract": abstract,
            "sections": sections,
            "full_text": full_text,
            "hash_sha256": pdf_sha256,
            "evidence": evidence,
            "filename": filename,
        }

    @staticmethod
    def _extract_title(text: str) -> str | None:
        line = next((ln.strip() for ln in text.splitlines() if ln.strip()), None)
        if line and len(line) < 200:
            return line
        match = re.search(r"(?im)^\s*(?:#\s*)?(?:title\s*[:\-]\s*)?(.{1,200})$", text[:500])
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_abstract(text: str) -> str | None:
        match = re.search(r"(?is)abstract\s*[:\-]?\s*(.*?)(?=\n\s*(?:introduction|method|background|experiment|results|conclusion)\b|\Z)", text)
        if not match:
            return None
        return re.sub(r"\s+", " ", match.group(1)).strip()

    @staticmethod
    def _extract_sections(text: str) -> list[str]:
        titles = []
        for line in text.splitlines():
            cleaned = line.strip()
            if re.match(r"^(#{1,6}\s+|\d+\.?\s+)?[A-Z][A-Za-z0-9 ,()\-/]{2,}$", cleaned):
                titles.append(cleaned.lstrip('#').strip())
        return titles
