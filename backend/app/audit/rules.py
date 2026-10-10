from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .models import AuditContext, Evidence, Finding, Phase

RuleFunc = Callable[..., list[Finding]]


@dataclass
class RuleSpec:
    rule_id: str
    phase: Phase
    func: RuleFunc


REGISTRY: list[RuleSpec] = []


def rule(rule_id: str, phase: Phase) -> Callable[[RuleFunc], RuleFunc]:
    def decorator(func: RuleFunc) -> RuleFunc:
        REGISTRY.append(RuleSpec(rule_id=rule_id, phase=phase, func=func))
        return func

    return decorator


CRITICAL_FIELDS = {
    "dataset": "dataset",
    "architecture": "model architecture",
    "learning_rate": "learning rate",
    "epochs": "epochs",
    "metrics": "evaluation metric",
}


@rule("critical_field_missing", "static")
def critical_field_missing(context: AuditContext) -> list[Finding]:
    findings = []
    for name, label in CRITICAL_FIELDS.items():
        if context.field(name).is_missing:
            findings.append(
                Finding(
                    rule_id=f"critical_field_missing:{name}",
                    phase="static",
                    severity="critical" if name in {"dataset", "metrics"} else "high",
                    status="confirmed",
                    title=f"Missing critical field: {label}",
                    message=f"The paper and repository do not state the {label}, so the experiment cannot be reproduced as described.",
                    evidence=[Evidence(source="paper", exact_text="(field not found)")],
                    remediation=f"Locate the {label} in the paper's methodology/appendix or in the repo's config/training script.",
                )
            )
    return findings


_SEED_PATTERN = re.compile(r"(manual_seed|set_seed|random\.seed|np\.random\.seed|seed\s*=)", re.IGNORECASE)


@rule("missing_seed", "static")
def missing_seed(context: AuditContext) -> list[Finding]:
    if not context.field("seed").is_missing or not context.has_repo:
        return []
    for path, text in context.repo_files.items():
        if _SEED_PATTERN.search(text or ""):
            return []
    return [
        Finding(
            rule_id="missing_seed",
            phase="static",
            severity="medium",
            status="confirmed",
            title="Random seed not reported and not set in code",
            message="The paper does not report a random seed, and no seeding call was found in the inspected repository files.",
            evidence=[Evidence(source="repository", exact_text="No seed/manual_seed/set_seed call found in inspected files.")],
            remediation="Report the seed(s) used in the paper, and call a seeding function (e.g. torch.manual_seed) before training.",
        )
    ]


_VARIANCE_PATTERN = re.compile(
    r"(±|\+/-|\bstd\b|standard deviation|confidence interval|\bC\.?I\.?\b|n\s*=\s*\d+\s*(runs|seeds|trials))",
    re.IGNORECASE,
)


@rule("no_variance_reported", "static")
def no_variance_reported(context: AuditContext) -> list[Finding]:
    if not context.paper_text.strip() or context.field("metrics").is_missing:
        return []
    if _VARIANCE_PATTERN.search(context.paper_text):
        return []
    return [
        Finding(
            rule_id="no_variance_reported",
            phase="static",
            severity="low",
            status="confirmed",
            title="No variance reported for the claimed metric",
            message="No standard deviation, confidence interval, or multiple-run statement was found for the reported results.",
            evidence=[Evidence(source="paper", exact_text="No variance indicator (±, std, CI, multiple runs) found in paper text.")],
            remediation="Report results across multiple seeds with a standard deviation or confidence interval.",
        )
    ]


_DEPENDENCY_FILES = ("requirements.txt", "pyproject.toml", "environment.yml", "Dockerfile")
_PIN_PATTERN = re.compile(r"(==|>=|<=|~=|!=|>|<)")


