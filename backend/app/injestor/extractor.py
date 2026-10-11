from __future__ import annotations

import json
import re

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings


_METRIC_WORDS = r"top-1 accuracy|top-5 accuracy|accuracy|f1[- ]score|f1|precision|recall|auc|mAP|bleu"
_CLAIM_AFTER_METRIC = re.compile(
    rf"\b(?P<metric>{_METRIC_WORDS})\b(?:\s+(?:of|is|was|=|:|reaches|reached|achieves|achieved|score))*\s*[:=]?\s*"
    r"(?<![\w.-])(?P<value>\d+(?:\.\d+)?)\s*(?P<pct>%)?",
    re.IGNORECASE,
)
_CLAIM_BEFORE_METRIC = re.compile(
    rf"(?<![\w.-])(?P<value>\d+(?:\.\d+)?)\s*(?P<pct>%)?\s+(?:test\s+)?(?P<metric>{_METRIC_WORDS})\b",
    re.IGNORECASE,
)


# Joins a hyperparameter name to its value: "batch size: 64", "batch size is 120", "learning rate starts at 0.001"
_VALUE_CONNECTOR = r"(?:\s*[:=]\s*|\s+(?:is|was|of|=|set to|starts at|starting at|initialized to)\s+|\s+)"

_DATASET_ASSIGNMENT = re.compile(r"\bdatasets?\s*[:=]\s*[\"']?([A-Za-z][A-Za-z0-9_\-]*)", re.IGNORECASE)
_DATASET_BEFORE_WORD = re.compile(r"\b([A-Za-z][A-Za-z0-9_\-]*)\s+datasets?\b", re.IGNORECASE)
_DATASET_AFTER_WORD = re.compile(r"\bdatasets?\s+([A-Za-z][A-Za-z0-9_\-]*)", re.IGNORECASE)
_NON_DATASET_WORDS = frozenset(
    "a an the this that these those our their its we it is are was were be of in on at to for from by with "
    "and or as along across into over under each every all any both same new own real synthetic custom "
    "training train test testing validation used using which where consists contains includes".split()
)


def _looks_like_dataset_name(token: str) -> bool:
    # Dataset names are proper nouns/acronyms (CIFAR-10, ImageNet, SST-2), not plain lowercase words
    if token.lower() in _NON_DATASET_WORDS:
        return False
    return any(ch.isdigit() for ch in token) or any(ch.isupper() for ch in token[1:])


def find_dataset_name(text: str) -> tuple[str, str] | None:
    """Return (dataset name, matched excerpt), or None when no plausible name is present.

    Prose such as "the dataset along the transition" must not yield "along", so a word
    adjacent to "dataset" only counts when it looks like a proper dataset name. Explicit
    assignments ("dataset: mnist", "dataset = cifar10") are trusted unless they hit a stopword.
    """
    for match in _DATASET_ASSIGNMENT.finditer(text):
        if match.group(1).lower() not in _NON_DATASET_WORDS:
            return match.group(1), match.group(0)
    for pattern in (_DATASET_BEFORE_WORD, _DATASET_AFTER_WORD):
        for match in pattern.finditer(text):
            if _looks_like_dataset_name(match.group(1)):
                return match.group(1), match.group(0)
    return None


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    right_candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return " ".join(text[left:right].split())[:300]


def _plausible(metric: str, value: float) -> bool:
    if metric.lower() == "bleu":
        return 0 <= value <= 100
    return 0 < value <= 100


def _number_in_text(value: float, text: str) -> bool:
    candidates = {f"{value:g}"}
    if value <= 1:
        candidates.add(f"{value * 100:g}")
    else:
        candidates.add(f"{value / 100:g}")
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", text) for c in candidates)


def extract_claimed_results(text: str) -> list[dict]:
    """Regex-extract headline metric values the paper reports, with the sentence as evidence."""
    claims: dict[str, dict] = {}
    matches = list(_CLAIM_AFTER_METRIC.finditer(text or "")) + list(_CLAIM_BEFORE_METRIC.finditer(text or ""))
    for match in sorted(matches, key=lambda m: m.start()):
        metric = match.group("metric").lower().replace(" ", "-")
        value = float(match.group("value"))
        if metric in claims or not _plausible(metric, value):
            continue
        claims[metric] = {
            "metric": metric,
            "value": value,
            "unit": "%" if match.group("pct") else None,
            "source": "paper",
            "exact_text": _sentence_around(text, match.start(), match.end()),
            "confidence": 0.6,
        }
    return list(claims.values())


