# Decisions

A running log of meaningful product, content, and technical decisions for Launchpad Program Coach. Newest entries go at the top.

---

## 2026-05-01 — Roadmap + chat LLM output is JSON-only with permissive parsing (no Anthropic tool-use)

**Decision:** `/api/roadmap` and `/api/chat` ask Claude (`claude-sonnet-4-20250514`) for a single JSON object in plain text — no Anthropic tool-use / structured-output API. The server strips optional Markdown code fences (e.g. a leading `json`-labeled fence), falls back to parsing the outermost `{...}` substring if there's stray preamble, then `json.loads`. If parsing fails or fewer than five valid steps come back, the API returns HTTP 502 with a friendly retry message.

**Reasoning:** Sonnet 4 is a reliable instruction-follower for "JSON only, no preamble" when the schema is printed in the system prompt. Tool-use would add a second round-trip (tool spec + tool_result handling) and more branching for a demo where speed of iteration matters more than squeezing out the last 1% of parse reliability. The permissive parser covers the occasional fence or leading sentence without changing the model contract.

---

## 2026-05-01 — Retrieval filters Chroma metadata to `state in [user_state, "general"]`

**Decision:** Both roadmap and chat retrieval call `collection.query(..., where={"state": {"$in": [user_state, "general"]}})` so chunks tagged with another US state never enter the context window for a different state's user.

**Reasoning:** During embedding, each chunk was tagged with the first US state name appearing in its text, or `general` if none. That metadata exists precisely to prevent cross-state contamination at query time — e.g. a Texas outdoor-space chunk outranking a New York article for a New York user because of shared generic words. Allowing `general` still lets through excerpts whose text never mentions a state name but whose licensing guidance still applies broadly.

---

## 2026-05-01 — State dropdown is limited to states the corpus actually covers

**Decision:** The intake's "What state are you in?" dropdown only offers the seven states for which the Wonderschool corpus has real licensing content: California, Florida, Maryland, New York, North Carolina, Texas, and Washington (alphabetical in the UI). All other US states are intentionally not selectable.

**Reasoning:** The roadmap quality is bounded by what the corpus contains. If a user picks Ohio or Georgia, the Chroma collection has no Ohio/Georgia chunks, so the LLM either refuses (correct) or freelances state-specific facts it can't ground (wrong). Letting the user pick those states would be a setup for the model to fail in exactly the way "DECISIONS — Wonderschool-only RAG" was designed to prevent. Better to make the supported set obvious in the UI than to let the user fall into a thin-coverage state and blame the app. Coverage tiers (high: CA, TX; medium: FL, NY, WA; lower: MD, NC) are documented; if the corpus expands, the dropdown expands with it.

---

## 2026-05-01 — Frontend stack: FastAPI + Jinja templates + vanilla CSS/JS

**Decision:** Build the `app/` frontend as a FastAPI application that renders Jinja2 templates and serves a small amount of vanilla CSS + JS, run via `uvicorn`. No React/Next.js, no Streamlit.

**Reasoning:** The retrieval and LLM layers are already pure Python (OpenAI + Chroma + Anthropic clients), so a Python web framework keeps everything in one process and one language. FastAPI specifically (over Flask) gives us free JSON schema validation for the `/api/roadmap` and `/api/chat` endpoints. Streamlit was tempting for speed but fights against the custom CSS/animations the UX calls for (cascade animation on intake, slide-in chat, hand-drawn-style accents). Vanilla CSS + JS with no build step keeps the project clone-and-run.

---

## 2026-05-01 — Visual design references the "Welcome Back" screenshot palette + Plus Jakarta Sans

**Decision:** Use a warm cream / deep plum / coral / muted mustard palette and Plus Jakarta Sans for type, taking the colors, typography, and "warm and organic" feel from the user-provided reference screenshot but **not** its layout (no top-banner blob composition).

**Reasoning:** The reference has a calm, encouraging feel that matches the persona — someone overwhelmed by licensing complexity who needs a friendly starting point, not a clinical form. Concrete tokens: bg `#FBF5ED`, primary `#67293F`, coral `#E07A6F`, mustard `#D4B254`, text `#1A1A1A`, with Plus Jakarta Sans (Google Fonts, 400/500/600/700/800). Layout stays clean and centered with one subtle organic backdrop accent so the *feel* carries through without imitating the source layout.

---

## 2026-05-01 — Strip the trailing "Join Wonderschool Today / Related Content" footer from articles

**Decision:** During scraping, drop everything from the first occurrence of `Join Wonderschool Today` or `Related Content` (case-insensitive line match) to EOF.

