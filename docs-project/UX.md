# UX

The flow is five screens. Intake is intentionally one page (not a form, not paginated) so the user can see the whole commitment up front and finish it in under a minute.

## Screen 1 — Welcome

- **Headline:** something short and direct that names what the app does for them (e.g. "Your starting line for a licensed home daycare.").
- **Description:** two sentences. First sentence names the problem (the process is overwhelming and state-specific). Second sentence names the promise (a personalized roadmap in under a minute).
- **CTA:** a single button — **"Get My Roadmap"** — that advances to Screen 2.

No nav, no secondary links, no footer chrome competing for attention.

## Screen 2 — Intake

All five questions live on **one screen**. Answers are **pill buttons**, not dropdowns or radios (except question 1, which is a dropdown because there are 50+ options). Tapping a pill selects it; tapping again deselects.

1. **What state are you in?** — *dropdown* (US states)
2. **What type of home do you have?** — apartment / condo / single family home / other
3. **What ages do you want to serve?** — infants / toddlers / preschool / mixed
4. **Where are you in the process?** — just exploring / ready to start / already started
5. **What's your biggest concern?** — licensing / money / finding families / setting up my space / all of it

### Surprise Me

A **"Surprise Me"** button randomly fills in all five answers with a **cascade animation** — the selections appear one after another (q1 → q2 → q3 → q4 → q5) so the user can watch it happen rather than seeing all five flip at once. Useful for demos and for users who want a "show me what this does" path.

### Build My Roadmap

The primary CTA at the bottom is **"Build My Roadmap"**. It is **greyed out until a state is selected** (state is the only hard requirement — without it the retrieval can't be state-specific). Once state is set, the button is active even if other answers are blank; missing answers are treated as "no preference" by the prompt.

## Screen 3 — Loading

- Animated loading state, ~3–5 seconds while the embedding + retrieval + LLM call runs.
- Status text: **"Building your personalized roadmap for [State]…"** (interpolates the user's selected state).
- The animation should feel like progress, not a generic spinner — it's the bridge between "I clicked a button" and "here is something tailored to me," and it sets up the perceived value of the result.

## Screen 4 — Roadmap

The result. **5–6 named steps** personalized to the user's intake answers. Each step has:

- A **name** (verb-led, action-oriented — e.g. "Confirm your home meets [State]'s square-footage rules").
- A short body (1–3 sentences) explaining what to do and why.
- A small **citation tag** linking to the source article URL the step was grounded in (the chunk's `source_url` from the Chroma metadata).

Two CTAs at the bottom:

- **"Ask a follow-up question"** → opens the chat panel (Screen 5).
- **"Start your program with Wonderschool"** → external link to `wonderschool.com`.

## Screen 5 — Chat

- Opens **below the roadmap** or as a **slide-in panel** (either is fine; the goal is that the roadmap stays visible/accessible so the user can refer back to it).
- **Pre-seeded with 3 suggested follow-up questions**, generated from the content of the roadmap that was just produced (e.g. if step 3 is about CPR training, one suggestion might be "How long is the CPR certification good for?"). Suggestions are clickable.
- After the suggestions, free chat. Every response should still go through the same RAG retrieval path so answers stay grounded in Wonderschool content.
