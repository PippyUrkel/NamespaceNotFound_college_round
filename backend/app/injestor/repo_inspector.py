from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from git import Repo


class RepositoryInspector:
    @staticmethod
    def validate_url(repo_url: str) -> str:
        parsed = urlparse(repo_url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Repository URL must use http or https.")
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            raise ValueError("Only public GitHub repositories are supported.")
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            raise ValueError("Repository URL must include owner and repo name.")
        repo_name = parts[1].removesuffix(".git")
        if not repo_name:
            raise ValueError("Repository name is missing.")
        return f"https://github.com/{parts[0]}/{repo_name}"

    @staticmethod
    def inspect(repo_url: str, branch: str | None = None, commit_ref: str | None = None) -> dict:
        validated = RepositoryInspector.validate_url(repo_url)
        with TemporaryDirectory(prefix="crisisgrid_repo_") as tmp_dir:
            repo_dir = Path(tmp_dir) / "repo"
            clone_kwargs = {"depth": 1}
            if branch:
                clone_kwargs["branch"] = branch
            Repo.clone_from(validated, repo_dir, **clone_kwargs)
            repo = Repo(repo_dir)
            if commit_ref:
                repo.git.checkout(commit_ref)
            commit_sha = repo.head.commit.hexsha
            repo.close()
            readme_text = ""
            candidate_files = [
                "README.md",
                "README",
                "requirements.txt",
                "pyproject.toml",
                "setup.py",
                "environment.yml",
                "Dockerfile",
                "train.py",
                "main.py",
            ]
            files = {}
            evidence = []
            dependencies = []
            for rel in candidate_files:
                target = repo_dir / rel
                if not target.exists():
                    continue
                text = target.read_text(encoding="utf-8", errors="ignore")
                files[rel] = text
                if rel.endswith(".txt") or rel.endswith(".toml") or rel in {"environment.yml", "Dockerfile"}:
                    dependencies.extend(re.findall(r"^[A-Za-z0-9_.\-]+", text, flags=re.MULTILINE))
                if rel == "README.md" or rel == "README":
                    readme_text = text[:1500]
                evidence.append({
                    "source": "repository",
                    "file_path": rel,
                    "exact_text": text[:200],
                })
            return {
                "repository_url": validated,
                "branch": branch or repo.active_branch.name,
                "commit_sha": commit_sha,
                "readme": readme_text,
                "files": files,
                "dependencies": sorted(set(dependencies)),
                "evidence": evidence,
            }
