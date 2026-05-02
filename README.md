# Hey, Wonderschool team.

## Why I built this

I saw the Early Career Software Engineer - Applied AI role and am so excited about it, I wanted to do something to stand out. So I built this demo today. It is a functional demo of a high-value moment in your funnel: the aspiring home daycare educator who has not yet become a provider and is trying to figure out if getting licensed is even possible for them.

## What it does

The user answers five intake questions, and the app builds a personalized licensing and business roadmap - five or six named steps.  The data is from Wonderschool's own blog content. Each step cites the source article it came from. From the roadmap, the user can open a slide-in chat panel to ask follow-up questions, or click straight through to start a program with Wonderschool.

The LLM is instructed to answer only from what was retrieved — it does not invent state-specific licensing facts. If a user asks about Texas capacity rules, the answer comes from the Texas article in the corpus, not from the model's training weights.

## Why these technical choices

Every meaningful decision maps to something in how Wonderschool's problem actually works.

**Python + FastAPI + vanilla CSS/JS** keeps the whole project in one process, one language, and zero build steps. The retrieval and generation layers are pure Python, so a Python web framework was the natural home. FastAPI specifically gives free JSON schema validation on the two API endpoints without the overhead of a framework designed for larger teams. Vanilla HTML/CSS/JS with no bundler means anyone can clone and run it in under two minutes.

**RAG with ChromaDB + OpenAI embeddings** is the core of the product decision. The licensing rules vary dramatically by state — California's capacity rules are not Texas's. Chunking the Wonderschool articles, embedding them locally into a persistent ChromaDB collection, and filtering at retrieval time by state metadata means a New York user only sees New York-relevant chunks. That state filter is set in the `where` clause of every Chroma query and is the primary thing that prevents cross-state hallucination.

**Anthropic Claude Sonnet 4** for generation. The hard constraint here is staying inside the retrieved context. Claude has been the most consistent instruction-follower for "answer only from the provided chunks and cite which one you used." That discipline matters more for this use case than model size.

**Wonderschool's own blog as the only corpus.** Mixing Wonderschool's summaries with primary government sources creates versioning conflicts — the same rule described with different numbers, different effective dates. Limiting the corpus to Wonderschool's content keeps answers consistent with Wonderschool's own voice. Business content (LLC, pricing, zoning) is handled by the LLM's general knowledge rather than retrieval, because those topics are not state-specific in a way that benefits from vector search.

**State dropdown limited to seven states.** The corpus only has real coverage for California, Florida, Maryland, New York, North Carolina, Texas, and Washington. Allowing a user to pick Ohio would mean the LLM gets no relevant chunks and either refuses or freelances — both are bad outcomes. Better to make the supported set visible in the UI.

## Running it locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set:
#   OPENAI_API_KEY=...
#   ANTHROPIC_API_KEY=...

# optional — build the vector index ahead of time
# (the server also builds it automatically on first start if chroma_db/ is missing)
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
docs/business/   Business articles, kept on disk but not indexed
scripts/
  scrape.py      Scrape Wonderschool blog posts into docs/
  embed.py       Chunk docs, embed with OpenAI, write chroma_db/
  audit.py       Sanity checks on the scraped text
  test_rag.py    Smoke test for retrieval
chroma_db/       Generated vector store (gitignored)
docs-project/    Architecture, decisions, and UX notes
```

## Notes on the Data

RAG quality is bounded by corpus quality, and corpus quality starts with choosing the right source. When I started researching child care licensing content, the landscape online is genuinely rough — state agency websites are inconsistent, PDFs go stale, forum threads contradict each other, and it's hard to know what's current. Wonderschool's blog stood out as a clear, maintained, and trustworthy resource. Trusting it as the sole corpus was a deliberate call: for a 1 or 2 day project, grounding answers in one coherent voice is better than blending Wonderschool's summaries with primary government sources that may describe the same rule differently, at different dates, with different numbers.

The tradeoff is real though. The corpus is small — 26 documents across seven states — and coverage is uneven. California and Texas are well-covered; Maryland and North Carolina are thinner. I spent real time on the scraper to make the most of what was there: stripping the sitewide nav blocks, the "this post is a part of our series" intro lists, and the trailing "Join Wonderschool Today / Related Content" footers that were contaminating every chunk with keywords from every other article. That cleanup made a measurable difference in retrieval rank. But a small, clean corpus is still a small corpus — the answers are only as good as the articles that exist. If I had more time, I would expand state coverage and depth of information, add a reranker pass before the LLM call, and think much more deeply on edge cases and liability.  


---

[Portfolio](https://heyimhelen.com) | [LinkedIn](https://www.linkedin.com/in/helen-highwater-96981532/)
