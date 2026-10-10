from __future__ import annotations


class ComparisonService:
    @staticmethod
    def compare(paper_values: dict, repo_values: dict) -> list[dict]:
        fields = sorted(set(paper_values) | set(repo_values))
        discrepancies = []
        for field in fields:
            paper_value = paper_values.get(field)
            repo_value = repo_values.get(field)
            if paper_value is None and repo_value is None:
                status = "missing_both"
            elif paper_value is None:
                status = "repository_only"
            elif repo_value is None:
                status = "paper_only"
            elif paper_value == repo_value:
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
