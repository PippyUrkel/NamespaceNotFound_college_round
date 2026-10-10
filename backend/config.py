from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def _resolve_artifacts_dir() -> str:
    raw = os.getenv("ARTIFACTS_DIR", "")
    if raw:
        p = Path(raw)
        if p.is_absolute():
            return str(p)
        return str((Path(__file__).resolve().parent / p).resolve())
    return str((Path(__file__).resolve().parent / "data").resolve())


class Settings:
    app_name: str = "CrisisGrid"
    project_root: str = str(Path(__file__).resolve().parent)
    artifacts_dir: str = _resolve_artifacts_dir()
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_index: str = os.getenv("PINECONE_INDEX", "bnb")
    pinecone_cloud: str = os.getenv("PINECONE_CLOUD", "aws")
    pinecone_region: str = os.getenv("PINECONE_REGION", "us-east-1")


settings = Settings()
