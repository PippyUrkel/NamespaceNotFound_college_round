"""Dataset manager for CrisisGrid Experiment Runner.

Handles:
- Dataset location and preparation
- Download progress tracking with expected vs downloaded sizes
- Hash/integrity validation (SHA256, MD5)
- Structured error reporting when datasets are unavailable or corrupt
- Ensures datasets are never silently modified or truncated
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import DatasetCheck


class DatasetManager:
    """Manages dataset retrieval, integrity verification, and cache storage."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_file = self.storage_dir / "datasets_manifest.json"
        self._manifest: dict[str, dict[str, Any]] = self._load_manifest()

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if self.manifest_file.exists():
            try:
                return json.loads(self.manifest_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_manifest(self) -> None:
        self.manifest_file.write_text(
            json.dumps(self._manifest, indent=2),
            encoding="utf-8",
        )

    def prepare_dataset(
        self,
        name: str,
        url: str | None = None,
        expected_hash: str | None = None,
        hash_algo: str = "sha256",
        expected_size_bytes: int | None = None,
        progress_callback: Callable[[float, int, int], None] | None = None,
    ) -> DatasetCheck:
        """Prepare a dataset by checking local cache or downloading it with progress tracking.

        progress_callback receives (percent, downloaded_bytes, total_bytes).
        """
        dest_dir = self.storage_dir / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / "dataset.bin"

        check = DatasetCheck(
            name=name,
            url=url,
            available=False,
            expected_size_mb=(
                round(expected_size_bytes / (1024 * 1024), 2)
                if expected_size_bytes
                else None
            ),
        )

        # Check existing cached dataset
        if dest_file.exists():
            actual_size = dest_file.stat().st_size
            check.downloaded_size_mb = round(actual_size / (1024 * 1024), 2)

            if expected_size_bytes is not None and actual_size != expected_size_bytes:
                check.integrity_ok = False
                check.issue = (
                    f"Size mismatch: expected {expected_size_bytes} bytes, "
                    f"found {actual_size} bytes."
                )
                return check

            if expected_hash:
                computed = self._compute_hash(dest_file, hash_algo)
                if computed != expected_hash:
                    check.integrity_ok = False
                    check.issue = (
                        f"Integrity check failed: expected {hash_algo} {expected_hash}, "
                        f"got {computed}"
                    )
                    return check

            check.available = True
            check.integrity_ok = True
            return check

        # If no URL is provided and not present locally
        if not url:
            check.available = False
            check.issue = "Dataset not present in local cache and no download URL was provided."
            return check

        # Download with progress
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "CrisisGrid-DatasetManager/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = response.headers.get("Content-Length")
                total_bytes = int(total_size) if total_size else (expected_size_bytes or 0)
                downloaded_bytes = 0
                block_size = 64 * 1024

                hasher = hashlib.new(hash_algo) if expected_hash else None

                with open(dest_file, "wb") as f_out:
                    while True:
                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        if hasher:
                            hasher.update(chunk)
                        downloaded_bytes += len(chunk)

                        if progress_callback and total_bytes > 0:
                            pct = min(100.0, (downloaded_bytes / total_bytes) * 100)
                            progress_callback(pct, downloaded_bytes, total_bytes)

            check.downloaded_size_mb = round(downloaded_bytes / (1024 * 1024), 2)

            if expected_hash and hasher:
                computed_hash = hasher.hexdigest()
                if computed_hash != expected_hash:
                    check.integrity_ok = False
                    check.issue = (
                        f"Integrity check failed after download: expected {expected_hash}, "
                        f"got {computed_hash}"
                    )
                    dest_file.unlink(missing_ok=True)
                    return check

            check.available = True
            check.integrity_ok = True

            # Record in manifest
            self._manifest[name] = {
                "name": name,
                "url": url,
                "path": str(dest_file),
                "size_bytes": downloaded_bytes,
                "hash_algo": hash_algo,
                "hash": hasher.hexdigest() if hasher else None,
                "prepared_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_manifest()
            return check

        except Exception as exc:
            check.available = False
            check.issue = f"Failed to download dataset from {url}: {exc}"
            dest_file.unlink(missing_ok=True)
            return check

    @staticmethod
    def _compute_hash(path: Path, algo: str = "sha256") -> str:
        hasher = hashlib.new(algo)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
