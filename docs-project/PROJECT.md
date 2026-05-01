# Launchpad Program Coach

## Purpose

A demo app built to supplement a job application for **Wonderschool's Early Career Software Engineer — Applied AI** role. The goal is to show end-to-end thinking about a real Wonderschool user problem: how to use an LLM + Wonderschool's own content to lower the barrier for someone trying to start a licensed home daycare.

## User Persona

**An aspiring home daycare educator.** Early in their journey. They have not yet applied for a license, may not know what state agency to talk to, and are typically overwhelmed by the volume and inconsistency of the information out there (state government PDFs, blog posts, Reddit threads, friends-of-friends). They need a single, calm starting point that tells them what to do next.

This is the highest-value moment in Wonderschool's funnel: the person *before* they become a Wonderschool provider, while they are still deciding whether starting a program is even possible for them.

## Core Value

The user answers **5 intake questions** (state, home type, age range, where they are in the process, biggest concern). The app then generates a **personalized licensing and business roadmap** — 5–6 named steps tailored to their inputs — grounded in retrieved Wonderschool blog content via a RAG pipeline. Each step cites the source article it came from. From the roadmap, the user can ask follow-up questions in a chat panel or click through to start a program with Wonderschool.

## Companion Documents

- [ARCHITECTURE.md](./ARCHITECTURE.md) — folder layout, RAG pipeline, models, environment
- [UX.md](./UX.md) — the five screens and interaction details
- [DECISIONS.md](./DECISIONS.md) — running log of product/technical decisions