**Reasoning:** This is the closing-side counterpart to the earlier "this post is a part of our series" decision. Every Wonderschool article ends with a fixed sitewide footer block — `Join Wonderschool Today / Sign Up / Related Content / [list of unrelated provider stories] / All Articles for Providers`. Because that block is identical across every article, leaving it in meant *every* doc contained keywords from every other doc (e.g. a West Virginia provider story was bleeding into the California licensing files). Confirmed across all 26 docs at audit time. Stripping it cleanly via line-match on the two heading triggers removes the footer without risking real article content (those exact strings don't appear as body text).

---

## 2026-05-01 — Business content is kept on disk in `docs/business/` but not indexed

**Decision:** Universal business topics (LLC vs sole prop, tuition pricing, zoning, securing space, earnings, costs) are scraped into `docs/business/` rather than `docs/`, and `embed.py` only globs `docs/*.txt` non-recursively, so they're excluded from the Chroma index.

**Reasoning:** This is the code-level enforcement of the earlier "business content via system prompt knowledge, not RAG" decision, which until now lived only in this doc — the files were sitting in `docs/` and being silently indexed alongside licensing content. Two folders + a non-recursive glob makes the rule mechanical: anything that should be retrievable lives at `docs/*.txt`; anything that's reference-only for the system prompt or for humans lives at `docs/business/`. `scrape.py` now has a separate `BUSINESS_URLS` list that writes to `docs/business/`, so the corpus is fully reproducible from the scraper.

---

## 2026-05-01 — User persona is aspiring (not existing) provider

**Decision:** The target user is someone who has *not yet* started a licensed home daycare — they're considering it, exploring it, or just-barely getting started.

**Reasoning:** This is the highest-value moment in Wonderschool's funnel. Existing providers already know the licensing rules and have other tools. The aspiring provider is the one who is most likely to bounce off the process entirely; helping them past the first wall both serves them and grows Wonderschool's supply side.

---

## 2026-05-01 — RAG source is Wonderschool's own blog only

**Decision:** The knowledge base is built exclusively from articles on `wonderschool.com/blog/child-care-provider-resources/` (with a couple of CMS-hosted equivalents).

**Reasoning:** Mixing Wonderschool's summaries with primary government sources creates conflicts (e.g. a state agency PDF and a Wonderschool article describing the same rule with different wording or out-of-date numbers). Limiting the corpus to Wonderschool keeps the answers consistent with Wonderschool's voice and reduces the chance of the LLM stitching together contradictory facts.

---

## 2026-05-01 — ChromaDB used locally, persisted to disk

**Decision:** Vectors live in a local `chroma_db/` directory via `chromadb.PersistentClient`. No hosted vector DB.

**Reasoning:** Simple. No infrastructure to provision for a demo, no auth to manage, no cost surprises, and the entire knowledge base fits comfortably on disk. If this ever needed to scale beyond a demo it would be straightforward to swap the client.

---

## 2026-05-01 — Government sources excluded from the corpus

**Decision:** State licensing PDFs, agency websites, and similar primary sources are deliberately *not* indexed.

**Reasoning:** When the same rule shows up in both a government source and a Wonderschool article, the two often disagree slightly (different effective dates, different rounding of fees, different phrasing of capacity rules). Including both raises the risk that retrieval surfaces the conflicting pair to the LLM, which then has to pick — and any pick can be wrong. Wonderschool's summaries are the canonical voice for this app.

---

## 2026-05-01 — Strip the "this post is a part of our series" intro nav from articles

**Decision:** During scraping, drop the line containing "this post is a part of our series" along with the short title-link list that follows it.

**Reasoning:** That block is a sibling-article nav menu, not article content. It's short, dense with state-name keywords, and was polluting rank-1 retrieval results — chunks that were *just* a list of related article titles were beating real content on similarity scores because they matched the query's keywords without containing any actual answer. Removing it noticeably improved top-K quality.

---

## 2026-05-01 — LLM is Claude (`claude-sonnet-4-20250514`) via the Anthropic API

**Decision:** Use Anthropic's Claude Sonnet 4 for roadmap generation and chat.

**Reasoning:** The hard requirement here is *staying inside the retrieved context* — the app should not invent state-specific licensing facts that weren't in the chunks it was given. In practice Claude has been the most reliable instruction-follower for "answer only from the provided context, and cite which source you used." That discipline matters more for this app than raw model size.

---

## 2026-05-01 — Business content (LLC, pricing, zoning) handled via system prompt knowledge, not RAG

**Decision:** Universal business topics — should I form an LLC, how to think about pricing, zoning basics — are handled by the LLM's general knowledge guided by the system prompt, *not* by retrieving from the indexed Wonderschool business articles.

**Reasoning:** These topics aren't state-specific in a way that benefits from retrieval, and the same Wonderschool article on LLCs applies to a user in California or Texas equally. Forcing them through RAG meant retrieval sometimes pulled an irrelevant state-licensing chunk just because it shared a few keywords, which made answers worse, not better. State-specific licensing content (capacity rules, training hours, square footage, fees) still goes through RAG; general business content does not. This narrows the surface area where hallucination is possible because the LLM is only being asked to "freelance" on widely-known, non-jurisdictional topics.

---

> **Instruction for Cursor:** When you make any meaningful technical or UX decision while working on this project, append it to this file with today's date before moving on.
