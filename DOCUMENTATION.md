# Design Documentation

## Problem

DSA prep is broken. People grind randomly, repeat patterns they're already good at, and ignore weaknesses. Existing tools (LeetCode lists, NeetCode roadmaps) are static — they don't adapt to what you actually know.

reps.gg is an adaptive learning engine that tracks per-subtopic mastery and serves problems where you need the most work.

## Technical Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 16, Tailwind, shadcn/ui | Fast iteration, dark theme out of the box |
| Backend | FastAPI (Python) | Tight integration with the Python mastery/reco engine |
| AI | OpenAI gpt-5-mini | Fast, cheap, good enough for structured JSON output |
| State | In-memory (single user) | Hackathon scope — no DB overhead |
| Data | 200 synthetic tagged problems | Subset of full 3,860 problem corpus |

## System Architecture

```
[Next.js Frontend :3001]
        |
        | /api/* proxy rewrite
        v
[FastAPI Backend :8000]
        |
        |--- lib/mastery.py          (scoring engine)
        |--- lib/reco_engine/        (recommendation engine)
        |      |--- llm.py           (LLM prompt + call)
        |      |--- search.py        (candidate selection)
        |      |--- data.py          (static data loading)
        |--- data/sample/            (synthetic problems + demo solves)
```

## Design Choices

### 1. Custom Taxonomy Over LeetCode Tags

LeetCode tags are flat and inconsistent ("Array", "Hash Table", "Dynamic Programming"). We built a hierarchical taxonomy: 18 topics → 40+ subtopics, each with importance weights. This enables granular mastery tracking — knowing you're weak at "Monotonic Stack" specifically, not just "Stack".

### 2. Importance Decoupled From Difficulty

A 3000-elo problem can have 0.15 importance if it's a niche math trick. A 1100-elo problem can have 0.95 importance if it's Two Sum (foundational pattern). This separation drives the mastery formula — you gain more from high-importance problems because those patterns transfer broadly.

### 3. Additive Mastery Over Averages/ELO

We don't average scores or use an ELO system. Each solve adds points based on:
- **Quality** (clean: 4.0, hints: 3.25, solution: 2.5, struggled: 0.0)
- **Difficulty multiplier** (0.3x-2.5x based on problem elo vs your expected elo at current mastery)
- **Importance gate** (niche problems get 25% of normal gain)
- **Diminishing returns** (post-Gold gains taper — Diamond requires real depth)

This is predictable and transparent. Users see exactly why their score changed.

### 4. Calculations Over Embeddings for Candidate Selection

We built embeddings but moved away from them. Embeddings find semantically similar problems, but we need problems targeting a specific subtopic at a specific difficulty/importance level. Direct filtering with expanding bounds gives more control:
- Start with tight elo + importance bounds
- Expand incrementally (elo ±50, importance -0.05) up to 5 times
- Later expansions are penalized in ranking (decay factor)

### 5. LLM as Recommender, Not Just Classifier

The LLM sees your full mastery profile and reasons about what to serve next. It picks subtopics + selectivity levels, then code handles candidate matching. This lets the LLM reason about things like "this user is strong at BFS but weak at multi-source BFS" without needing complex rule systems.

### 6. Rule-Based Fallback

If the LLM is unavailable, the system falls back to selecting the 10 weakest eligible subtopics sorted by gap to overall mastery, weighted by importance, with max 3 per topic for variety. No LLM needed — just math.

### 7. Conservative Resume Enrichment

Resume analysis bumps mastery only where there's concrete evidence (specific coursework, projects, job responsibilities). Capped at Silver (35) — resume shows familiarity, not mastery. If the user already has practice data (score ≥ 20), it's more accurate than resume inference, so we don't override it.

## Monte Carlo Calibration

Mastery rates aren't hand-tuned. We simulate 500 learning journeys × 300 problems across 8 archetypes (slow learner, fast learner, comfort zone player, contest grinder, etc.) and verify:
- NC150 completion reaches Silver/low Gold (30-40)
- NC250 completion reaches comfortable Gold (45-55)
- Slow learners still progress meaningfully
- Fast learners aren't artificially capped

## Future Enhancements

1. **Persistent storage** — PostgreSQL for multi-user state
2. **Spaced repetition** — Re-serve shaky problems (hints/solution used) after 30-day cooldown. Shaky twice = permanently discarded.
3. **Chrome extension** — Post-solve quality input directly on LeetCode
4. **Interview mode** — Filter by company type (FAANG/quant/startup), weight by interview plausibility
5. **Decay** — Mastery loss for inactive subtopics over time
6. **Targeted learning** — Lock recommendations to a specific topic
