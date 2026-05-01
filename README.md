# Launchpad Program Coach

A small RAG app that turns five intake questions into a personalized roadmap for opening a home-based child care program, then lets the user ask follow-up questions. Content is grounded in scraped Wonderschool licensing guides via a local Chroma vector index, with Anthropic Claude generating the roadmap and chat answers.

## Stack

- **Backend / API:** FastAPI + uvicorn
- **Retrieval:** ChromaDB (persistent), OpenAI `text-embedding-3-small`
- **Generation:** Anthropic Claude Sonnet 4
- **Frontend:** Single HTML page + vanilla CSS/JS, served by FastAPI

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set:
#   OPENAI_API_KEY=...
#   ANTHROPIC_API_KEY=...

# (Optional) build the vector index ahead of time. The server will also
# build it automatically on first start if chroma_db/ is missing.
python scripts/embed.py

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000`.

## Project layout

```
app/
  main.py        FastAPI: /, /healthz, /api/roadmap, /api/chat
  rag.py         embed_query, retrieve (state-filtered), slug_to_title
  prompts.py     System prompts + user-message builders
  templates/
    index.html   Single-page shell (welcome, intake, loading, roadmap, chat)
  static/        css/styles.css, js/app.js
docs/            Scraped + cleaned licensing articles (RAG corpus)
docs/business/   Business articles, NOT indexed
scripts/
  scrape.py      Scrape Wonderschool blog posts into docs/
  embed.py       Chunk docs, embed with OpenAI, write chroma_db/
  audit.py       Sanity checks on the scraped text
  test_rag.py    Smoke test for retrieval
chroma_db/       Generated vector store (gitignored)
docs-project/    Architecture / decisions / UX notes
```

## Deploy to Railway

The app is configured to deploy on Railway with **no volume**. On first start, the server builds `chroma_db/` from `docs/*.txt` (~10-20 seconds, a few cents of OpenAI embedding usage). Subsequent restarts also rebuild — that's fine because the corpus is small. If you want to avoid rebuilds, mount a Railway Volume at `chroma_db/`.

### One-time setup

1. Push this repo to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo**, pick this repo.
3. Add environment variables in the service's **Variables** tab:
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
4. Under **Settings → Networking**, click **Generate Domain** to get a public URL.

Railway auto-detects Python from `requirements.txt`, runs the start command in `Procfile` / `railway.json`, and uses `/healthz` as the healthcheck.

### Files that drive the deploy

- `Procfile` — `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `railway.json` — Nixpacks build, `/healthz` healthcheck, restart policy
- `.python-version` — pins Python to 3.12
- `requirements.txt` — pip dependencies

### Optional: persistent vector store

If you'd rather embed once and keep the index across deploys, add a Railway **Volume** mounted at `/app/chroma_db` (the project root inside the container). The first boot builds the index into the volume; subsequent boots reuse it.
