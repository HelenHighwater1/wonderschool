# Architecture

## Folder Structure

```
wonderschool-coach/
├── app/                 # Frontend lives here (not yet built)
├── chroma_db/           # Persisted ChromaDB vector store (auto-generated)
├── docs/                # Scraped Wonderschool blog articles as .txt
│   ├── *.txt            # State-specific licensing articles — INDEXED into Chroma
│   ├── business/*.txt   # Universal business topics (LLC, pricing, zoning) — NOT INDEXED
│   └── failed_urls.txt  # URLs that failed to scrape, with reason
├── docs-project/        # Project documentation (this folder)
│   ├── PROJECT.md
│   ├── ARCHITECTURE.md
│   ├── UX.md
│   └── DECISIONS.md
├── scripts/             # Python pipeline + tooling
│   ├── scrape.py        # Fetch + clean Wonderschool blog articles → docs/
│   ├── embed.py         # Chunk docs/ → embed → write chroma_db/
│   ├── audit.py         # Quality-check the scraped .txt files
│   └── test_rag.py      # Smoke-test retrieval against the index
├── .env                 # API keys (gitignored)
├── .env.example         # Template for .env
└── requirements.txt     # Python dependencies
```

## RAG Pipeline

Data flows in one direction, with each step writing to disk so any stage can be re-run independently:

```
Wonderschool blog URLs
        │
        │  scripts/scrape.py
        ▼
   docs/*.txt           (clean article text + SOURCE/DATE_SCRAPED header)
        │
        │  scripts/embed.py
        ▼
   chroma_db/           (persistent vector store)
        │
        │  app/ (frontend, not yet built) → query → retrieved chunks → LLM
        ▼
     Roadmap
```

### 1. Scrape — `scripts/scrape.py`

- Maintains two URL lists: `LICENSING_URLS` (state-specific licensing guides → `docs/`) and `BUSINESS_URLS` (universal business topics → `docs/business/`).
- Extracts the main article element, strips nav/header/footer/aside/script/style/CTA/sidebar nodes.
- Removes known boilerplate phrases (e.g. "Find a child care program", "click here"), the **"this post is a part of our series"** intro block plus the title-link list that follows it, and the **trailing "Join Wonderschool Today / Related Content"** sibling-article footer block. See `DECISIONS.md` for why.
- Writes one `.txt` per URL into the appropriate folder, prefixed with a `SOURCE:` and `DATE_SCRAPED:` header.
- Failures (HTTP errors, too-short articles) are appended to `docs/failed_urls.txt` with a reason.

### 2. Embed — `scripts/embed.py`

- Reads each `docs/*.txt` at the top level only (non-recursive — the `business/` subfolder is intentionally skipped, and `failed_urls.txt` is filtered out), strips the header, and re-attaches the source URL as metadata.
- Chunks by sliding **sentence windows**: ~500 tokens per chunk with ~100-token overlap, breaking oversized sentences at clause boundaries when needed.
- Embeds each chunk via OpenAI.
- Tags each chunk with metadata: `source_url`, `filename`, `chunk_index`, and `state` (the first US state name appearing in the chunk, or `general` if none — used so retrieval can prefer state-specific chunks).
- Writes everything to a persistent ChromaDB collection at `chroma_db/`.

### 3. Retrieve + Generate — `app/` (FastAPI)

- `POST /api/roadmap` embeds a query string derived from the intake, queries `wonderschool_kb` with `where={"state": {"$in": [user_state, "general"]}}`, and passes the top-K chunks plus intake to Claude. The response is JSON parsed server-side into 5–6 steps with `source_url` / `source_title` resolved from chunk indices.
- `POST /api/chat` repeats the same embed + retrieve + Claude path for each follow-up, including recent chat history in the prompt.
- Shared logic lives in [app/rag.py](../app/rag.py) (OpenAI embed + Chroma query) and [app/prompts.py](../app/prompts.py) (system prompts + user message builders). The browser only calls these JSON endpoints; it does not talk to OpenAI or Chroma directly.

## ChromaDB

- **Collection name:** `wonderschool_kb`
- **Persisted at:** `/chroma_db` (project-relative)
- **Client:** `chromadb.PersistentClient`
- The collection is rebuilt from scratch on every `embed.py` run (delete + recreate), so it always reflects the current `docs/` directory.

## Models

- **Embedding model:** `text-embedding-3-small` via the OpenAI API. Used at indexing time (`embed.py`) and at query time in `app/rag.py` when serving `/api/*`.
- **LLM:** `claude-sonnet-4-20250514` via the Anthropic API. Used to synthesize the roadmap and answer chat follow-ups against the retrieved Wonderschool content. Choice rationale lives in `DECISIONS.md`.

## Environment Variables

Set in `.env` at the project root (see `.env.example`):

- `OPENAI_API_KEY` — required for embeddings (indexing + query time).
- `ANTHROPIC_API_KEY` — required for roadmap generation and chat.

Both keys are listed in `.env.example`. `scripts/embed.py` and `scripts/test_rag.py` both call `load_dotenv(root / ".env")` and bail out if `OPENAI_API_KEY` is missing.

## The `app/` Folder

The frontend — a FastAPI application that renders Jinja2 templates and serves vanilla CSS/JS. Run with `uvicorn app.main:app --reload` from the project root. The 5-screen flow described in `UX.md` is implemented as a single page with JS-driven screen transitions.

```
app/
├── main.py              # FastAPI: `/` static shell + `/api/roadmap` + `/api/chat`
├── rag.py               # embed_query, retrieve (state-filtered), slug_to_title
├── prompts.py           # system prompts + user message builders
├── templates/
│   └── index.html       # Single-page shell: welcome, intake, loading, roadmap + chat panel
└── static/
    ├── css/styles.css   # Design tokens + per-screen styles
    └── js/app.js        # Screen transitions, intake, fetch to `/api/*`, chat UI
```

On first request the app loads `.env`, verifies `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`, and opens the persisted `chroma_db/` collection the same way as `scripts/test_rag.py`.
