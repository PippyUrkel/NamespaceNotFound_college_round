from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field


class ParameterCondition(BaseModel):
    name: str
    value: Any
    source: str  # "paper", "repository", "reconciled", "assumed"
    evidence: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    confidence: float = 1.0
    is_assumed: bool = False
    discrepancy: str | None = None


class ExperimentConditionReport(BaseModel):
    seed: ParameterCondition
    dataset: ParameterCondition
    batch_size: ParameterCondition
    learning_rate: ParameterCondition
    epochs: ParameterCondition
    optimizer: ParameterCondition
    architecture: ParameterCondition
    metrics: ParameterCondition
    summary: dict[str, Any] = Field(default_factory=dict)


class ExperimentConditionResolver:
    """
    Extracts and reconciles exact experimental parameter conditions from
    research papers and accompanying repositories for reproducible DAG execution.
    """

    @classmethod
    def resolve_conditions(
        cls,
        spec: dict[str, Any],
        paper_analysis: dict[str, Any] | None = None,
        repo_analysis: dict[str, Any] | None = None,
    ) -> ExperimentConditionReport:
        paper_analysis = paper_analysis or spec.get("paper") or {}
        repo_analysis = repo_analysis or spec.get("repo") or {}

        paper_text = paper_analysis.get("full_text", "") or spec.get("paper_text", "") or ""
        repo_files = repo_analysis.get("files", {}) or {}
        repo_readme = repo_analysis.get("readme", "") or repo_files.get("README.md", "") or ""

        # 1. Random Seed
        seed_cond = cls._resolve_seed(spec, paper_text, repo_files, repo_readme)

        # 2. Dataset
        dataset_cond = cls._resolve_dataset(spec, paper_text, repo_files, repo_readme)

        # 3. Batch Size
        batch_cond = cls._resolve_batch_size(spec, paper_text, repo_files, repo_readme)

        # 4. Learning Rate
        lr_cond = cls._resolve_learning_rate(spec, paper_text, repo_files, repo_readme)

        # 5. Epochs
        epochs_cond = cls._resolve_epochs(spec, paper_text, repo_files, repo_readme)

        # 6. Optimizer
        opt_cond = cls._resolve_optimizer(spec, paper_text, repo_files, repo_readme)

        # 7. Architecture
        arch_cond = cls._resolve_architecture(spec, paper_text, repo_files, repo_readme)

        # 8. Metrics
        metrics_cond = cls._resolve_metrics(spec, paper_text, repo_files)

        summary = {
            "seed": seed_cond.value,
            "seed_source": seed_cond.source,
            "seed_is_assumed": seed_cond.is_assumed,
            "dataset": dataset_cond.value,
            "dataset_source": dataset_cond.source,
            "batch_size": batch_cond.value,
            "batch_size_source": batch_cond.source,
            "learning_rate": lr_cond.value,
            "learning_rate_source": lr_cond.source,
            "epochs": epochs_cond.value,
            "epochs_source": epochs_cond.source,
            "optimizer": opt_cond.value,
            "optimizer_source": opt_cond.source,
            "architecture": arch_cond.value,
            "architecture_source": arch_cond.source,
            "metrics": metrics_cond.value,
            "metrics_source": metrics_cond.source,
        }

        return ExperimentConditionReport(
            seed=seed_cond,
            dataset=dataset_cond,
            batch_size=batch_cond,
            learning_rate=lr_cond,
            epochs=epochs_cond,
            optimizer=opt_cond,
            architecture=arch_cond,
            metrics=metrics_cond,
            summary=summary,
        )

    @classmethod
    def _resolve_seed(
        cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str], repo_readme: str
    ) -> ParameterCondition:
        paper_seed: int | None = None
        paper_evidence: str | None = None
        repo_seed: int | None = None
        repo_evidence: str | None = None
        repo_file: str | None = None

        # Check spec first
        if spec.get("seed") is not None:
            try:
                paper_seed = int(spec["seed"])
                paper_evidence = f"Spec parameter seed: {paper_seed}"
            except (ValueError, TypeError):
                pass

        # Regex search paper text if needed
        if paper_seed is None and paper_text:
            p_patterns = [
                r"(?:random\s+)?seed\s*(?:is|was|of|to|set\s+to|=|\:)?\s*(\d+)",
                r"(?:manual_seed|random_state)\s*[:=\(]\s*(\d+)",
                r"(?:random\s+seed)\s*[:=]?\s*(\d+)",
            ]
            for pat in p_patterns:
                m = re.search(pat, paper_text, re.IGNORECASE)
                if m:
                    paper_seed = int(m.group(1))
                    paper_evidence = f"Paper text excerpt: '{m.group(0)}'"
                    break

        # Check repository files and readme
        all_repo_texts = [("README.md", repo_readme)] + list(repo_files.items())
        r_patterns = [
            r"(?:torch\.manual_seed|np\.random\.seed|random\.seed)\s*\(\s*(\d+)\s*\)",
            r"(?:--seed|-s)\s+(\d+)",
            r"default\s*=\s*(\d+).*?seed",
            r"seed.*?default\s*=\s*(\d+)",
            r"SEED\s*=\s*(\d+)",
        ]
        for fname, text in all_repo_texts:
            if not text:
                continue
            for pat in r_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    repo_seed = int(m.group(1))
                    repo_evidence = f"Repository {fname}: '{m.group(0)}'"
                    repo_file = fname
                    break
            if repo_seed is not None:
                break

        # Reconcile paper vs repository
        if paper_seed is not None and repo_seed is not None:
            if paper_seed == repo_seed:
                return ParameterCondition(
                    name="seed",
                    value=paper_seed,
                    source="reconciled",
                    evidence=f"Reconciled: Paper ({paper_evidence}) matches Repository ({repo_evidence})",
                    confidence=1.0,
                    is_assumed=False,
                )
            else:
                return ParameterCondition(
                    name="seed",
                    value=paper_seed,  # Prefer author's reported paper claim condition
                    source="paper",
                    evidence=f"Paper reported {paper_seed} ({paper_evidence}); Repository configured {repo_seed} ({repo_evidence})",
                    confidence=0.9,
                    is_assumed=False,
                    discrepancy=f"Seed discrepancy: paper specifies {paper_seed} while repo specifies {repo_seed}",
                )
        elif paper_seed is not None:
            return ParameterCondition(
                name="seed",
                value=paper_seed,
                source="paper",
                evidence=paper_evidence,
                confidence=0.95,
                is_assumed=False,
            )
        elif repo_seed is not None:
            return ParameterCondition(
                name="seed",
                value=repo_seed,
                source="repository",
                evidence=repo_evidence,
                file_path=repo_file,
                confidence=0.95,
                is_assumed=False,
            )
        else:
            return ParameterCondition(
                name="seed",
                value=42,
                source="assumed",
                evidence="Assumed default seed (42): no seed call or parameter found in paper or repository",
                confidence=0.50,
                is_assumed=True,
            )

    @classmethod
    def _resolve_dataset(
        cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str], repo_readme: str
    ) -> ParameterCondition:
        paper_dataset: str | None = None
        paper_evidence: str | None = None
        repo_dataset: str | None = None
        repo_evidence: str | None = None

        if spec.get("dataset"):
            paper_dataset = str(spec["dataset"]).strip()
            paper_evidence = f"Spec parameter dataset: {paper_dataset}"
        elif paper_text:
            m = re.search(r"dataset[s]?\s*[:=]?\s*([A-Za-z0-9_\-]+)", paper_text, re.I)
            if m:
                paper_dataset = m.group(1).strip()
                paper_evidence = f"Paper text excerpt: '{m.group(0)}'"

        m2 = re.search(r"(?:dataset|data)\s*[:=]?\s*([A-Za-z0-9_\-]+)", repo_readme, re.I)
        if m2:
            repo_dataset = m2.group(1).strip()
            repo_evidence = f"Repository README: '{m2.group(0)}'"
        else:
            for fname, text in repo_files.items():
                m_file = re.search(r"(?:dataset|data)\s*[:=]?\s*([A-Za-z0-9_\-]+)", text, re.I)
                if m_file:
                    repo_dataset = m_file.group(1).strip()
                    repo_evidence = f"Repository {fname}: '{m_file.group(0)}'"
                    break

        if paper_dataset and repo_dataset:
            if paper_dataset.lower() == repo_dataset.lower():
                return ParameterCondition(
                    name="dataset",
                    value=paper_dataset,
                    source="reconciled",
                    evidence=f"Reconciled: Paper ({paper_evidence}) matches Repository ({repo_evidence})",
                    confidence=1.0,
                    is_assumed=False,
                )
            return ParameterCondition(
                name="dataset",
                value=paper_dataset,
                source="paper",
                evidence=f"Paper specifies '{paper_dataset}' ({paper_evidence}); Repository specifies '{repo_dataset}' ({repo_evidence})",
                confidence=0.90,
                is_assumed=False,
                discrepancy=f"Dataset discrepancy: paper specifies {paper_dataset} while repo specifies {repo_dataset}",
            )
        elif paper_dataset:
            return ParameterCondition(
                name="dataset",
                value=paper_dataset,
                source="paper",
                evidence=paper_evidence,
                confidence=0.95,
                is_assumed=False,
            )
        elif repo_dataset:
            return ParameterCondition(
                name="dataset",
                value=repo_dataset,
                source="repository",
                evidence=repo_evidence,
                confidence=0.90,
                is_assumed=False,
            )
        return ParameterCondition(
            name="dataset",
            value="CIFAR-10",
            source="assumed",
            evidence="Default dataset CIFAR-10 assumed; no dataset specified in paper or repository",
            confidence=0.50,
            is_assumed=True,
        )

    @classmethod
    def _resolve_batch_size(
        cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str], repo_readme: str
    ) -> ParameterCondition:
        paper_batch: int | None = None
        paper_evidence: str | None = None
        repo_batch: int | None = None
        repo_evidence: str | None = None

        if spec.get("batch_size"):
            try:
                paper_batch = int(spec["batch_size"])
                paper_evidence = f"Spec parameter batch_size: {paper_batch}"
            except (ValueError, TypeError):
                pass
        elif paper_text:
            m = re.search(r"batch\s*size\s*[:=]?\s*(\d+)", paper_text, re.I)
            if m:
                paper_batch = int(m.group(1))
                paper_evidence = f"Paper text excerpt: '{m.group(0)}'"

        all_repo = [("README.md", repo_readme)] + list(repo_files.items())
        for fname, text in all_repo:
            m2 = re.search(r"(?:batch_size|batch-size|--batch_size|-b)\s*[:=]?\s*(\d+)", text, re.I)
            if m2:
                repo_batch = int(m2.group(1))
                repo_evidence = f"Repository {fname}: '{m2.group(0)}'"
                break

        if paper_batch is not None and repo_batch is not None:
            if paper_batch == repo_batch:
                return ParameterCondition(
                    name="batch_size",
                    value=paper_batch,
                    source="reconciled",
                    evidence=f"Reconciled: Paper ({paper_evidence}) matches Repository ({repo_evidence})",
                    confidence=1.0,
                    is_assumed=False,
                )
            return ParameterCondition(
                name="batch_size",
                value=paper_batch,
                source="paper",
                evidence=f"Paper specifies {paper_batch}; Repository specifies {repo_batch}",
                confidence=0.90,
                is_assumed=False,
                discrepancy=f"Batch size discrepancy: paper specifies {paper_batch} while repo specifies {repo_batch}",
            )
        elif paper_batch is not None:
            return ParameterCondition(
                name="batch_size",
                value=paper_batch,
                source="paper",
                evidence=paper_evidence,
                confidence=0.95,
                is_assumed=False,
            )
        elif repo_batch is not None:
            return ParameterCondition(
                name="batch_size",
                value=repo_batch,
                source="repository",
                evidence=repo_evidence,
                confidence=0.90,
                is_assumed=False,
            )
        return ParameterCondition(
            name="batch_size",
            value=64,
            source="assumed",
            evidence="Default batch size (64) assumed; no batch size found in paper or repository",
            confidence=0.50,
            is_assumed=True,
        )

    @classmethod
    def _resolve_learning_rate(
        cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str], repo_readme: str
    ) -> ParameterCondition:
        paper_lr: float | None = None
        paper_evidence: str | None = None
        repo_lr: float | None = None
        repo_evidence: str | None = None

        if spec.get("learning_rate"):
            try:
                paper_lr = float(spec["learning_rate"])
                paper_evidence = f"Spec parameter learning_rate: {paper_lr}"
            except (ValueError, TypeError):
                pass
        elif paper_text:
            m = re.search(r"learning\s*rate\s*[:=]?\s*([0-9]*\.?[0-9]+(?:e-?[0-9]+)?)", paper_text, re.I)
            if m:
                paper_lr = float(m.group(1))
                paper_evidence = f"Paper text excerpt: '{m.group(0)}'"

        all_repo = [("README.md", repo_readme)] + list(repo_files.items())
        for fname, text in all_repo:
            m2 = re.search(r"(?:lr|learning_rate|--lr)\s*[:=]?\s*([0-9]*\.?[0-9]+(?:e-?[0-9]+)?)", text, re.I)
            if m2:
                repo_lr = float(m2.group(1))
                repo_evidence = f"Repository {fname}: '{m2.group(0)}'"
                break

        if paper_lr is not None and repo_lr is not None:
            if paper_lr == repo_lr:
                return ParameterCondition(
                    name="learning_rate",
                    value=paper_lr,
                    source="reconciled",
                    evidence=f"Reconciled: Paper ({paper_evidence}) matches Repository ({repo_evidence})",
                    confidence=1.0,
                    is_assumed=False,
                )
            return ParameterCondition(
                name="learning_rate",
                value=paper_lr,
                source="paper",
                evidence=f"Paper specifies {paper_lr}; Repository specifies {repo_lr}",
                confidence=0.90,
                is_assumed=False,
                discrepancy=f"Learning rate discrepancy: paper specifies {paper_lr} while repo specifies {repo_lr}",
            )
        elif paper_lr is not None:
            return ParameterCondition(
                name="learning_rate",
                value=paper_lr,
                source="paper",
                evidence=paper_evidence,
                confidence=0.95,
                is_assumed=False,
            )
        elif repo_lr is not None:
            return ParameterCondition(
                name="learning_rate",
                value=repo_lr,
                source="repository",
                evidence=repo_evidence,
                confidence=0.90,
                is_assumed=False,
            )
        return ParameterCondition(
            name="learning_rate",
            value=0.001,
            source="assumed",
            evidence="Default learning rate (0.001) assumed; no lr found in paper or repository",
            confidence=0.50,
            is_assumed=True,
        )

    @classmethod
    def _resolve_epochs(
        cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str], repo_readme: str
    ) -> ParameterCondition:
        paper_epochs: int | None = None
        paper_evidence: str | None = None
        repo_epochs: int | None = None
        repo_evidence: str | None = None

        if spec.get("epochs"):
            try:
                paper_epochs = int(spec["epochs"])
                paper_evidence = f"Spec parameter epochs: {paper_epochs}"
            except (ValueError, TypeError):
                pass
        elif paper_text:
            m = re.search(r"epochs?\s*[:=]?\s*(\d+)", paper_text, re.I)
            if m:
                paper_epochs = int(m.group(1))
                paper_evidence = f"Paper text excerpt: '{m.group(0)}'"

        all_repo = [("README.md", repo_readme)] + list(repo_files.items())
        for fname, text in all_repo:
            m2 = re.search(r"(?:epochs|num_epochs|--epochs)\s*[:=]?\s*(\d+)", text, re.I)
            if m2:
                repo_epochs = int(m2.group(1))
                repo_evidence = f"Repository {fname}: '{m2.group(0)}'"
                break

        if paper_epochs is not None and repo_epochs is not None:
            if paper_epochs == repo_epochs:
                return ParameterCondition(
                    name="epochs",
                    value=paper_epochs,
                    source="reconciled",
                    evidence=f"Reconciled: Paper ({paper_evidence}) matches Repository ({repo_evidence})",
                    confidence=1.0,
                    is_assumed=False,
                )
            return ParameterCondition(
                name="epochs",
                value=paper_epochs,
                source="paper",
                evidence=f"Paper specifies {paper_epochs}; Repository specifies {repo_epochs}",
                confidence=0.90,
                is_assumed=False,
                discrepancy=f"Epochs discrepancy: paper specifies {paper_epochs} while repo specifies {repo_epochs}",
            )
        elif paper_epochs is not None:
            return ParameterCondition(
                name="epochs",
                value=paper_epochs,
                source="paper",
                evidence=paper_evidence,
                confidence=0.95,
                is_assumed=False,
            )
        elif repo_epochs is not None:
            return ParameterCondition(
                name="epochs",
                value=repo_epochs,
                source="repository",
                evidence=repo_evidence,
                confidence=0.90,
                is_assumed=False,
            )
        return ParameterCondition(
            name="epochs",
            value=10,
            source="assumed",
            evidence="Default epochs (10) assumed; no epoch count found in paper or repository",
            confidence=0.50,
            is_assumed=True,
        )

    @classmethod
    def _resolve_optimizer(
        cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str], repo_readme: str
    ) -> ParameterCondition:
        paper_opt: str | None = None
        paper_evidence: str | None = None
        repo_opt: str | None = None
        repo_evidence: str | None = None

        if spec.get("optimizer"):
            paper_opt = str(spec["optimizer"]).strip()
            paper_evidence = f"Spec parameter optimizer: {paper_opt}"
        elif paper_text:
            for opt in ["AdamW", "Adam", "SGD", "RMSprop", "Adagrad"]:
                if opt.lower() in paper_text.lower():
                    paper_opt = opt
                    paper_evidence = f"Paper text mentioned optimizer: {opt}"
                    break

        all_repo = [("README.md", repo_readme)] + list(repo_files.items())
        for fname, text in all_repo:
            for opt in ["AdamW", "Adam", "SGD", "RMSprop", "Adagrad"]:
                if f"optim.{opt}" in text or f'"{opt}"' in text or f"'{opt}'" in text:
                    repo_opt = opt
                    repo_evidence = f"Repository {fname}: optim.{opt}"
                    break
            if repo_opt:
                break

        if paper_opt and repo_opt:
            if paper_opt.lower() == repo_opt.lower():
                return ParameterCondition(
                    name="optimizer",
                    value=paper_opt,
                    source="reconciled",
                    evidence=f"Reconciled: Paper ({paper_evidence}) matches Repository ({repo_evidence})",
                    confidence=1.0,
                    is_assumed=False,
                )
            return ParameterCondition(
                name="optimizer",
                value=paper_opt,
                source="paper",
                evidence=f"Paper specifies {paper_opt}; Repository specifies {repo_opt}",
                confidence=0.90,
                is_assumed=False,
                discrepancy=f"Optimizer discrepancy: paper specifies {paper_opt} while repo specifies {repo_opt}",
            )
        elif paper_opt:
            return ParameterCondition(
                name="optimizer",
                value=paper_opt,
                source="paper",
                evidence=paper_evidence,
                confidence=0.95,
                is_assumed=False,
            )
        elif repo_opt:
            return ParameterCondition(
                name="optimizer",
                value=repo_opt,
                source="repository",
                evidence=repo_evidence,
                confidence=0.90,
                is_assumed=False,
            )
        return ParameterCondition(
            name="optimizer",
            value="Adam",
            source="assumed",
            evidence="Default optimizer (Adam) assumed; none found in paper or repository",
            confidence=0.50,
            is_assumed=True,
        )

    @classmethod
    def _resolve_architecture(
        cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str], repo_readme: str
    ) -> ParameterCondition:
        paper_arch: str | None = None
        paper_evidence: str | None = None
        repo_arch: str | None = None
        repo_evidence: str | None = None

        if spec.get("architecture") and spec["architecture"] != "inferred from paper":
            paper_arch = str(spec["architecture"]).strip()
            paper_evidence = f"Spec parameter architecture: {paper_arch}"
        elif paper_text:
            for arch in ["ResNet", "Transformer", "VGG", "BERT", "GPT", "MLP", "CNN"]:
                if arch.lower() in paper_text.lower():
                    paper_arch = arch
                    paper_evidence = f"Paper text mentioned architecture: {arch}"
                    break

        for fname, text in repo_files.items():
            m = re.search(r"class\s+([A-Za-z0-9_]+)\s*\(\s*(?:nn\.)?Module\s*\)", text)
            if m:
                repo_arch = m.group(1)
                repo_evidence = f"Repository {fname} defines class {repo_arch}(nn.Module)"
                break

        if paper_arch and repo_arch:
            if paper_arch.lower() in repo_arch.lower() or repo_arch.lower() in paper_arch.lower():
                return ParameterCondition(
                    name="architecture",
                    value=repo_arch,
                    source="reconciled",
                    evidence=f"Reconciled: Paper ({paper_evidence}) matches Repository class ({repo_evidence})",
                    confidence=1.0,
                    is_assumed=False,
                )
            return ParameterCondition(
                name="architecture",
                value=repo_arch,
                source="repository",
                evidence=f"Repository implementation {repo_arch} ({repo_evidence}) chosen over paper reference ({paper_evidence})",
                confidence=0.90,
                is_assumed=False,
                discrepancy=f"Architecture naming discrepancy: paper specifies {paper_arch} while repo implements {repo_arch}",
            )
        elif repo_arch:
            return ParameterCondition(
                name="architecture",
                value=repo_arch,
                source="repository",
                evidence=repo_evidence,
                confidence=0.95,
                is_assumed=False,
            )
        elif paper_arch:
            return ParameterCondition(
                name="architecture",
                value=paper_arch,
                source="paper",
                evidence=paper_evidence,
                confidence=0.90,
                is_assumed=False,
            )
        return ParameterCondition(
            name="architecture",
            value="CNNClassifier",
            source="assumed",
            evidence="Default CNNClassifier assumed; no architecture found in paper or repository",
            confidence=0.50,
            is_assumed=True,
        )

    @classmethod
    def _resolve_metrics(cls, spec: dict[str, Any], paper_text: str, repo_files: dict[str, str]) -> ParameterCondition:
        metrics = spec.get("metrics")
        if metrics and isinstance(metrics, list) and len(metrics) > 0:
            return ParameterCondition(name="metrics", value=metrics, source="paper", confidence=0.95)
        found: list[str] = []
        for m in ["accuracy", "f1", "precision", "recall", "mAP", "auc", "loss", "bleu"]:
            if m in paper_text.lower():
                found.append(m)
        if found:
            return ParameterCondition(name="metrics", value=found, source="paper", confidence=0.90)
        return ParameterCondition(name="metrics", value=["accuracy"], source="assumed", confidence=0.5, is_assumed=True)
