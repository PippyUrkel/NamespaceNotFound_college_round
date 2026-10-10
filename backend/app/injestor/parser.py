from __future__ import annotations

import hashlib
import io
import re
from typing import Any

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=DeprecationWarning)
    try:
        from PyPDF2 import PdfReader
    except ImportError:  # pragma: no cover
        try:
            from pypdf import PdfReader
        except ImportError:  # pragma: no cover
            PdfReader = None

try:
    from backend.app.injestor.repo_inspector import RepositoryInspector
except ModuleNotFoundError:  # pragma: no cover
    from app.injestor.repo_inspector import RepositoryInspector


class PDFParser:
    @staticmethod
    def parse_upload(file_bytes: bytes, filename: str) -> dict[str, Any]:
        pdf_sha256 = hashlib.sha256(file_bytes).hexdigest()
        full_text = ""

        if PdfReader is not None:
            try:
                reader = PdfReader(io.BytesIO(file_bytes))
                page_texts = []
                for page in reader.pages:
                    txt = page.extract_text() or ""
                    if txt.strip():
                        page_texts.append(txt.strip())
                full_text = "\n\n".join(page_texts).strip()
            except Exception:
                pass

        if not full_text:
            full_text = file_bytes.decode("utf-8", errors="ignore") or f"Uploaded file: {filename}"

        title = PDFParser._extract_title(full_text) or filename
        abstract = PDFParser._extract_abstract(full_text)
        sections = PDFParser._extract_sections(full_text)
        repo_url = PDFParser._extract_repo_url(full_text)

        if repo_url:
            print(f"[PDFParser] Parsed GitHub repository URL from {filename}: {repo_url}", flush=True)
        else:
            print(f"[PDFParser] No GitHub repository URL found in {filename}", flush=True)

        evidence = [{
            "source": "paper",
            "section": "document",
            "file_path": filename,
            "exact_text": (abstract or title or full_text[:200]),
        }]
        if repo_url:
            evidence.append({
                "source": "paper",
                "section": "code_availability",
                "file_path": filename,
                "exact_text": f"Found repository URL: {repo_url}",
            })

        return {
            "title": title,
            "abstract": abstract,
            "sections": sections,
            "full_text": full_text,
            "hash_sha256": pdf_sha256,
            "evidence": evidence,
            "filename": filename,
            "repo_url": repo_url,
        }

    @staticmethod
    def _extract_repo_url(text: str) -> str | None:
        if not text:
            return None
        # Unfold lines wrapped across newlines (e.g., in two-column formatting)
        unfolded = re.sub(
            r"((?:https?://)?(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|huggingface\.co|codeberg\.org|[A-Za-z0-9_.-]+\.github\.io)(?:/[A-Za-z0-9_.-]+)*/?)\s*\n\s*",
            r"\1",
            text,
            flags=re.IGNORECASE,
        )
        pattern = r"(?:https?://)?(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|huggingface\.co|codeberg\.org|[A-Za-z0-9_.-]+\.github\.io)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
        for match in re.finditer(pattern, unfolded, flags=re.IGNORECASE):
            candidate = match.group(0)
            try:
                return RepositoryInspector.validate_url(candidate)
            except ValueError:
                continue
        return None

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