@rule("unpinned_dependencies", "static")
def unpinned_dependencies(context: AuditContext) -> list[Finding]:
    if not context.has_repo:
        return []
    present = [name for name in _DEPENDENCY_FILES if name in context.repo_files]
    if not present:
        return [
            Finding(
                rule_id="missing_requirements_file",
                phase="static",
                severity="medium",
                status="confirmed",
                title="No dependency manifest found",
                message="None of requirements.txt, pyproject.toml, environment.yml, or Dockerfile were found in the repository.",
                evidence=[Evidence(source="repository", exact_text="No dependency manifest file present among inspected files.")],
                remediation="Add a requirements.txt or pyproject.toml pinning exact dependency versions.",
            )
        ]

    findings: list[Finding] = []
    for name in present:
        if name in ("Dockerfile",):
            continue
        unpinned = []
        for line in (context.repo_files.get(name) or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("["):
                continue
            if not _PIN_PATTERN.search(stripped):
                unpinned.append(stripped)
        if unpinned:
            findings.append(
                Finding(
                    rule_id=f"unpinned_dependencies:{name}",
                    phase="static",
                    severity="medium",
                    status="confirmed",
                    title=f"Unpinned dependencies in {name}",
                    message=f"{len(unpinned)} entr{'y' if len(unpinned) == 1 else 'ies'} in {name} have no version pin: {', '.join(unpinned[:10])}.",
                    evidence=[Evidence(source="repository", file_path=name, exact_text=", ".join(unpinned[:10]))],
                    remediation=f"Pin exact versions for each dependency in {name} (e.g. torch==2.1.0).",
                )
            )
    return findings


@rule("paper_vs_code_mismatch", "static")
def paper_vs_code_mismatch(context: AuditContext) -> list[Finding]:
    findings = []
    for item in context.discrepancies:
        if item.get("status") != "conflict":
            continue
        field_name = item.get("field", "field")
        findings.append(
            Finding(
                rule_id=f"paper_vs_code_mismatch:{field_name}",
                phase="static",
                severity="high",
                status="confirmed",
                title=f"Paper and code disagree on {field_name}",
                message=f"Paper states {field_name}={item.get('paper_value')!r}, but the repository indicates {field_name}={item.get('repository_value')!r}.",
                evidence=[
                    Evidence(source="paper", exact_text=str(item.get("paper_value"))),
                    Evidence(source="repository", exact_text=str(item.get("repository_value"))),
                ],
                remediation="Reconcile the paper and the repository so the reported configuration matches what was actually run.",
            )
        )
    return findings


_URL_PATTERN = re.compile(r"https?://[^\s)\]\"'<>]+", re.IGNORECASE)


def _default_http_get(url: str) -> int:
    import httpx

    response = httpx.head(url, timeout=5.0, follow_redirects=True)
    return response.status_code


@rule("dataset_unavailable", "static")
def dataset_unavailable(context: AuditContext, *, http_get: Callable[[str], int] | None = None) -> list[Finding]:
    http_get = http_get or _default_http_get
    sources = [context.paper_text] + list(context.repo_files.values())
    candidate_urls: set[str] = set()
    for text in sources:
        if not text:
            continue
        for match in re.finditer(r".{0,60}dataset.{0,120}", text, re.IGNORECASE):
            window = match.group(0)
            candidate_urls.update(_URL_PATTERN.findall(window))

    findings = []
    for url in sorted(candidate_urls):
        try:
            status_code = http_get(url)
            unreachable = status_code >= 400
            detail = f"HTTP {status_code}"
        except Exception as exc:  # noqa: BLE001
            unreachable = True
            detail = str(exc)
        if unreachable:
            findings.append(
                Finding(
                    rule_id="dataset_unavailable",
                    phase="static",
                    severity="high",
                    status="confirmed",
                    title="Dataset link unreachable",
                    message=f"A dataset link found near a 'dataset' mention could not be reached: {url} ({detail}).",
                    evidence=[Evidence(source="paper", url=url, exact_text=detail)],
                    remediation="Verify the dataset is still hosted at this URL, or provide a mirror/archive link.",
                )
            )
    return findings


_LEAKAGE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"tun(e|ed|ing)[^.]{0,40}on the test set",
        r"select(ed)?[^.]{0,40}(on|using)[^.]{0,20}the test set",
        r"test (set )?accuracy[^.]{0,30}to (tune|select)",
        r"best model[^.]{0,30}on the test set",
    ]
]


