"""System prompts and user-message builders for roadmap + chat."""

from __future__ import annotations

from typing import Any

from app.rag import Chunk

ROADMAP_SYSTEM_PROMPT = """You are Launchpad, a calm, encouraging coach helping someone start a licensed home daycare in the United States.

You will receive (1) the user's short intake answers and (2) numbered excerpts from Wonderschool's own blog articles about child care licensing and related topics.

Rules — follow strictly:
- State-specific facts (agency names, fees, capacity limits, square footage, training hours, timelines, forms) MUST only appear if they are supported by the numbered excerpts. If the excerpts do not contain a specific fact, speak in general terms or say "check your state's licensing office" — never invent numbers or rules for a state.
- Universal business topics (LLC vs sole proprietorship, pricing mindset, zoning basics, marketing to families) MAY use your general knowledge. For those steps, set "source_index" to null (no citation).
- Produce exactly 5 or 6 steps. Each step must have a short, verb-led name (action-oriented) and a body of 1–3 sentences.
- Personalize ordering and emphasis using the user's intake (especially their biggest concern and where they are in the process). Steps should feel like a roadmap, not a generic article summary.
- When you cite licensing content from the excerpts, set "source_index" to the excerpt number (1-based) that best supports that step. One primary citation per step is enough; pick the single best excerpt.
- Also produce exactly 3 short "suggested follow-up questions" (strings) the user might ask next, grounded in the roadmap you just wrote.

Output format — CRITICAL:
- Respond with a single JSON object only. No markdown, no code fences, no text before or after the JSON.
- Schema:
{"steps":[{"name":"string","body":"string","source_index":1}],"suggestions":["string","string","string"]}
- "source_index" is either a positive integer matching an excerpt number, or null for general-knowledge-only steps.
"""

CHAT_SYSTEM_PROMPT = """You are Launchpad, continuing to help someone who is starting a licensed home daycare.

You will receive the user's original intake, recent chat history, their new question, and numbered excerpts from Wonderschool's blog (same licensing corpus as before).

Rules:
- Answer in 1–3 short paragraphs (plain text in the "answer" field — no markdown).
- State-specific licensing facts MUST only come from the numbered excerpts. If the excerpts don't cover the question, say honestly that the guides you have don't spell that out and point them to their state licensing office — do not invent specifics.
- Universal business topics may use general knowledge without a citation (omit that index from "citation_indexes").
- Stay on topic: licensed home daycare, licensing, and closely related business/setup questions. If asked something unrelated, politely decline in one sentence.
- At the end, list which excerpt numbers (1-based) you relied on for any state-specific claims in "citation_indexes". If none, use an empty array.

Output format — CRITICAL:
- Respond with a single JSON object only. No markdown, no code fences, no text before or after the JSON.
- Schema: {"answer":"string","citation_indexes":[1,2]}
"""


def _fmt_intake_line(label: str, value: str, mapping: dict[str, str]) -> str:
    v = (value or "").strip()
    if not v:
        return f"- {label}: (no preference)"
    return f"- {label}: {mapping.get(v, v)}"


_HOME: dict[str, str] = {
    "apartment": "Apartment",
    "condo": "Condo",
    "single_family": "Single family home",
    "other": "Other",
}
_AGES: dict[str, str] = {
    "infants": "Infants",
    "toddlers": "Toddlers",
    "preschool": "Preschool",
    "mixed": "Mixed ages",
}
_STAGE: dict[str, str] = {
    "exploring": "Just exploring",
    "ready": "Ready to start",
    "started": "Already started",
}
_CONCERN: dict[str, str] = {
    "licensing": "Licensing",
    "money": "Money / finances",
    "finding_families": "Finding families",
    "space": "Setting up my space",
    "all": "All of it / overwhelmed",
}


def build_intake_block(intake: dict[str, Any]) -> str:
    state = (intake.get("state") or "").strip() or "(unknown)"
    lines = [
        "User intake:",
        f"- State: {state}",
        _fmt_intake_line("Home type", str(intake.get("home_type") or ""), _HOME),
        _fmt_intake_line("Ages to serve", str(intake.get("ages") or ""), _AGES),
        _fmt_intake_line("Where they are in the process", str(intake.get("stage") or ""), _STAGE),
        _fmt_intake_line("Biggest concern", str(intake.get("concern") or ""), _CONCERN),
    ]
    return "\n".join(lines)


def build_roadmap_user_message(intake: dict[str, Any], chunks: list[Chunk]) -> str:
    intake_block = build_intake_block(intake)
    parts = [intake_block, "", "Numbered excerpts from Wonderschool (use these for state-specific licensing facts):"]
    for i, ch in enumerate(chunks, start=1):
        src = ch.source_url or "(unknown source)"
        parts.append(f"[{i}] (source: {src})\n{ch.document}")
    parts.append("")
    parts.append(
        "Now output ONLY the JSON object with 5–6 steps and exactly 3 suggestions, following the schema in your system instructions."
    )
    return "\n".join(parts)


def build_chat_user_message(
    question: str,
    intake: dict[str, Any],
    history: list[dict[str, str]],
    chunks: list[Chunk],
) -> str:
    intake_block = build_intake_block(intake)
    hist_lines: list[str] = []
    for turn in history[-12:]:
        role = turn.get("role", "")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        hist_lines.append(f"{role.upper()}: {content}")
    hist_block = "\n".join(hist_lines) if hist_lines else "(no prior messages)"

    parts = [
        intake_block,
        "",
        "Recent conversation:",
        hist_block,
        "",
        f"New question from the user:\n{question.strip()}",
        "",
        "Numbered excerpts from Wonderschool:",
    ]
    for i, ch in enumerate(chunks, start=1):
        src = ch.source_url or "(unknown source)"
        parts.append(f"[{i}] (source: {src})\n{ch.document}")
    parts.append("")
    parts.append(
        'Now output ONLY the JSON object with "answer" and "citation_indexes", following the schema in your system instructions.'
    )
    return "\n".join(parts)


def build_retrieval_query_from_intake(intake: dict[str, Any]) -> str:
    """Single string to embed for roadmap retrieval."""
    state = (intake.get("state") or "").strip()
    ht = _HOME.get(str(intake.get("home_type") or ""), "")
    ag = _AGES.get(str(intake.get("ages") or ""), "")
    st = _STAGE.get(str(intake.get("stage") or ""), "")
    co = _CONCERN.get(str(intake.get("concern") or ""), "")
    bits = [
        f"Licensed family child care home daycare in {state}.",
        "Licensing steps, training, home requirements, application process.",
    ]
    if ht:
        bits.append(f"Home type: {ht}.")
    if ag:
        bits.append(f"Ages: {ag}.")
    if st:
        bits.append(f"Stage: {st}.")
    if co:
        bits.append(f"Main concern: {co}.")
    return " ".join(bits)


def build_retrieval_query_for_chat(question: str, intake: dict[str, Any]) -> str:
    state = (intake.get("state") or "").strip()
    return f"{question.strip()} Context: licensed home daycare in {state}."
