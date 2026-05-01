"""RAG helpers: embed queries and retrieve from the local Chroma index."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-small"
COLLECTION_NAME = "wonderschool_kb"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_env() -> None:
    load_dotenv(project_root() / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "Missing OPENAI_API_KEY. Copy .env.example to .env and set your key."
        )


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    _ensure_env()
    return OpenAI()


@lru_cache(maxsize=1)
def get_chroma_collection():
    _ensure_env()
    chroma_path = project_root() / "chroma_db"
    if not chroma_path.exists():
        raise RuntimeError(
            f"No Chroma index at {chroma_path}. Run scripts/embed.py from the project root."
        )
    client = chromadb.PersistentClient(path=str(chroma_path))
    return client.get_collection(COLLECTION_NAME)


@dataclass(frozen=True)
class Chunk:
    document: str
    source_url: str
    filename: str
    state: str
    chunk_index: int


def embed_query(text: str) -> list[float]:
    oai = get_openai_client()
    resp = oai.embeddings.create(model=EMBED_MODEL, input=[text])
    by_idx = sorted(resp.data, key=lambda d: d.index)
    return by_idx[0].embedding


def retrieve(
    query_embedding: list[float],
    state: str,
    k: int = 10,
) -> list[Chunk]:
    """Return top-k chunks where metadata state is the user's state or general."""
    coll = get_chroma_collection()
    res = coll.query(
        query_embeddings=[query_embedding],
        n_results=k,
        where={"state": {"$in": [state, "general"]}},
    )
    ids = res["ids"][0]
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    out: list[Chunk] = []
    for _cid, doc, meta in zip(ids, docs, metas):
        if meta is None:
            meta = {}
        out.append(
            Chunk(
                document=doc or "",
                source_url=str(meta.get("source_url") or ""),
                filename=str(meta.get("filename") or ""),
                state=str(meta.get("state") or "general"),
                chunk_index=int(meta.get("chunk_index") or 0),
            )
        )
    return out


def slug_to_title(filename: str) -> str:
    """Turn 'family-child-care-licensing-in-california.txt' into a title-like string."""
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    base = base.replace("-", " ").replace("_", " ")
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        return "Wonderschool guide"
    return base[:1].upper() + base[1:]
