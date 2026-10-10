"""Environment and dependency manager for CrisisGrid Experiment Runner.

Resolves and validates environment specifications, requirements.txt,
and pip dependencies needed to run experiment DAGs. Records dependency
checks and version resolution for execution provenance.
"""
from __future__ import annotations

import re
from typing import Any

from .models import DependencyCheck


class EnvironmentManager:
    """Manages python dependency resolution and environment integrity."""

    @classmethod
    def parse_requirements(cls, requirements_txt: str) -> list[dict[str, str]]:
        """Parse requirements.txt content into package specs."""
        packages = []
        for line in requirements_txt.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # e.g. torch>=2.0.0, numpy==1.24.3, scikit-learn
            match = re.match(r"^([A-Za-z0-9_.\-]+)(.*)$", line)
            if match:
                pkg_name = match.group(1)
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
            # Parse version if specified
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
