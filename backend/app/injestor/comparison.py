from __future__ import annotations

import re


def _normalize(value):
    """Reduce a value to a comparable form: numbers as floats, names lowercased without punctuation."""
    if isinstance(value, (list, tuple, set)):
        return sorted(str(_normalize(v)) for v in value)
    if isinstance(value, bool):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _values_match(field: str, paper_value, repo_value) -> bool:
    paper_norm, repo_norm = _normalize(paper_value), _normalize(repo_value)
    if paper_norm == repo_norm:
        return True
    # A repo implements the paper's architecture under a more specific class name (ResNet -> ResNet18)
    if field == "architecture" and isinstance(paper_norm, str) and isinstance(repo_norm, str):
        return bool(paper_norm and repo_norm) and (paper_norm in repo_norm or repo_norm in paper_norm)
    return False


class ComparisonService:
    @staticmethod
    def compare(paper_values: dict, repo_values: dict) -> list[dict]:
        fields = sorted(set(paper_values) | set(repo_values))
        discrepancies = []
        for field in fields:
            paper_value = paper_values.get(field)
            repo_value = repo_values.get(field)
            if paper_value in (None, "", []) and repo_value in (None, "", []):
                status = "missing_both"
            elif paper_value in (None, "", []):
                status = "repository_only"
            elif repo_value in (None, "", []):
                status = "paper_only"
            elif _values_match(field, paper_value, repo_value):
                status = "match"
            else:
                status = "conflict"
            discrepancies.append({
                "field": field,
                "status": status,
                "paper_value": paper_value,
                "repository_value": repo_value,
                "note": f"{field}: {status}",
            })
        return discrepancies