def _normalize_llm_claims(raw: object, text: str) -> list[dict]:
    """Keep only LLM-reported claims whose number actually appears in the paper text."""
    if isinstance(raw, dict):
        raw = [{"metric": k, "value": v} for k, v in raw.items()]
    if not isinstance(raw, list):
        return []
    claims: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "").strip().lower()
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        if not metric or metric in claims or not _number_in_text(value, text):
            continue
        quote = str(item.get("quote") or "").strip() or None
        claims[metric] = {
            "metric": metric,
            "value": value,
            "unit": item.get("unit"),
            "source": "paper",
            "exact_text": quote,
            "confidence": 0.8,
        }
    return list(claims.values())


class GroqExtractor:
    @staticmethod
    def extract(paper_analysis: dict, repo_analysis: dict | None = None) -> dict:
        text = paper_analysis.get("full_text", "")
        if settings.groq_api_key:
            try:
                from groq import Groq

                client = Groq(api_key=settings.groq_api_key)
                prompt = (
                    "Extract experiment metadata as JSON. Include title, dataset, optimizer, learning_rate, batch_size, epochs, seed, metrics, architecture. "
                    "Also include reported_results: a list of {\"metric\": str, \"value\": number, \"unit\": \"%\"|null, \"quote\": str} giving the headline "
                    "numeric result the paper claims for its proposed method on each evaluation metric, with quote copied verbatim from the paper. "
                    "Use null if missing (or [] for reported_results). Do not invent values.\n"
                    f"Paper text: {text[:6000]}\n\n"
                    f"Repository readme: {(repo_analysis or {}).get('readme','')[:1000]}"
                )
                response = client.chat.completions.create(
                    model=settings.groq_model,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                )
                parsed = json.loads(response.choices[0].message.content)
                if isinstance(parsed, dict):
                    claimed = _normalize_llm_claims(parsed.pop("reported_results", None), text)
                    parsed["claimed_results"] = claimed or extract_claimed_results(text)
                    # The LLM only sees the first 6000 chars; hyperparameters often sit later in the
                    # methods section, so backfill anything it left empty from the full-text rules
                    rule_based = GroqExtractor._extract_with_rules(paper_analysis, text)
                    for key in ("dataset", "optimizer", "learning_rate", "batch_size", "epochs", "seed", "metrics"):
                        if parsed.get(key) in (None, "", []) and rule_based.get(key) not in (None, "", []):
                            parsed[key] = rule_based[key]
                    return parsed
            except Exception:
                pass

        return GroqExtractor._extract_with_rules(paper_analysis, text)

    @staticmethod
    def _extract_with_rules(paper_analysis: dict, text: str) -> dict:
        title = paper_analysis.get("title") or "Untitled paper"
        dataset = find_dataset_name(text)
        optimizer = re.search(r"optimizer\s*[:=]?\s*([A-Za-z0-9_\-]+)", text, re.I)
        lr = re.search(
            rf"learning rate{_VALUE_CONNECTOR}([0-9]*\.?[0-9]+(?:e-?[0-9]+)?)", text, re.I
        )
        batch = re.search(rf"batch size{_VALUE_CONNECTOR}(\d+)", text, re.I)
        # "trained for 150 epochs" is the common phrasing; "epochs: 150" mostly appears in configs
        epochs = re.search(r"(\d+)\s+(?:training\s+)?epochs\b", text, re.I) or re.search(
            r"epochs?\s*[:=]?\s*(\d+)", text, re.I
        )
        seed = re.search(r"seed\s*[:=]?\s*(\d+)", text, re.I)
        metrics = []
        for metric in ["accuracy", "f1", "precision", "recall", "mAP", "auc"]:
            if re.search(rf"\b{metric}\b", text, 0 if metric == "mAP" else re.I):
                metrics.append(metric)
        return {
            "title": title,
            "dataset": dataset[0] if dataset else None,
            "optimizer": optimizer.group(1).strip() if optimizer else None,
            "learning_rate": float(lr.group(1)) if lr else None,
            "batch_size": int(batch.group(1)) if batch else None,
            "epochs": int(epochs.group(1)) if epochs else None,
            "seed": int(seed.group(1)) if seed else None,
            "metrics": metrics,
            "architecture": "inferred from paper",
            "claimed_results": extract_claimed_results(text),
        }
