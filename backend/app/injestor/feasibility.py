from __future__ import annotations


class FeasibilityService:
    @staticmethod
    def assess(extracted: dict, *, repo_analysis: dict | None = None) -> dict:
        required = ["dataset", "optimizer", "learning_rate", "epochs", "metrics"]
        missing = [key for key in required if not extracted.get(key)]

        if repo_analysis is None and not extracted.get("dataset"):
            return {
                "feasibility": "blocked",
                "reproducibility": "blocked",
                "missing_fields": missing or ["dataset"],
                "warnings": ["No repository was provided and the experiment metadata is incomplete."],
            }

        if missing:
            return {
                "feasibility": "audit_only",
                "reproducibility": "audit_only",
                "missing_fields": missing,
                "warnings": [f"Missing required fields: {', '.join(missing)}"],
            }

        return {
            "feasibility": "ready_with_limitations",
            "reproducibility": "ready_with_limitations",
            "missing_fields": [],
            "warnings": ["Execution readiness is estimated without actually running the repository."],
        }
