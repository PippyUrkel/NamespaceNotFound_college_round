from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from git import Repo


class RepositoryInspector:
    @staticmethod
    def validate_url(repo_url: str) -> str:
        if not repo_url or not isinstance(repo_url, str):
            raise ValueError("Repository URL must use http or https.")

        # Strip invisible zero-width chars and collapse excessive whitespace
        clean = re.sub(r"[\u200b\u200c\u200d\ufeff\u200e\u200f]", "", repo_url)
        clean = re.sub(r"[\xa0\s]+", " ", clean).strip()
        clean = clean.strip("`'\"<>[]{}() \t\n\r")
        clean = re.sub(r"[.,;:!?)'\"]+$", "", clean)

        # Handle SSH format like git@github.com:owner/repo(.git)
        ssh_match = re.match(
            r"^(?:ssh://)?git@([A-Za-z0-9_.-]+)[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$",
            clean,
        )
        if ssh_match:
            host, owner, repo = ssh_match.groups()
            return f"https://{host}/{owner}/{repo}"

        # Handle git:// or git+https:// schemes
        if clean.startswith(("git://", "git+https://", "git+http://")):
            clean = re.sub(r"^git(?:\+https?|\+ssh)?://", "https://", clean)

        # If scheme is missing, default to https://
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", clean):
            clean = f"https://{clean}"

        parsed = urlparse(clean)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("Repository URL must use http or https.")

        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname:
            raise ValueError("Repository URL must include a valid host.")

        # Handle GitHub Pages: <owner>.github.io/<repo>
        gh_pages = re.match(r"^([a-z0-9\-]+)\.github\.io$", hostname)
        if gh_pages:
            owner = gh_pages.group(1)
            path_parts = [p.strip() for p in parsed.path.split("/") if p.strip()]
            if not path_parts:
                raise ValueError("Repository URL must include owner and repo name.")
            repo_name = path_parts[0].removesuffix(".git")
            repo_name = re.sub(r"[.,;:!?)'\"]+$", "", repo_name)
            return f"https://github.com/{owner}/{repo_name}"

        allowed_hosts = {
            "github.com",
            "www.github.com",
            "gitlab.com",
            "www.gitlab.com",
            "bitbucket.org",
            "www.bitbucket.org",
            "huggingface.co",
            "www.huggingface.co",
            "codeberg.org",
            "www.codeberg.org",
        }
        if hostname not in allowed_hosts:
            raise ValueError("Only public Git repositories (e.g. GitHub, GitLab, Hugging Face, Bitbucket) are supported.")

        main_host = hostname.removeprefix("www.")
        parts = [p.strip() for p in parsed.path.split("/") if p.strip()]
        if len(parts) < 2:
            raise ValueError("Repository URL must include owner and repo name.")

        owner = parts[0]
        repo_name = parts[1].removesuffix(".git")
        repo_name = re.sub(r"[.,;:!?)'\"]+$", "", repo_name)
        if not repo_name:
            raise ValueError("Repository name is missing.")

        return f"https://{main_host}/{owner}/{repo_name}"

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
