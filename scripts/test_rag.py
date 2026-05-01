#!/usr/bin/env python3
"""Smoke-test retrieval against the wonderschool_kb ChromaDB collection."""

from __future__ import annotations

import os
import re
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-small"
COLLECTION_NAME = "wonderschool_kb"
TOP_K = 3
PREVIEW_CHARS = 300

QUERIES: list[tuple[str, dict]] = [
    (
        "How many children can I care for with a small license in California?",
        {
            "expected_state": "California",
            "expected_keywords": ("california", "small", "license", "children", "capacity", "ratio"),
        },
    ),
    (
        "How much does it cost to apply for a child care license in Texas?",
        {
            "expected_state": "Texas",
            "expected_keywords": ("texas", "fee", "cost", "apply", "license", "$"),
        },
    ),
    (
        "How many hours of health and safety training do I need before I can open a licensed childcare in California?",
        {
            "expected_state": "California",
            "expected_keywords": ("california", "training", "health", "safety", "hour"),
        },
    ),
    (
        "How much outdoor space do I need for a licensed home daycare in Texas?",
        {
            "expected_state": "Texas",
            "expected_keywords": ("texas", "outdoor", "square", "feet", "sq", "space"),
        },
    ),
    (
        "Should I form an LLC for my home daycare?",
        {
            "expected_state": None,
            "expected_keywords": ("llc", "sole proprietor", "business", "entity", "structure"),
        },
    ),
]


BOILERPLATE_PATTERNS: tuple[str, ...] = (
    "find a child care program",
    "find child care",
    "click here",
    "if you're a provider, create a listing",
    "subscribe to our newsletter",
    "sign up for our newsletter",
    "cookie policy",
    "privacy policy",
    "all rights reserved",
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def looks_boilerplate(text: str) -> tuple[bool, list[str]]:
    low = text.lower()
    hits = [p for p in BOILERPLATE_PATTERNS if p in low]
    word_chars = sum(c.isalpha() for c in text)
    if word_chars and word_chars / max(len(text), 1) < 0.5:
        hits.append("low alphabetic ratio")
    return (len(hits) > 0), hits


def keyword_score(text: str, keywords: tuple[str, ...]) -> int:
    low = text.lower()
    return sum(1 for kw in keywords if kw and kw in low)


def main() -> None:
    root = project_root()
    load_dotenv(root / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "Missing OPENAI_API_KEY. Copy .env.example to .env and set your key."
        )

    chroma_path = root / "chroma_db"
    if not chroma_path.exists():
        raise SystemExit(
            f"No Chroma index at {chroma_path}. Run scripts/embed.py first."
        )

    client = chromadb.PersistentClient(path=str(chroma_path))
    coll = client.get_collection(COLLECTION_NAME)

    oai = OpenAI()

    all_query_texts = [q for q, _ in QUERIES]
    emb_resp = oai.embeddings.create(model=EMBED_MODEL, input=all_query_texts)
    by_idx = sorted(emb_resp.data, key=lambda d: d.index)
    query_embeddings = [d.embedding for d in by_idx]

    summary_rows: list[dict] = []

    for (qtext, meta), q_emb in zip(QUERIES, query_embeddings):
        res = coll.query(query_embeddings=[q_emb], n_results=TOP_K)
        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]

        print(f"Query: {qtext}")
        print("-" * 80)

        chunk_records = []
        for rank, (cid, doc, m) in enumerate(zip(ids, docs, metas), start=1):
            src = m.get("source_url", "")
            state = m.get("state", "general")
            preview = doc[:PREVIEW_CHARS].replace("\n", " ")
            preview = re.sub(r"\s+", " ", preview).strip()
            print(f"RANK: {rank}")
            print(f"SOURCE: {src}")
            print(f"STATE: {state}")
            print(f"CONTENT PREVIEW: {preview}")
            print()

            is_boiler, boiler_hits = looks_boilerplate(doc[:600])
            kw_hits = keyword_score(doc, meta["expected_keywords"])
            chunk_records.append(
                {
                    "rank": rank,
                    "id": cid,
                    "source": src,
                    "state": state,
                    "boilerplate": is_boiler,
                    "boiler_hits": boiler_hits,
                    "keyword_hits": kw_hits,
                }
            )

        summary_rows.append(
            {
                "query": qtext,
                "expected_state": meta["expected_state"],
                "expected_keywords": meta["expected_keywords"],
                "chunks": chunk_records,
            }
        )

        print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for i, row in enumerate(summary_rows, start=1):
        q = row["query"]
        exp_state = row["expected_state"]
        chunks = row["chunks"]
        states = [c["state"] for c in chunks]
        kw_hits_per_chunk = [c["keyword_hits"] for c in chunks]
        top = chunks[0] if chunks else None

        if exp_state is None:
            on_topic = any(
                c["keyword_hits"] >= 1 for c in chunks
            )
            state_ok = True
            top_state_ok = True
        else:
            state_ok = exp_state in states or any(s == "general" and c["keyword_hits"] >= 2 for s, c in zip(states, chunks))
            top_state_ok = (
                top is not None
                and (top["state"] == exp_state or top["keyword_hits"] >= 2)
            )
            on_topic = state_ok

        print(f"\nQ{i}: {q}")
        print(f"  Expected state/topic: {exp_state or 'general (LLC/business structure)'}")
        print(f"  Top-3 states: {states}")
        print(f"  Top-3 keyword hits: {kw_hits_per_chunk}")
        if exp_state and not on_topic:
            print(f"  [FLAG] No top-{TOP_K} chunk is from {exp_state} or strongly on-topic.")
        elif exp_state and not top_state_ok:
            print(
                f"  [FLAG] Top result is from state '{top['state']}' (expected {exp_state}); "
                f"may be from an unrelated article."
            )
        else:
            print("  Topic match: OK")

        if top is not None:
            top_filename = top["source"].rstrip("/").rsplit("/", 1)[-1]
            related_terms = []
            if exp_state:
                related_terms.append(exp_state.lower().replace(" ", "-"))
            related_terms.extend(row["expected_keywords"])
            top_blob = f"{top['source']} {top_filename}".lower()
            if exp_state and not any(t in top_blob for t in [exp_state.lower(), exp_state.lower().replace(" ", "-")]) \
                    and top["state"] != exp_state:
                print(
                    f"  [FLAG] Top result URL ({top_filename}) does not look related to {exp_state}."
                )

        for c in chunks:
            if c["boilerplate"]:
                print(
                    f"  [FLAG] Rank {c['rank']} chunk has boilerplate signals: {c['boiler_hits']}"
                )


if __name__ == "__main__":
    main()
