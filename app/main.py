"""FastAPI entrypoint for the Launchpad Program Coach frontend + API.

Run from the project root:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.prompts import (
    CHAT_SYSTEM_PROMPT,
    ROADMAP_SYSTEM_PROMPT,
    build_chat_user_message,
    build_retrieval_query_for_chat,
    build_retrieval_query_from_intake,
    build_roadmap_user_message,
)
from app.rag import Chunk, embed_query, retrieve, slug_to_title

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
TEMPLATES_DIR = APP_DIR / "templates"
INDEX_HTML = TEMPLATES_DIR / "index.html"

CLAUDE_MODEL = "claude-sonnet-4-20250514"
RETRIEVAL_K = 10

logger = logging.getLogger("app.main")

ALLOWED_STATES = frozenset(
    {
        "California",
        "Florida",
        "Maryland",
        "New York",
        "North Carolina",
        "Texas",
        "Washington",
    }
)

app = FastAPI(title="Launchpad Program Coach")

app.mount(
    "/static",
    StaticFiles(directory=APP_DIR / "static"),
    name="static",
)


@app.on_event("startup")
def startup() -> None:
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "Missing OPENAI_API_KEY. Set it in your hosting environment (or .env)."
        )
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Missing ANTHROPIC_API_KEY. Set it in your hosting environment (or .env)."
        )

    chroma_path = ROOT / "chroma_db"
    if not chroma_path.exists():
        logger.warning(
            "No Chroma index at %s. Building from docs/ now (one-time, ~10-20s).",
            chroma_path,
        )
        from scripts.embed import main as build_index

        build_index()

    from app.rag import get_chroma_collection

    get_chroma_collection()


def get_anthropic() -> Anthropic:
    return Anthropic()


def parse_json_loose(text: str) -> dict[str, Any]:
    """Strip optional markdown fences and parse the outermost JSON object."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(s[start : end + 1])


def anthropic_first_text(message: Any) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


# --- Request / response models ------------------------------------------------


class Intake(BaseModel):
    state: str
    home_type: str | None = ""
    ages: str | None = ""
    stage: str | None = ""
    concern: str | None = ""


class RoadmapStep(BaseModel):
    name: str
    body: str
    source_url: str | None = None
    source_title: str | None = None


class RoadmapResponse(BaseModel):
    state: str
    steps: list[RoadmapStep]
    suggestions: list[str]


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    intake: Intake
    history: list[ChatTurn] = Field(default_factory=list)


class ChatCitation(BaseModel):
    source_url: str
    source_title: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation]


# --- Roadmap ----------------------------------------------------------------


def _validate_intake(intake: Intake) -> None:
    st = intake.state.strip()
    if not st or st not in ALLOWED_STATES:
        raise HTTPException(
            status_code=400,
            detail="Invalid or missing state. Choose one of the supported states.",
        )


def _resolve_step_citation(
    raw: dict[str, Any], chunks: list[Chunk]
) -> tuple[str | None, str | None]:
    si = raw.get("source_index")
    if si is None or si == "":
        return None, None
    try:
        idx = int(si)
    except (TypeError, ValueError):
        return None, None
    if idx < 1 or idx > len(chunks):
        return None, None
    ch = chunks[idx - 1]
    url = (ch.source_url or "").strip() or None
    title = slug_to_title(ch.filename) if ch.filename else "Wonderschool guide"
    return url, title


@app.post("/api/roadmap", response_model=RoadmapResponse)
async def api_roadmap(intake: Intake) -> RoadmapResponse:
    _validate_intake(intake)

    q_text = build_retrieval_query_from_intake(intake.model_dump())
    emb = embed_query(q_text)
    chunks = retrieve(emb, intake.state.strip(), k=RETRIEVAL_K)
    user_msg = build_roadmap_user_message(intake.model_dump(), chunks)

    client = get_anthropic()
    raw_text = ""
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            temperature=0.3,
            system=ROADMAP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw_text = anthropic_first_text(msg)
        data = parse_json_loose(raw_text)
    except Exception:
        logger.exception(
            "Roadmap generation failed (state=%s, raw_text_head=%r)",
            intake.state,
            raw_text[:300],
        )
        raise HTTPException(
            status_code=502,
            detail="We had trouble building your roadmap. Try again.",
        ) from None

    raw_steps = data.get("steps") or []
    raw_suggestions = data.get("suggestions") or []

    steps_out: list[RoadmapStep] = []
    for rs in raw_steps[:8]:
        if not isinstance(rs, dict):
            continue
        name = str(rs.get("name") or "").strip()
        body = str(rs.get("body") or "").strip()
        if not name or not body:
            continue
        url, title = _resolve_step_citation(rs, chunks)
        steps_out.append(
            RoadmapStep(name=name, body=body, source_url=url, source_title=title)
        )

    if len(steps_out) < 5:
        logger.error(
            "Roadmap returned only %d valid steps (state=%s, raw_steps=%d)",
            len(steps_out),
            intake.state,
            len(raw_steps),
        )
        raise HTTPException(
            status_code=502,
            detail="We had trouble building your roadmap. Try again.",
        )

    steps_out = steps_out[:6]

    sugg: list[str] = []
    for s in raw_suggestions:
        if isinstance(s, str) and (t := s.strip()):
            sugg.append(t)
    while len(sugg) < 3:
        sugg.append("What should I do first this week?")
    sugg = sugg[:3]

    return RoadmapResponse(
        state=intake.state.strip(),
        steps=steps_out,
        suggestions=sugg,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest) -> ChatResponse:
    _validate_intake(req.intake)
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question is required.")

    q_text = build_retrieval_query_for_chat(q, req.intake.model_dump())
    emb = embed_query(q_text)
    chunks = retrieve(emb, req.intake.state.strip(), k=RETRIEVAL_K)

    hist = [t.model_dump() for t in req.history]
    user_msg = build_chat_user_message(q, req.intake.model_dump(), hist, chunks)

    client = get_anthropic()
    raw_text = ""
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=900,
            temperature=0.3,
            system=CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw_text = anthropic_first_text(msg)
        data = parse_json_loose(raw_text)
    except Exception:
        logger.exception(
            "Chat generation failed (state=%s, raw_text_head=%r)",
            req.intake.state,
            raw_text[:300],
        )
        raise HTTPException(
            status_code=502,
            detail="We couldn't answer that right now. Try again.",
        ) from None

    answer = str(data.get("answer") or "").strip()
    if not answer:
        logger.error("Chat returned empty answer (state=%s)", req.intake.state)
        raise HTTPException(
            status_code=502,
            detail="We couldn't answer that right now. Try again.",
        )

    raw_cites = data.get("citation_indexes") or data.get("citations") or []
    citations: list[ChatCitation] = []
    seen: set[str] = set()

    if isinstance(raw_cites, list):
        for item in raw_cites:
            try:
                idx = int(item)
            except (TypeError, ValueError):
                continue
            if idx < 1 or idx > len(chunks):
                continue
            ch = chunks[idx - 1]
            url = (ch.source_url or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            citations.append(
                ChatCitation(
                    source_url=url,
                    source_title=slug_to_title(ch.filename),
                )
            )

    return ChatResponse(answer=answer, citations=citations)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(INDEX_HTML, media_type="text/html")
