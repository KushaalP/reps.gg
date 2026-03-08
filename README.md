# reps.gg

**Video Demo:** https://youtu.be/2zx42ad9NTA

**Candidate Name:** Kushaal

**Scenario Chosen:** Skill-Bridge Career Navigator

**Estimated Time Spent:** ~5 hours

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- pnpm
- OpenAI API key (for LLM-powered recommendations and resume enrichment)

### Run Commands

```bash
# Backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your OPENAI_API_KEY
uvicorn api.server:app --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev
```

App runs at `http://localhost:3001`, API at `http://localhost:8000`.

### Test Commands

```bash
source venv/bin/activate
python tests/test_mastery_api.py
```

3 tests: clean solve increases mastery (happy path), mastery clamped at 100 (edge case), struggled gives zero change (edge case).

## Architecture

### Tech Stack
- **Frontend:** Next.js 16 (Turbopack), Tailwind CSS, shadcn/ui
- **Backend:** FastAPI (Python), in-memory state
- **AI:** OpenAI gpt-5-mini (recommendations + resume enrichment)
- **Data:** 200 synthetic tagged problems (`data/sample/synthetic_problems.json`)

### Core Flow
1. **Connect** — Load demo profile (80 synthetic solved problems) or connect LeetCode
2. **Resume Enrichment (AI)** — LLM analyzes resume text, conservatively bumps mastery on subtopics with concrete evidence (capped at Silver/35)
3. **Goal Selection** — Choose target (FAANG/Quant/Mid-tech/Startup/General), sets overall mastery target
4. **Dashboard** — View overall mastery vs target, per-topic/subtopic scores, gap analysis
5. **Recommendations (AI)** — LLM generates 10 problem profiles targeting weak subtopics, candidate search matches real problems
6. **Solve + Feedback** — Mark solved with quality rating, see mastery deltas per subtopic and overall

### AI Integration + Fallback
**AI features:**
- LLM-driven problem recommendations (analyzes mastery state, picks optimal subtopics + difficulty)
- LLM-driven resume enrichment (extracts skills from projects/coursework/experience)

**Rule-based fallback:** If the LLM is unavailable, the recommendation engine falls back to a heuristic that selects the 10 weakest eligible subtopics sorted by gap-to-overall-mastery and importance, with max 3 per topic for variety. See `RecoQueue._rule_based_profiles()` in `lib/reco_engine/__init__.py`.

### Input Validation
- Resume validation: LLM rejects non-resume input (gibberish, code, vague text) with a clear error message prompting the user to provide specific projects/coursework/experience
- Quality rating required before solve is recorded
- Goal must be selected before proceeding

### Data Safety
- All data is synthetic. `data/sample/synthetic_problems.json` contains 200 problems, `data/sample/demo_solves.json` contains 80 demo solve slugs.
- Real data files (`data/core/`) are gitignored.
- No live site scraping in the demo flow.

### Security
- API keys stored in `.env` (gitignored)
- `.env.example` provided with required variables

## Key Technical Decisions

### Tagging Pipeline
200 synthesized problems tagged via two-pass LLM pipeline (Claude Opus + Haiku) with 8-check validation and corrective pass. Each problem gets: primary/secondary subtopics with weights, importance (transferability, NOT difficulty), interview plausibility, company plausibility scores. Validated against NC250 as calibration anchors.

### Mastery Model (not averages, not ELO)
Additive scoring per subtopic (0-100). Each solve:
```
change = quality_score * difficulty_mult * importance_gate * mastery_rate * diminishing_returns
```
- **Difficulty multiplier**: harder problems relative to your level give more (0.3x-2.5x)
- **Importance gate**: niche problems (<0.2 importance) get 25% of normal gain
- **Diminishing returns**: post-Gold (40+) gains taper to 30% at mastery 100
- **Secondary gains**: solving a graph problem gives fractional heap mastery if it uses heaps

### Monte Carlo Calibration
500 simulated journeys x 300 problems across 8 archetypes (slow learner, fast learner, comfort zone, contest bro, etc.) to tune mastery rates, reco engine modes, and prerequisite thresholds. Target: NC150 completion ≈ Silver/Gold, NC250 ≈ comfortable Gold.

### Candidate Selection (calc over embeddings)
Direct subtopic filtering with elo/importance ranges instead of embedding similarity. Expanding bounds with decay: starts tight, widens elo ±50 and importance -0.05 per expansion (max 5), with later expansions penalized in ranking. Bronze users get 90th percentile importance gate; Silver+ get LLM-selectivity-based gate.

## AI Disclosure
- **Did you use an AI assistant?** Yes — Claude Code for implementation, iteration, and debugging.
- **How did you verify suggestions?** Manual testing of each endpoint, Monte Carlo simulation of mastery progression across archetypes, validation of tagging pipeline against NC250 benchmarks.
- **Example of a rejected/changed suggestion:** Claude initially proposed using embedding-based candidate search for recommendations. After testing, switched to direct subtopic filtering with elo/importance ranges — more precise, explainable, and tunable per dimension.

## Tradeoffs & Prioritization
- **What I cut:** Persistent database (in-memory state is fine for demo), Chrome extension (dashboard-only for now), interview practice mode, spaced repetition scheduling (shaky problem re-serving designed but not wired to frontend). Vector Embeddings
- **What I'd build next:** PostgreSQL persistence, spaced repetition with cooldown-based re-serving of shaky problems, Chrome extension for post-solve input on LeetCode, targeted learning mode (filter by topic), decay/progress loss for inactive subtopics
- **Known limitations:** Single-user in-memory state resets on server restart. Resume enrichment calls OpenAI directly from browser (bypasses Next.js proxy due to Turbopack rewrite issue). Demo profile is static synthetic data.
