"""Docker worker — isolated container execution for DAG nodes.

Each node runs inside a Docker container with:
- Configurable resource limits (memory, CPU)
- Configurable timeout with correct process termination
- Seed injection via environment variables
- Structured output collection (stdout, stderr, exit code, metrics)
- Volume mounting for input/output data flow between nodes

The worker never silently modifies scientific parameters.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings

from .models import (
    FailureReason,
    NodeExecutionConfig,
    NodeRunResult,
    RunStatus,
)


class DockerWorker:
    """Execute a single DAG node code block inside a Docker container."""

    def __init__(
        self,
        work_dir: Path,
        docker_image: str = "python:3.11-slim",
        shared_cache_dir: Path | None = None,
    ) -> None:
        self._work_dir = Path(work_dir).resolve()
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._docker_image = docker_image
        # Downloads (datasets, pretrained weights, pip wheels) persist here across nodes, seeds and
        # experiments. Every node re-runs its upstream code, so without this each node re-downloads.
        self._shared_cache_dir = Path(shared_cache_dir or Path(settings.artifacts_dir) / "shared_cache").resolve()
        for sub in ("data", "torch", "huggingface", "pip"):
            sub_dir = self._shared_cache_dir / sub
            sub_dir.mkdir(parents=True, exist_ok=True)
            try:
                sub_dir.chmod(0o777)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute_node(
        self,
        node_id: str,
        code: str,
        seed: int,
        parameters: dict[str, Any],
        config: NodeExecutionConfig | None = None,
        upstream_outputs_dir: Path | None = None,
        pip_packages: list[str] | None = None,
        upstream_code: str | None = None,
    ) -> NodeRunResult:
        """Run a node's code in Docker and return a structured result."""
        cfg = config or NodeExecutionConfig(node_id=node_id)
        started_at = datetime.now(timezone.utc).isoformat()

        # Prepare workspace (always resolve to absolute paths for Docker host mounts)
        node_dir = (self._work_dir / f"node_{node_id}_seed_{seed}").resolve()
        node_dir.mkdir(parents=True, exist_ok=True)
        code_file = node_dir / "run.py"
        output_dir = (node_dir / "output").resolve()
        output_dir.mkdir(exist_ok=True)
        metrics_file = node_dir / "metrics.json"

        # Build the runner script: seed & device injection + upstream context + user code + metrics capture
        runner_code = self._build_runner_script(
            code=code,
            seed=seed,
            parameters=parameters,
            metrics_filename=metrics_file.name,
            upstream_code=upstream_code,
        )
        code_file.write_text(runner_code, encoding="utf-8")

        # Build pip install prefix
        pip_install_cmd = ""
        if pip_packages:
            pkg_list = " ".join(pip_packages)
            pip_install_cmd = f"pip install --quiet {pkg_list} && "

        # Unique per attempt: names shared across executions make concurrent runs (or a
        # container still alive from a timed-out run) fail with "name already in use"
        container_name = f"crisisgrid_{node_id}_{seed}_{uuid.uuid4().hex[:8]}"

        # Build docker run command
        cmd = self._build_docker_command(
            code_file=code_file,
            node_dir=node_dir,
            output_dir=output_dir,
            seed=seed,
            config=cfg,
            upstream_outputs_dir=upstream_outputs_dir,
            pip_install_cmd=pip_install_cmd,
            container_name=container_name,
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
                cwd=str(self._work_dir),
            )

            completed_at = datetime.now(timezone.utc).isoformat()
            runtime = self._calc_runtime(started_at, completed_at)

            # Collect metrics if the script wrote them
            metrics: dict[str, float] = {}
            metrics_path = node_dir / "metrics.json"
            if metrics_path.exists():
                try:
                    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Collect output files
            output_files = [str(f) for f in output_dir.iterdir()] if output_dir.exists() else []

            if result.returncode == 0:
                status = RunStatus.completed
                failure_reason = FailureReason.none
                failure_detail = None
            elif result.returncode == 137:
                # SIGKILL — typically OOM killer
                status = RunStatus.resource_exhausted
                failure_reason = FailureReason.oom
                failure_detail = "Container killed (exit 137) — likely OOM"
            elif result.returncode == 125:
                # `docker run` itself failed (name conflict, bad mount, daemon error); the code never ran
                docker_error = next(
                    (line.strip() for line in (result.stderr or "").splitlines() if line.strip().startswith("docker:")),
                    (result.stderr or "").strip()[:300],
                )
                status = RunStatus.failed
                failure_reason = FailureReason.invalid_configuration
                failure_detail = f"Docker refused to start the container (exit 125): {docker_error}"
            else:
                status = RunStatus.failed
                failure_reason = FailureReason.container_crash
                failure_detail = f"Exit code {result.returncode}"

            return NodeRunResult(
                node_id=node_id,
                status=status,
                failure_reason=failure_reason,
                failure_detail=failure_detail,
                started_at=started_at,
                completed_at=completed_at,
                runtime_seconds=runtime,
                stdout=result.stdout[-10000:] if result.stdout else "",
                stderr=result.stderr[-10000:] if result.stderr else "",
                exit_code=result.returncode,
                output_files=output_files,
                metrics=metrics,
            )

        except subprocess.TimeoutExpired:
            completed_at = datetime.now(timezone.utc).isoformat()
            runtime = self._calc_runtime(started_at, completed_at)
            # Force kill the container
            self._kill_container(container_name)
            return NodeRunResult(
                node_id=node_id,
                status=RunStatus.timed_out,
                failure_reason=FailureReason.timeout,
                failure_detail=f"Exceeded timeout of {cfg.timeout_seconds}s",
                started_at=started_at,
                completed_at=completed_at,
                runtime_seconds=runtime,
                exit_code=-1,
            )

        except FileNotFoundError:
            completed_at = datetime.now(timezone.utc).isoformat()
            return NodeRunResult(
                node_id=node_id,
                status=RunStatus.failed,
                failure_reason=FailureReason.invalid_configuration,
                failure_detail="Docker not found on system PATH",
                started_at=started_at,
                completed_at=completed_at,
                runtime_seconds=0.0,
                exit_code=-1,
            )

        except Exception as exc:
            completed_at = datetime.now(timezone.utc).isoformat()
            runtime = self._calc_runtime(started_at, completed_at)
            return NodeRunResult(
                node_id=node_id,
                status=RunStatus.failed,
                failure_reason=FailureReason.unknown,
                failure_detail=str(exc),
                started_at=started_at,
                completed_at=completed_at,
                runtime_seconds=runtime,
                exit_code=-1,
            )

    # ------------------------------------------------------------------
    # Docker command building
    # ------------------------------------------------------------------
    def _build_docker_command(
        self,
        code_file: Path,
        node_dir: Path,
        output_dir: Path,
        seed: int,
        config: NodeExecutionConfig,
        upstream_outputs_dir: Path | None = None,
        pip_install_cmd: str = "",
        container_name: str | None = None,
    ) -> list[str]:
        container_name = container_name or f"crisisgrid_{config.node_id}_{seed}_{uuid.uuid4().hex[:8]}"
        node_dir_abs = Path(node_dir).resolve()
        output_dir_abs = Path(output_dir).resolve()
        network_mode = "bridge" if pip_install_cmd else "none"

        cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            f"--memory={config.memory_limit_mb}m",
            f"--cpus={config.cpu_limit}",
            f"--network={network_mode}",
            "-e", f"PYTHONHASHSEED={seed}",
            "-e", f"CRISISGRID_SEED={seed}",
            "-v", f"{node_dir_abs}:/workspace",
            "-v", f"{output_dir_abs}:/workspace/output",
            # Generated code conventionally downloads to ./data; back it with the shared cache
            "-v", f"{self._shared_cache_dir / 'data'}:/workspace/data",
            "-v", f"{self._shared_cache_dir}:/cache",
            "-e", "TORCH_HOME=/cache/torch",
            "-e", "HF_HOME=/cache/huggingface",
            "-e", "PIP_CACHE_DIR=/cache/pip",
            "-w", "/workspace",
        ]

        # Mount upstream outputs if available (always resolve to absolute path)
        if upstream_outputs_dir and Path(upstream_outputs_dir).exists():
            cmd.extend(["-v", f"{Path(upstream_outputs_dir).resolve()}:/workspace/upstream:ro"])

        # Inject node-level environment
        for k, v in config.environment.items():
            cmd.extend(["-e", f"{k}={v}"])

        cmd.append(self._docker_image)
        cmd.extend(["bash", "-c", f"{pip_install_cmd}python /workspace/run.py"])

        return cmd

    def _kill_container(self, container_name: str) -> None:
        """Force-kill a timed-out container."""
        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Runner script generation
    # ------------------------------------------------------------------
    @staticmethod
    def _build_runner_script(
        code: str,
        seed: int,
        parameters: dict[str, Any],
        metrics_filename: str = "metrics.json",
        upstream_code: str | None = None,
    ) -> str:
        """Wrap user code with deterministic seed setup, device definition, and metrics capture."""
        lines = [
            "import os, sys, json, random",
            "",
            "# === CrisisGrid seed & device injection (deterministic harness) ===",
            f"SEED = {seed}",
            f"seed = {seed}",
            "os.environ['PYTHONHASHSEED'] = str(SEED)",
            "random.seed(SEED)",
            "",
            "try:",
            "    import numpy as np",
            "    np.random.seed(SEED)",
            "except ImportError:",
            "    pass",
            "",
            "try:",
            "    import torch",
            "    torch.manual_seed(SEED)",
            "    if torch.cuda.is_available():",
            "        torch.cuda.manual_seed_all(SEED)",
            "        torch.backends.cudnn.deterministic = True",
            "        torch.backends.cudnn.benchmark = False",
            "    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')",
            "    DEVICE = device",
            "except ImportError:",
            "    device = 'cpu'",
            "    DEVICE = 'cpu'",
            "",
            "try:",
            "    import tensorflow as tf",
            "    tf.random.set_seed(SEED)",
            "except ImportError:",
            "    pass",
            "",
            "# === Parameters ===",
        ]

        # Inject parameters as variables
        valid_keys = set()
        for k, v in parameters.items():
            # Skip non-identifiers and metadata keys
            if not isinstance(k, str) or not k.isidentifier() or k.endswith("_source") or k.endswith("_is_assumed") or k.startswith("seed_audit"):
                continue
            valid_keys.add(k)
            lines.append(f"{k} = {repr(v)}")

        # Fallback defaults for common ML hyperparameters if referenced in code but missing from parameters
        combined_code = f"{upstream_code or ''}\n{code}"
        standard_fallbacks = {
            "seed": seed,
            "batch_size": 64,
            "learning_rate": 0.001,
            "epochs": 10,
        }
        for var_name, default_val in standard_fallbacks.items():
            if var_name not in valid_keys and re.search(r"\b" + re.escape(var_name) + r"\b", combined_code):
                lines.append(f"{var_name} = {repr(default_val)}")

        lines.extend([
            "",
            "# === Metrics collection helper ===",
            "crisisgrid_metrics = {}",
            "",
            "def report_metric(name, value):",
            "    crisisgrid_metrics[name] = float(value)",
        ])

        # Prepend upstream code context if provided
        if upstream_code and upstream_code.strip():
            lines.extend([
                "",
                "# === Upstream Chained Execution Context ===",
                upstream_code.strip(),
                "",
            ])

        lines.extend([
            "",
            "# === User code ===",
            code,
            "",
            "# === Save metrics ===",
            "# Auto-capture numeric entries of an `eval_results` dict if the code did not report them explicitly",
            "if isinstance(globals().get('eval_results'), dict):",
            "    for _k, _v in globals()['eval_results'].items():",
            "        if isinstance(_v, (int, float)) and not isinstance(_v, bool) and _k not in crisisgrid_metrics:",
            "            crisisgrid_metrics[_k] = float(_v)",
            "try:",
            f"    with open('/workspace/{metrics_filename}', 'w') as _mf:",
            "        json.dump(crisisgrid_metrics, _mf)",
            "except Exception:",
            "    pass",
        ])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_runtime(started: str, completed: str) -> float:
        try:
            t1 = datetime.fromisoformat(started)
            t2 = datetime.fromisoformat(completed)
            return (t2 - t1).total_seconds()
        except Exception:
            return 0.0
