from __future__ import annotations

import json
import re

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings


class GroqExtractor:
    @staticmethod
    def extract(paper_analysis: dict, repo_analysis: dict | None = None) -> dict:
        if settings.groq_api_key:
            try:
                from groq import Groq

                client = Groq(api_key=settings.groq_api_key)
                prompt = (
                    "Extract experiment metadata as JSON. Include title, dataset, optimizer, learning_rate, batch_size, epochs, seed, metrics, architecture. "
                    "Use null if missing. Do not invent values.\n"
                    f"Paper text: {paper_analysis.get('full_text','')[:6000]}\n\n"
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
                    return parsed
            except Exception:
                pass

        text = paper_analysis.get("full_text", "")
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
        }
