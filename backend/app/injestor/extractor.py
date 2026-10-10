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
                    return parsed
            except Exception:
                pass

        title = paper_analysis.get("title") or "Untitled paper"
        dataset = re.search(r"dataset[s]?\s*[:=]?\s*([A-Za-z0-9_\-]+)", text, re.I)
        optimizer = re.search(r"optimizer\s*[:=]?\s*([A-Za-z0-9_\-]+)", text, re.I)
        lr = re.search(r"learning rate\s*[:=]?\s*([0-9]*\.?[0-9]+(?:e-?[0-9]+)?)", text, re.I)
        batch = re.search(r"batch size\s*[:=]?\s*(\d+)", text, re.I)
        epochs = re.search(r"epochs?\s*[:=]?\s*(\d+)", text, re.I)
        seed = re.search(r"seed\s*[:=]?\s*(\d+)", text, re.I)
        metrics = []
        for metric in ["accuracy", "f1", "precision", "recall", "mAP", "auc"]:
            if metric.lower() in text.lower():
                metrics.append(metric)
        return {
            "title": title,
            "dataset": dataset.group(1).strip() if dataset else None,
            "optimizer": optimizer.group(1).strip() if optimizer else None,
            "learning_rate": float(lr.group(1)) if lr else None,
            "batch_size": int(batch.group(1)) if batch else None,
            "epochs": int(epochs.group(1)) if epochs else None,
            "seed": int(seed.group(1)) if seed else None,
            "metrics": metrics,
            "architecture": "inferred from paper",
            "claimed_results": extract_claimed_results(text),
        }
