#!/usr/bin/env python3
"""Build ChromaDB vector index from docs/*.txt using OpenAI embeddings."""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from pathlib import Path

import chromadb
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

TARGET_CHUNK_TOKENS = 500
OVERLAP_TOKENS = 100
EMBED_BATCH = 50
CHROMA_ADD_BATCH = 128
EMBED_MODEL = "text-embedding-3-small"
COLLECTION_NAME = "wonderschool_kb"
ENCODING_NAME = "cl100k_base"

# Longer names first for non-overlapping state detection (West Virginia vs Virginia).
US_STATE_NAMES: tuple[str, ...] = (
    "District of Columbia",
    "North Carolina",
    "North Dakota",
    "South Carolina",
    "South Dakota",
    "West Virginia",
    "New Hampshire",
    "Rhode Island",
    "Connecticut",
    "Pennsylvania",
    "Massachusetts",
    "Mississippi",
    "California",
    "Washington",
    "New Jersey",
    "New Mexico",
    "Tennessee",
    "Wisconsin",
    "Maryland",
    "Minnesota",
    "Louisiana",
    "Kentucky",
    "Michigan",
    "Missouri",
    "Nebraska",
    "Oklahoma",
    "Arkansas",
    "Colorado",
    "Delaware",
    "Illinois",
    "Indiana",
    "Kansas",
    "Montana",
    "Nevada",
    "New York",
    "Ohio",
    "Oregon",
    "Texas",
    "Utah",
    "Virginia",
    "Alabama",
    "Alaska",
    "Arizona",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Iowa",
    "Maine",
    "Wyoming",
    "Vermont",
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_doc_header(raw: str) -> tuple[str | None, str]:
    """Return (source_url, body) with SOURCE/DATE header removed."""
    lines = raw.splitlines()
    source_url: str | None = None
    i = 0
    if i < len(lines) and lines[i].startswith("SOURCE:"):
        source_url = lines[i].split(":", 1)[1].strip()
        i += 1
    if i < len(lines) and lines[i].startswith("DATE_SCRAPED:"):
        i += 1
    if i < len(lines) and lines[i].strip() == "":
        i += 1
    body = "\n".join(lines[i:]).strip()
    return source_url, body


def split_sentences(text: str) -> list[str]:
    parts = SENTENCE_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def token_len(enc: tiktoken.Encoding, text: str) -> int:
    return len(enc.encode(text))


def split_oversized_sentence(text: str, enc: tiktoken.Encoding, max_tokens: int) -> list[str]:
    """Break a single sentence over max_tokens at clause boundaries, else token windows."""
    if token_len(enc, text) <= max_tokens:
        return [text]
    for sep in ("; ", ";", ", ", "\n"):
        if sep in text:
            pieces = [p.strip() for p in text.split(sep) if p.strip()]
            if len(pieces) > 1:
                out: list[str] = []
                for p in pieces:
                    out.extend(split_oversized_sentence(p, enc, max_tokens))
                return out
    toks = enc.encode(text)
    out_chunks: list[str] = []
    step = max(1, max_tokens - 50)
    for i in range(0, len(toks), step):
        out_chunks.append(enc.decode(toks[i : i + max_tokens]))
    return out_chunks


def chunk_by_sentences(body: str, enc: tiktoken.Encoding) -> list[str]:
    """Sliding sentence windows: ~TARGET_CHUNK_TOKENS, OVERLAP_TOKENS overlap, sentence boundaries."""
    raw_sents = split_sentences(body)
    sentences: list[str] = []
    for s in raw_sents:
        sentences.extend(split_oversized_sentence(s, enc, TARGET_CHUNK_TOKENS))

    if not sentences:
        return []

    n = len(sentences)
    chunks: list[str] = []
    start = 0

    while start < n:
        total = 0
        end = start
        while end < n and total + token_len(enc, sentences[end]) <= TARGET_CHUNK_TOKENS:
            total += token_len(enc, sentences[end])
            end += 1
        if end == start:
            end = start + 1
        chunk_text = " ".join(sentences[start:end])
        chunks.append(chunk_text.strip())

        if end >= n:
            break

        back = end - 1
        ot = token_len(enc, sentences[back])
        while back > start and ot < OVERLAP_TOKENS:
            back -= 1
            ot += token_len(enc, sentences[back])
        next_start = back if ot >= OVERLAP_TOKENS else end
        if next_start <= start:
            next_start = end
        start = next_start

    return [c for c in chunks if c.strip()]


def first_state_in_chunk(text: str) -> str:
    """First US state by start position in text (longer names disambiguate); else general."""
    lower = text.lower()
    used: list[tuple[int, int]] = []
    hits: list[tuple[int, str]] = []
    for state in sorted(US_STATE_NAMES, key=len, reverse=True):
        pat = re.compile(r"\b" + re.escape(state.lower()) + r"\b")
        for m in pat.finditer(lower):
            s, e = m.span()
            if any(not (e <= us or s >= ue) for us, ue in used):
                continue
            used.append((s, e))
            hits.append((s, state))
    if not hits:
        return "general"
    hits.sort(key=lambda x: x[0])
    return hits[0][1]


def embed_batches(client: OpenAI, texts: list[str]) -> list[list[float]]:
    all_emb: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        by_idx = sorted(resp.data, key=lambda d: d.index)
        all_emb.extend([d.embedding for d in by_idx])
        if i + EMBED_BATCH < len(texts):
            time.sleep(0.2)
    return all_emb


def main() -> None:
    root = project_root()
    load_dotenv(root / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "Missing OPENAI_API_KEY. Copy .env.example to .env and set your key."
        )

    docs_dir = root / "docs"
    chroma_path = root / "chroma_db"

    enc = tiktoken.get_encoding(ENCODING_NAME)
    oai = OpenAI()

    txt_paths = sorted(
        p for p in docs_dir.glob("*.txt") if p.name != "failed_urls.txt"
    )
    if not txt_paths:
        raise SystemExit(f"No .txt files in {docs_dir}")

    all_ids: list[str] = []
    all_docs: list[str] = []
    all_meta: list[dict] = []
    doc_chunk_counts: list[int] = []

    for path in txt_paths:
        raw = path.read_text(encoding="utf-8", errors="replace")
        source_url, body = parse_doc_header(raw)
        if not body:
            doc_chunk_counts.append(0)
            continue
        url_meta = source_url or ""
        chunks = chunk_by_sentences(body, enc)
        doc_chunk_counts.append(len(chunks))
        for ci, chunk in enumerate(chunks):
            all_ids.append(f"{path.name}::{ci}")
            all_docs.append(chunk)
            all_meta.append(
                {
                    "source_url": url_meta,
                    "filename": path.name,
                    "chunk_index": ci,
                    "state": first_state_in_chunk(chunk),
                }
            )

    if not all_docs:
        raise SystemExit("No chunks produced from documents.")

    embeddings = embed_batches(oai, all_docs)

    client = chromadb.PersistentClient(path=str(chroma_path))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    coll = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"embedding_model": EMBED_MODEL},
    )
    for i in range(0, len(all_ids), CHROMA_ADD_BATCH):
        j = i + CHROMA_ADD_BATCH
        coll.add(
            ids=all_ids[i:j],
            embeddings=embeddings[i:j],
            documents=all_docs[i:j],
            metadatas=all_meta[i:j],
        )

    n_docs = len(txt_paths)
    n_chunks = len(all_docs)
    avg_chunks = n_chunks / n_docs if n_docs else 0.0
    state_counts = Counter(m["state"] for m in all_meta)

    print(f"Total documents processed: {n_docs}")
    print(f"Total chunks created: {n_chunks}")
    print(f"Average chunks per document: {avg_chunks:.2f}")
    print("Breakdown of chunks by state:")
    for state, cnt in state_counts.most_common():
        print(f"  {state}: {cnt}")


if __name__ == "__main__":
    main()
