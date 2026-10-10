from __future__ import annotations

import hashlib
import io
import re
import tempfile
import warnings
from pathlib import Path
from typing import Any

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
    from docling.document_converter import DocumentConverter
except ImportError:  # pragma: no cover
    DocumentConverter = None

try:
    from backend.app.injestor.repo_inspector import RepositoryInspector
except ModuleNotFoundError:  # pragma: no cover
    from app.injestor.repo_inspector import RepositoryInspector


class PDFParser:
    @staticmethod
    def _is_desirable_text(text: str) -> bool:
        """
        Determines whether directly retrieved text from a document is sufficient
        and of desirable quality, or if standby OCR should be triggered.
        """
        if not text or not text.strip():
            return False

        stripped = text.strip()
        # In research papers, a valid extracted text layer should contain substantial text.
        # Scanned documents typically yield 0 or only a few stray characters/numbers.
        if len(stripped) < 100:
            return False

        # Check for presence of actual words (not just garbage glyphs or corrupt font mappings)
        words = re.findall(r"\b[A-Za-z]{2,}\b", stripped)
        if len(words) < 15:
            return False

        # Check printable character ratio to guard against binary noise/corrupt fonts
        printable_count = sum(1 for c in stripped if c.isprintable() or c in "\n\r\t")
        if (printable_count / len(stripped)) < 0.7:
            return False

        return True

    @staticmethod
    def _extract_text_direct(file_bytes: bytes) -> str:
        """
        Fast direct document text retrieval without OCR.
        Reads native PDF text streams and fonts directly from memory.
        """
        if PdfReader is None:
            return ""

        reader = PdfReader(io.BytesIO(file_bytes))
        page_texts: list[str] = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            if txt.strip():
                page_texts.append(txt.strip())
        return "\n\n".join(page_texts).strip()

    @staticmethod
    def _extract_text_ocr(file_bytes: bytes) -> str:
        """
        Standby OCR fallback for scanned, image-only, or non-extractable PDFs.
        """
        if DocumentConverter is None:
            return ""

        temp_file = Path(tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name)
        try:
            temp_file.write_bytes(file_bytes)
            converter = DocumentConverter()
            result = converter.convert(str(temp_file))
            document = getattr(result, "document", None)
            if document is not None:
                export_fn = getattr(document, "export_to_markdown", None)
                if callable(export_fn):
                    ocr_text = str(export_fn()) or ""
                else:
                    ocr_text = ""
                if not ocr_text:
                    ocr_text = str(getattr(document, "text", "") or "")
                return ocr_text.strip()
        except Exception as exc:
            print(f"[PDFParser] Standby OCR encountered an issue: {exc}", flush=True)
            return ""
        finally:
            temp_file.unlink(missing_ok=True)
        return ""

    @staticmethod
    def parse_upload(file_bytes: bytes, filename: str) -> dict[str, Any]:
        pdf_sha256 = hashlib.sha256(file_bytes).hexdigest()
        full_text = ""
        method = "text_retrieval"

        # Step 1: Normal document text retrieval (primary engine)
        try:
            full_text = PDFParser._extract_text_direct(file_bytes)
        except Exception as exc:
            print(f"[PDFParser] Normal text retrieval failed on {filename}: {exc}", flush=True)
            full_text = ""

        # Step 2: Quality verification
        if PDFParser._is_desirable_text(full_text):
            print(f"[PDFParser] Normal document text retrieval succeeded for {filename} ({len(full_text)} characters). Standby OCR not needed.", flush=True)
        else:
            reason = "empty text layer" if not full_text else f"insufficient/low-quality text ({len(full_text)} chars)"
            print(f"[PDFParser] Normal text retrieval yielded {reason}. Triggering standby OCR for {filename}...", flush=True)

            ocr_text = ""
            try:
                ocr_text = PDFParser._extract_text_ocr(file_bytes)
            except Exception as exc:
                print(f"[PDFParser] Standby OCR execution failed: {exc}", flush=True)

            if PDFParser._is_desirable_text(ocr_text):
                full_text = ocr_text
                method = "ocr_standby"
                print(f"[PDFParser] Standby OCR succeeded for {filename} ({len(full_text)} characters).", flush=True)
            elif ocr_text.strip():
                full_text = ocr_text
                method = "ocr_standby"
                print(f"[PDFParser] Using standby OCR output for {filename} ({len(full_text)} characters).", flush=True)
            elif not full_text:
                full_text = file_bytes.decode("utf-8", errors="ignore").strip() or f"Uploaded file: {filename}"
                method = "fallback"
                print(f"[PDFParser] Standby OCR did not yield text. Using fallback text decode for {filename}.", flush=True)

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
            "method": method,
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
            "extraction_method": method,
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