@rule("test_set_used_for_tuning", "static")
def test_set_used_for_tuning(context: AuditContext) -> list[Finding]:
    if not context.paper_text.strip():
        return []
    for pattern in _LEAKAGE_PATTERNS:
        match = pattern.search(context.paper_text)
        if match:
            return [
                Finding(
                    rule_id="test_set_used_for_tuning",
                    phase="static",
                    severity="medium",
                    status="possible",
                    title="Possible test-set leakage",
                    message="The paper's wording suggests the test set may have been used for model selection or tuning. This is a heuristic, not a proof.",
                    evidence=[Evidence(source="paper", exact_text=match.group(0).strip())],
                    remediation="Confirm whether hyperparameter/model selection used a held-out validation split, not the test set.",
                )
            ]
    return []


@rule("no_code_available", "static")
def no_code_available(context: AuditContext) -> list[Finding]:
    if context.has_repo:
        return []
    missing = sum(1 for f in context.fields.values() if f.is_missing)
    assumed = sum(1 for f in context.fields.values() if f.is_assumed)
    return [
        Finding(
            rule_id="no_code_available",
            phase="static",
            severity="high",
            status="confirmed",
            title="No code repository available",
            message=f"No repository was provided or found for this paper. {missing} spec field(s) are missing and {assumed} are assumed, so reproduction cannot be independently verified.",
            evidence=[Evidence(source="paper", exact_text="No repository_url resolved for this experiment.")],
            remediation="Request or locate the authors' code repository; until then, treat any reproduction as a reimplementation.",
        )
    ]


_GAP_THRESHOLD = 0.10
_CRITICAL_GAP_THRESHOLD = 0.30


@rule("reproduced_mean_far_from_claim", "run")
def reproduced_mean_far_from_claim(context: AuditContext) -> list[Finding]:
    findings = []
    for run in context.run_summaries:
        if run.claimed_value is None or run.reproduced_mean is None:
            continue
        denom = abs(run.claimed_value) if run.claimed_value else 1e-9
        gap = abs(run.reproduced_mean - run.claimed_value) / denom
        if gap <= _GAP_THRESHOLD:
            continue
        message = (
            f"Reproduced {run.metric} ({run.reproduced_mean}) differs from the claimed value "
            f"({run.claimed_value}) by {gap:.1%}, over {run.seeds_run} seed(s)."
        )
        if run.used_assumed_values:
            message += " This run used assumed configuration values, so the gap may reflect assumptions rather than the original setup."
        findings.append(
            Finding(
                rule_id=f"reproduced_mean_far_from_claim:{run.metric}",
                phase="run",
                severity="critical" if gap > _CRITICAL_GAP_THRESHOLD else "high",
                status="confirmed",
                title=f"Reproduced result diverges from claim for {run.metric}",
                message=message,
                evidence=[Evidence(source="run", exact_text=message)],
                remediation="Re-check the configuration used for reproduction against the paper, or mark the claim as not verified.",
            )
        )
    return findings


@rule("seed_variance_exceeds_claim", "run")
def seed_variance_exceeds_claim(context: AuditContext) -> list[Finding]:
    findings = []
    for run in context.run_summaries:
        if run.reproduced_std is None or run.claimed_improvement is None:
            continue
        if run.reproduced_std <= abs(run.claimed_improvement):
            continue
        message = (
            f"Seed variance for {run.metric} (std={run.reproduced_std}) exceeds the claimed improvement "
            f"({run.claimed_improvement}) over {run.seeds_run} seed(s)."
        )
        if run.used_assumed_values:
            message += " This run used assumed configuration values."
        findings.append(
            Finding(
                rule_id=f"seed_variance_exceeds_claim:{run.metric}",
                phase="run",
                severity="high",
                status="confirmed",
                title=f"Seed variance exceeds claimed improvement for {run.metric}",
                message=message,
                evidence=[Evidence(source="run", exact_text=message)],
                remediation="Run additional seeds and report variance; treat the claimed improvement as not verifiable until it exceeds noise.",
            )
        )
    return findings


__all__ = ["REGISTRY", "RuleSpec", "rule"]
