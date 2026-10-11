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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from .models import (
    DependencyCheck,
    EnvironmentBuildProgress,
    EnvironmentPreview,
    ImportItem,
)


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
        "psutil",
        "tensorflow",
    }

    # Map from import module name to PyPI package name
    IMPORT_TO_PKG_MAP = {
        "torch": "torch",
        "torchvision": "torchvision",
        "torchaudio": "torchaudio",
        "numpy": "numpy",
        "np": "numpy",
        "sklearn": "scikit-learn",
        "scipy": "scipy",
        "pandas": "pandas",
        "pd": "pandas",
        "PIL": "pillow",
        "cv2": "opencv-python",
        "matplotlib": "matplotlib",
        "plt": "matplotlib",
        "seaborn": "seaborn",
        "sns": "seaborn",
        "timm": "timm",
        "transformers": "transformers",
        "datasets": "datasets",
        "accelerate": "accelerate",
        "yaml": "pyyaml",
        "tqdm": "tqdm",
        "rich": "rich",
        "requests": "requests",
        "optuna": "optuna",
        "xgboost": "xgboost",
        "lightgbm": "lightgbm",
        "catboost": "catboost",
        "h5py": "h5py",
    }

    # ------------------------------------------------------------------
    # Detailed Automated Dependency Detection
    # ------------------------------------------------------------------
    @classmethod
    def detect_detailed_imports(
        cls,
        graph: Any = None,
        spec: dict[str, Any] | None = None,
        explicit_packages: list[str] | None = None,
    ) -> list[ImportItem]:
        """Detect and group all Python imports across DAG nodes with module mapping."""
        # Mapping: module_name -> {package, nodes, statements}
        detected_map: dict[str, dict[str, Any]] = {}

        def record_import(mod_name: str, node_id: str, stmt: str) -> None:
            mod_clean = mod_name.strip().split(".")[0]
            if not mod_clean or mod_clean in {"os", "sys", "json", "random", "re", "math", "time", "datetime", "pathlib", "typing", "collections", "itertools", "functools", "shutil", "tempfile", "hashlib", "copy", "subprocess"}:
                return  # Skip standard library modules

            pkg_name = cls.IMPORT_TO_PKG_MAP.get(mod_clean, mod_clean.lower())
            if mod_clean not in detected_map:
                detected_map[mod_clean] = {
                    "module": mod_clean,
                    "package": pkg_name,
                    "nodes": set(),
                    "import_statements": set(),
                }
            detected_map[mod_clean]["nodes"].add(node_id)
            if stmt:
                detected_map[mod_clean]["import_statements"].add(stmt.strip())

        # 1. Scan graph nodes code for import statements
        if graph and hasattr(graph, "nodes"):
            for node in graph.nodes:
                node_id = getattr(node, "id", "unknown_node")
                code = getattr(node, "code", "")
                for line in code.splitlines():
                    trimmed = line.strip()
                    if trimmed.startswith("import "):
                        parts = trimmed[len("import "):].split(",")
                        for part in parts:
                            mod = part.strip().split()[0].split(".")[0]
                            record_import(mod, node_id, trimmed)
                    elif trimmed.startswith("from "):
                        match = re.match(r"^from\s+([A-Za-z0-9_]+)", trimmed)
                        if match:
                            mod = match.group(1)
                            record_import(mod, node_id, trimmed)

        # 2. Check repository files for requirements.txt
        if spec and isinstance(spec, dict):
            repo = spec.get("repo", {})
            files = repo.get("files", {}) if isinstance(repo, dict) else {}
            if "requirements.txt" in files:
                req_text = files["requirements.txt"]
                parsed = cls.parse_requirements(req_text)
                for item in parsed:
                    p_name = item["name"]
                    # Reverse-lookup module or default to package name
                    rev_mod = next((k for k, v in cls.IMPORT_TO_PKG_MAP.items() if v == p_name), p_name)
                    record_import(rev_mod, "requirements.txt", f"requirement: {p_name}")

        # 3. Explicitly requested packages
        if explicit_packages:
            for p in explicit_packages:
                clean_p = re.split(r"[=><~!]", p.strip())[0].lower()
                rev_mod = next((k for k, v in cls.IMPORT_TO_PKG_MAP.items() if v == clean_p), clean_p)
                record_import(rev_mod, "custom_configured", f"configured: {p}")

        # Build list of ImportItem models
        items: list[ImportItem] = []
        for mod, data in sorted(detected_map.items()):
            items.append(
                ImportItem(
                    module=data["module"],
                    package=data["package"],
                    nodes=sorted(data["nodes"]),
                    import_statements=sorted(data["import_statements"]),
                )
            )
        return items

    @classmethod
    def detect_required_packages(
        cls,
        graph: Any = None,
        spec: dict[str, Any] | None = None,
        explicit_packages: list[str] | None = None,
    ) -> list[str]:
        """Detect all required Python packages from DAG code and spec."""
        detailed = cls.detect_detailed_imports(graph, spec, explicit_packages)
        detected = {item.package for item in detailed}

        # Default standard ML stack if any ML primitives are in DAG
        if "torch" in detected or any("train" in getattr(n, "id", "") for n in getattr(graph, "nodes", [])):
            detected.add("torch")
            detected.add("numpy")

        return sorted(detected)

    # ------------------------------------------------------------------
    # Container Library Verification (Pre-Flight Check)
    # ------------------------------------------------------------------
    @classmethod
    def verify_container_libraries(
        cls,
        docker_image: str,
        import_items: list[ImportItem],
        timeout_seconds: int = 15,
    ) -> tuple[bool, list[ImportItem], list[str]]:
        """Verify whether all required libraries are installed and importable in the container."""
        if not import_items:
            return True, [], []

        updated_items: list[ImportItem] = [i.model_copy() for i in import_items]
        missing_pkgs: list[str] = []

        # If Docker is available and image exists, execute in-container probe
        if cls._is_docker_available() and cls._docker_image_exists(docker_image):
            probe_modules = list(dict.fromkeys(item.module for item in updated_items))
            probe_script = (
                "import sys, importlib, json\n"
                f"mods = {json.dumps(probe_modules)}\n"
                "res = {}\n"
                "for m in mods:\n"
                "    try:\n"
                "        mod = importlib.import_module(m)\n"
                "        res[m] = {'installed': True, 'version': str(getattr(mod, '__version__', 'available'))}\n"
                "    except Exception as e:\n"
                "        res[m] = {'installed': False, 'error': str(e)}\n"
                "print(json.dumps(res))\n"
            )

            try:
                probe_res = subprocess.run(
                    ["docker", "run", "--rm", docker_image, "python", "-c", probe_script],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                if probe_res.returncode == 0:
                    probe_output = probe_res.stdout.strip()
                    # Filter output to json line
                    json_line = next((l for l in probe_output.splitlines() if l.startswith("{")), "{}")
                    results = json.loads(json_line)
                    for item in updated_items:
                        mod_res = results.get(item.module)
                        if mod_res and mod_res.get("installed"):
                            item.installed = True
                            item.installed_version = mod_res.get("version")
                            item.issue = None
                        else:
                            item.installed = False
                            item.issue = mod_res.get("error") if mod_res else "Module not found in container"
                            if item.package not in missing_pkgs:
                                missing_pkgs.append(item.package)
                    all_installed = len(missing_pkgs) == 0
                    return all_installed, updated_items, missing_pkgs
            except Exception as exc:
                print(f"[EnvironmentManager] Container probe failed: {exc}", flush=True)

        # Fallback check (e.g. without docker daemon or if probe failed)
        is_ml_base = "crisisgrid-ml-base" in docker_image
        for item in updated_items:
            pkg_clean = item.package.lower()
            if is_ml_base and pkg_clean in cls.PREINSTALLED_ML_PACKAGES:
                item.installed = True
                item.installed_version = "pre-baked"
            else:
                # Mark as installed if part of preinstalled base, else flag missing
                if pkg_clean in cls.PREINSTALLED_ML_PACKAGES:
                    item.installed = True
                    item.installed_version = "standard"
                else:
                    item.installed = False
                    item.issue = f"Library '{item.package}' not verified in container image"
                    if item.package not in missing_pkgs:
                        missing_pkgs.append(item.package)

        all_installed = len(missing_pkgs) == 0
        return all_installed, updated_items, missing_pkgs

    @classmethod
    def get_environment_preview(
        cls,
        graph: Any = None,
        spec: dict[str, Any] | None = None,
        explicit_packages: list[str] | None = None,
        docker_image: str = "crisisgrid-ml-base:latest",
    ) -> EnvironmentPreview:
        """Generate comprehensive pre-flight environment preview with container availability."""
        # Check if docker image exists, fallback to crisisgrid-ml-base or python:3.11-slim
        target_image = docker_image
        if not cls._docker_image_exists(target_image):
            if cls._docker_image_exists("crisisgrid-ml-base:latest"):
                target_image = "crisisgrid-ml-base:latest"
            else:
                target_image = "python:3.11-slim"

        raw_imports = cls.detect_detailed_imports(graph, spec, explicit_packages)
        all_ok, verified_imports, missing_pkgs = cls.verify_container_libraries(target_image, raw_imports)
        required_pkgs = sorted({i.package for i in verified_imports})

        return EnvironmentPreview(
            docker_image=target_image,
            detected_imports=verified_imports,
            required_packages=required_pkgs,
            all_installed=all_ok,
            missing_packages=missing_pkgs,
            can_preinstall=cls._is_docker_available(),
        )

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
    # Pre-Execution Image Preparation & Real-Time Build Tracking
    # ------------------------------------------------------------------
    _build_progress: dict[str, EnvironmentBuildProgress] = {}

    @classmethod
    def get_build_progress(cls, experiment_id: str) -> EnvironmentBuildProgress:
        """Retrieve real-time container build progress and logs."""
        if experiment_id not in cls._build_progress:
            return EnvironmentBuildProgress(
                experiment_id=experiment_id,
                status="idle",
                docker_image="crisisgrid-ml-base:latest",
                current_step="No build currently in progress",
                percent=0,
            )
        return cls._build_progress[experiment_id]

    @classmethod
    def _record_progress(
        cls,
        experiment_id: str | None,
        status: Literal["idle", "building", "completed", "failed"],
        step: str = "",
        pct: int = 0,
        log_line: str | None = None,
        docker_image: str = "",
        packages: list[str] | None = None,
        error: str | None = None,
        on_progress: Callable[[int, str, str], None] | None = None,
        current_step: str | None = None,
        percent: int | None = None,
        logs: list[str] | None = None,
    ) -> None:
        effective_step = current_step if current_step is not None else step
        effective_pct = percent if percent is not None else pct
        if experiment_id:
            now_iso = datetime.now(timezone.utc).isoformat()
            if experiment_id not in cls._build_progress:
                cls._build_progress[experiment_id] = EnvironmentBuildProgress(
                    experiment_id=experiment_id,
                    status=status,
                    docker_image=docker_image,
                    packages=packages or [],
                    current_step=effective_step,
                    percent=effective_pct,
                    logs=list(logs) if logs else [],
                    error=error,
                    started_at=now_iso,
                )
            else:
                prog = cls._build_progress[experiment_id]
                prog.status = status
                prog.current_step = effective_step
                prog.percent = effective_pct
                if docker_image:
                    prog.docker_image = docker_image
                if packages is not None:
                    prog.packages = packages
                if error:
                    prog.error = error
                if logs:
                    prog.logs.extend(logs)
                if status in ("completed", "failed"):
                    prog.completed_at = now_iso

            if log_line:
                prog = cls._build_progress[experiment_id]
                prog.logs.append(log_line)
                if len(prog.logs) > 500:
                    prog.logs = prog.logs[-500:]

        if on_progress and log_line:
            try:
                on_progress(effective_pct, effective_step, log_line)
            except Exception:
                pass

    @classmethod
    def prepare_image(
        cls,
        packages: list[str],
        base_image: str = "crisisgrid-ml-base:latest",
        timeout_seconds: int = 300,
        experiment_id: str | None = None,
        on_progress: Callable[[int, str, str], None] | None = None,
    ) -> str:
        """Ensure all dependencies are pre-installed in a Docker image before execution.

        Returns the image tag to use for container execution.
        """
        # If no packages are required, return the base image
        if not packages:
            cls._record_progress(
                experiment_id=experiment_id,
                status="completed",
                step="No extra packages required",
                pct=100,
                log_line=f"[INFO] Using base image {base_image} directly (no extra packages needed).",
                docker_image=base_image,
                packages=[],
                on_progress=on_progress,
            )
            return base_image

        # Check if Docker is available
        if not cls._is_docker_available():
            cls._record_progress(
                experiment_id=experiment_id,
                status="completed",
                step="Docker unavailable; using base image fallback",
                pct=100,
                log_line="[WARNING] Docker daemon is not available; falling back to base image.",
                docker_image=base_image,
                packages=packages,
                on_progress=on_progress,
            )
            return base_image

        normalized_pkgs = {re.split(r"[=><~!]", p)[0].lower() for p in packages}

        # Check if crisisgrid-ml-base:latest is already available and satisfies requirements
        ml_base_exists = cls._docker_image_exists("crisisgrid-ml-base:latest")

        # If base image exists and all required packages are pre-installed in it
        if ml_base_exists and normalized_pkgs.issubset(cls.PREINSTALLED_ML_PACKAGES):
            cls._record_progress(
                experiment_id=experiment_id,
                status="completed",
                step="All libraries already pre-installed in base image",
                pct=100,
                log_line="[INFO] All requested libraries are pre-installed in crisisgrid-ml-base:latest.",
                docker_image="crisisgrid-ml-base:latest",
                packages=packages,
                on_progress=on_progress,
            )
            return "crisisgrid-ml-base:latest"

        # If additional packages need to be installed, generate a deterministic hash tag
        sorted_pkgs = sorted(packages)
        pkg_hash = hashlib.sha256(json.dumps(sorted_pkgs).encode()).hexdigest()[:12]
        custom_tag = f"crisisgrid-env-{pkg_hash}:latest"

        if cls._docker_image_exists(custom_tag):
            cls._record_progress(
                experiment_id=experiment_id,
                status="completed",
                step=f"Reusing existing pre-built container image {custom_tag}",
                pct=100,
                log_line=f"[INFO] Found pre-built cached image {custom_tag} satisfying requirements.",
                docker_image=custom_tag,
                packages=packages,
                on_progress=on_progress,
            )
            return custom_tag

        # Build image with pre-installed packages
        try:
            parent_image = "crisisgrid-ml-base:latest" if ml_base_exists else base_image
            pkgs_to_install = [
                p for p in sorted_pkgs
                if not (ml_base_exists and re.split(r"[=><~!]", p)[0].lower() in cls.PREINSTALLED_ML_PACKAGES)
            ]

            if not pkgs_to_install:
                cls._record_progress(
                    experiment_id=experiment_id,
                    status="completed",
                    step=f"Reusing parent image {parent_image}",
                    pct=100,
                    log_line=f"[INFO] Using {parent_image} (all packages satisfied).",
                    docker_image=parent_image,
                    packages=packages,
                    on_progress=on_progress,
                )
                return parent_image

            cls._record_progress(
                experiment_id=experiment_id,
                status="building",
                step=f"Preparing build context with packages: {', '.join(pkgs_to_install)}",
                pct=15,
                log_line=f"[1/4] Preparing build context for base image {parent_image}...",
                docker_image=custom_tag,
                packages=packages,
                on_progress=on_progress,
            )

            with tempfile.TemporaryDirectory() as tmp_dir:
                dockerfile_path = Path(tmp_dir) / "Dockerfile"
                pkg_str = " ".join(pkgs_to_install)

                lines = [
                    f"FROM {parent_image}",
                    f"RUN pip install --no-cache-dir {pkg_str}",
                ]
                dockerfile_path.write_text("\n".join(lines), encoding="utf-8")

                cls._record_progress(
                    experiment_id=experiment_id,
                    status="building",
                    step=f"Executing docker build: pip install {pkg_str}",
                    pct=25,
                    log_line=f"[2/4] Running: pip install --no-cache-dir {pkg_str}",
                    docker_image=custom_tag,
                    packages=packages,
                    on_progress=on_progress,
                )

                cmd = ["docker", "build", "--progress=plain", "-t", custom_tag, tmp_dir]
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )

                if process.stdout:
                    for raw_line in iter(process.stdout.readline, ''):
                        line = raw_line.rstrip()
                        if not line:
                            continue

                        # Determine progress percentage and current step
                        pct = 40
                        step_desc = None
                        if "Step " in line or "FROM " in line:
                            pct = 30
                            step_desc = "Preparing container base layer"
                        elif "Collecting " in line:
                            pct = 50
                            target_mod = line.split("Collecting ")[-1].strip()
                            step_desc = f"Resolving package: {target_mod}"
                        elif "Downloading " in line:
                            pct = 65
                            wheel_name = line.split("Downloading ")[-1].split("(")[0].strip()
                            step_desc = f"Downloading: {wheel_name}"
                        elif "Installing collected packages" in line or "Building wheels" in line:
                            pct = 85
                            step_desc = "Installing compiled wheels into container..."
                        elif "Successfully installed" in line:
                            pct = 95
                            installed_str = line.split("Successfully installed")[-1].strip()
                            step_desc = f"Installed: {installed_str}"

                        current_step = step_desc or cls.get_build_progress(experiment_id or "").current_step
                        cls._record_progress(
                            experiment_id=experiment_id,
                            status="building",
                            step=current_step,
                            pct=pct,
                            log_line=line,
                            docker_image=custom_tag,
                            packages=packages,
                            on_progress=on_progress,
                        )

                    process.stdout.close()

                return_code = process.wait(timeout=timeout_seconds)

                if return_code == 0:
                    cls._record_progress(
                        experiment_id=experiment_id,
                        status="completed",
                        step=f"Container image {custom_tag} built successfully",
                        pct=100,
                        log_line=f"[3/3] ✓ Successfully installed dependencies into {custom_tag}",
                        docker_image=custom_tag,
                        packages=packages,
                        on_progress=on_progress,
                    )
                    print(f"[EnvironmentManager] Successfully pre-installed dependencies into {custom_tag}", flush=True)
                    return custom_tag
                else:
                    err_msg = f"Docker build failed with exit code {return_code}"
                    cls._record_progress(
                        experiment_id=experiment_id,
                        status="failed",
                        step=err_msg,
                        pct=0,
                        log_line=f"[ERROR] {err_msg}",
                        docker_image=parent_image,
                        packages=packages,
                        error=err_msg,
                        on_progress=on_progress,
                    )
                    print(f"[EnvironmentManager] {err_msg}", flush=True)
                    return parent_image

        except Exception as exc:
            err_msg = f"Error preparing image: {exc}"
            cls._record_progress(
                experiment_id=experiment_id,
                status="failed",
                step=err_msg,
                pct=0,
                log_line=f"[EXCEPTION] {err_msg}",
                docker_image=base_image,
                packages=packages,
                error=err_msg,
                on_progress=on_progress,
            )
            print(f"[EnvironmentManager] {err_msg}", flush=True)
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
