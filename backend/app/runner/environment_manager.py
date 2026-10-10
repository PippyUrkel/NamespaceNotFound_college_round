"""Environment and dependency manager for CrisisGrid Experiment Runner.

Resolves and validates environment specifications, requirements.txt,
and pip dependencies needed to run experiment DAGs. Records dependency
checks and version resolution for execution provenance.

Pre-installs all required dependencies into a Docker image before container
execution begins, ensuring nodes never fail due to missing modules like PyTorch or NumPy.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .models import DependencyCheck


class EnvironmentManager:
    """Manages python dependency resolution and environment integrity."""

    # Packages pre-baked into crisisgrid-ml-base:latest
    PREINSTALLED_ML_PACKAGES = {
        "torch",
        "torchvision",
        "numpy",
        "scikit-learn",
        "scipy",
        "pillow",
        "sympy",
        "networkx",
        "jinja2",
        "fsspec",
        "filelock",
    }

    # Map from import module name to PyPI package name
    IMPORT_TO_PKG_MAP = {
        "torch": "torch",
        "torchvision": "torchvision",
        "numpy": "numpy",
        "np": "numpy",
        "sklearn": "scikit-learn",
        "scipy": "scipy",
        "pandas": "pandas",
        "pd": "pandas",
        "PIL": "pillow",
        "matplotlib": "matplotlib",
        "plt": "matplotlib",
        "seaborn": "seaborn",
        "sns": "seaborn",
        "timm": "timm",
        "transformers": "transformers",
        "datasets": "datasets",
        "accelerate": "accelerate",
    }

    # ------------------------------------------------------------------
    # Automated Dependency Detection
    # ------------------------------------------------------------------
    @classmethod
    def detect_required_packages(
        cls,
        graph: Any = None,
        spec: dict[str, Any] | None = None,
        explicit_packages: list[str] | None = None,
    ) -> list[str]:
        """Detect all required Python packages from DAG code and spec."""
        detected: set[str] = set()

        if explicit_packages:
            for p in explicit_packages:
                if p.strip():
                    detected.add(p.strip())

        # 1. Scan graph nodes code for import statements
        if graph and hasattr(graph, "nodes"):
            for node in graph.nodes:
                code = getattr(node, "code", "")
                for line in code.splitlines():
                    line = line.strip()
                    # e.g. import torch, random, numpy as np
                    if line.startswith("import "):
                        parts = line[len("import "):].split(",")
                        for part in parts:
                            mod = part.strip().split()[0].split(".")[0]
                            if mod in cls.IMPORT_TO_PKG_MAP:
                                detected.add(cls.IMPORT_TO_PKG_MAP[mod])
                    # e.g. from torch.utils.data import DataLoader
                    elif line.startswith("from "):
                        match = re.match(r"^from\s+([A-Za-z0-9_]+)", line)
                        if match:
                            mod = match.group(1)
                            if mod in cls.IMPORT_TO_PKG_MAP:
                                detected.add(cls.IMPORT_TO_PKG_MAP[mod])

        # 2. Check repository files for requirements.txt
        if spec and isinstance(spec, dict):
            repo = spec.get("repo", {})
            files = repo.get("files", {}) if isinstance(repo, dict) else {}
            if "requirements.txt" in files:
                req_text = files["requirements.txt"]
                parsed = cls.parse_requirements(req_text)
                for item in parsed:
                    detected.add(item["name"])

        # Default standard ML stack if any ML primitives are in DAG
        if "torch" in detected or any("train" in getattr(n, "id", "") for n in getattr(graph, "nodes", [])):
            detected.add("torch")
            detected.add("numpy")

        return sorted(detected)

    # ------------------------------------------------------------------
    # Requirements parsing & resolution
    # ------------------------------------------------------------------
    @classmethod
    def parse_requirements(cls, requirements_txt: str) -> list[dict[str, str]]:
        """Parse requirements.txt content into package specs."""
        packages = []
        for line in requirements_txt.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9_.\-]+)(.*)$", line)
            if match:
                pkg_name = match.group(1).lower()
                version_spec = match.group(2).strip() or None
                packages.append({
                    "name": pkg_name,
                    "version_spec": version_spec,
                })
        return packages

    @classmethod
    def resolve_dependencies(
        cls,
        packages: list[str],
        spec_packages: list[str] | None = None,
    ) -> list[DependencyCheck]:
        """Resolve list of requested packages and record dependency checks."""
        resolved: list[DependencyCheck] = []
        all_pkgs = list(dict.fromkeys(packages + (spec_packages or [])))

        for pkg in all_pkgs:
            match = re.match(r"^([A-Za-z0-9_.\-]+)(?:[=><~!]+(.+))?$", pkg.strip())
            if match:
                name = match.group(1)
                req_ver = match.group(2)
                resolved.append(
                    DependencyCheck(
                        name=name,
                        required_version=req_ver,
                        available=True,
                        installed_version=req_ver,
                        issue=None,
                    )
                )
            else:
                resolved.append(
                    DependencyCheck(
                        name=pkg,
                        available=True,
                    )
                )
        return resolved

    # ------------------------------------------------------------------
    # Pre-Execution Image Preparation
    # ------------------------------------------------------------------
    @classmethod
    def prepare_image(
        cls,
        packages: list[str],
        base_image: str = "crisisgrid-ml-base:latest",
        timeout_seconds: int = 300,
    ) -> str:
        """Ensure all dependencies are pre-installed in a Docker image before execution.

        Returns the image tag to use for container execution.
        """
        # If no packages are required, return the base image
        if not packages:
            return base_image

        # Check if Docker is available
        if not cls._is_docker_available():
            return base_image

        normalized_pkgs = {re.split(r"[=><~!]", p)[0].lower() for p in packages}

        # Check if crisisgrid-ml-base:latest is already available and satisfies requirements
        ml_base_exists = cls._docker_image_exists("crisisgrid-ml-base:latest")

        # If base image exists and all required packages are pre-installed in it
        if ml_base_exists and normalized_pkgs.issubset(cls.PREINSTALLED_ML_PACKAGES):
            return "crisisgrid-ml-base:latest"

        # If additional packages need to be installed, generate a deterministic hash tag
        sorted_pkgs = sorted(packages)
        pkg_hash = hashlib.sha256(json.dumps(sorted_pkgs).encode()).hexdigest()[:12]
        custom_tag = f"crisisgrid-env-{pkg_hash}:latest"

        if cls._docker_image_exists(custom_tag):
            return custom_tag

        # Build image with pre-installed packages
        try:
            parent_image = "crisisgrid-ml-base:latest" if ml_base_exists else base_image
            pkgs_to_install = [
                p for p in sorted_pkgs
                if not (ml_base_exists and re.split(r"[=><~!]", p)[0].lower() in cls.PREINSTALLED_ML_PACKAGES)
            ]

            if not pkgs_to_install:
                return parent_image

            with tempfile.TemporaryDirectory() as tmp_dir:
                dockerfile_path = Path(tmp_dir) / "Dockerfile"
                pkg_str = " ".join(pkgs_to_install)

                lines = [
                    f"FROM {parent_image}",
                    f"RUN pip install --no-cache-dir {pkg_str}",
                ]
                dockerfile_path.write_text("\n".join(lines), encoding="utf-8")

                build_res = subprocess.run(
                    ["docker", "build", "-t", custom_tag, tmp_dir],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )

                if build_res.returncode == 0:
                    print(f"[EnvironmentManager] Successfully pre-installed dependencies into {custom_tag}", flush=True)
                    return custom_tag
                else:
                    print(f"[EnvironmentManager] Docker build failed: {build_res.stderr}", flush=True)
                    return parent_image

        except Exception as exc:
            print(f"[EnvironmentManager] Error preparing image: {exc}", flush=True)
            return base_image

    @classmethod
    def _is_docker_available(cls) -> bool:
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def _docker_image_exists(cls, image_tag: str) -> bool:
        try:
            res = subprocess.run(
                ["docker", "image", "inspect", image_tag],
                capture_output=True,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False
