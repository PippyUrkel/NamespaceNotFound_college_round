from __future__ import annotations

import json
import re
from typing import Protocol

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings

from .models import AuditContext, Evidence, Finding

_PROMPT = (
    "You are auditing an AI/ML research paper for reproducibility risk. Read the paper text and "
    "identify up to 5 issues of these kinds only: an ambiguous metric definition, a claim made "
    "without a baseline comparison, or a hint of test-set leakage. "
    "Respond as a JSON object: {\"issues\": [{\"quote\": str, \"section\": str|null, "
    "\"issue_type\": \"ambiguous_metric\"|\"missing_baseline\"|\"leakage_hint\", "
    "\"confidence\": float between 0 and 1, \"explanation\": str}]}. "
    "The quote MUST be copied verbatim from the paper text below, not paraphrased or invented. "
    "If you find nothing, return {\"issues\": []}.\n\nPaper text:\n"
)

_ISSUE_TITLES = {
    "ambiguous_metric": "Ambiguous metric definition",
    "missing_baseline": "Claim made without a baseline comparison",
    "leakage_hint": "Possible hint of data/test-set leakage",
}


class GroqLike(Protocol):
    def chat_completion(self, prompt: str) -> str: ...


class _GroqClient:
    def __init__(self, api_key: str, model: str) -> None:
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model

    def chat_completion(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return response.choices[0].message.content


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _quote_verified(quote: str, paper_text: str) -> bool:
    if not quote or not paper_text:
        return False
    return _normalize(quote) in _normalize(paper_text)


def check_ambiguous_claims(context: AuditContext, *, client: GroqLike | None = None) -> list[Finding]:
    if not context.paper_text.strip():
        return []

    if client is None:
        if not settings.groq_api_key:
            return []
        try:
            client = _GroqClient(settings.groq_api_key, settings.groq_model)
        except Exception:
            return []

    try:
        raw = client.chat_completion(_PROMPT + context.paper_text[:8000])
        parsed = json.loads(raw)
        issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
    except Exception:
        return []

    findings: list[Finding] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        quote = str(issue.get("quote") or "")
        issue_type = str(issue.get("issue_type") or "")
        if issue_type not in _ISSUE_TITLES:
            continue
        if not _quote_verified(quote, context.paper_text):
            continue
        try:
            confidence = float(issue.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.3:
            continue

        explanation = str(issue.get("explanation") or _ISSUE_TITLES[issue_type])
        findings.append(
            Finding(
                rule_id=f"llm:{issue_type}",
                phase="static",
                severity="medium",
                status="possible",
                title=_ISSUE_TITLES[issue_type],
                message=f"{explanation} (model confidence: {confidence:.2f})",
                evidence=[
                    Evidence(
                        source="paper",
                        section=issue.get("section"),
                        exact_text=quote,
                    )
                ],
                remediation=None,
            )
        )
    return findings


__all__ = ["check_ambiguous_claims", "GroqLike"]
