"""
reps.gg API Server

Endpoints:
  POST /api/connect     — LC session/csrf → fetch solved → build mastery → return profile
  GET  /api/profile     — return current user profile
  POST /api/recommend   — generate 10 problem recommendations
  POST /api/solve       — report a solve with quality rating
  POST /api/skip        — skip a problem
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json
import requests
from openai import OpenAI

from lib.mastery import (
    new_user_state, update_mastery, get_subtopic_tier,
    get_topic_levels, get_overall_level,
)
from lib.reco_engine import (
    RecoQueue, TAG_LOOKUP, PROB_LOOKUP, TAXONOMY, SUBTOPIC_TO_TOPIC,
)

app = FastAPI(title="reps.gg API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── In-memory state (single user, fine for hackathon) ──────────────

_state = new_user_state()
_completed_ids: set[int] = set()
_skip_cooldown_ids: set[int] = set()
_discarded_ids: set[int] = set()
_queue = RecoQueue()
_goal: Optional[str] = None


# ── Request/response models ────────────────────────────────────────

class ConnectRequest(BaseModel):
    session: str
    csrfToken: str

class SolveRequest(BaseModel):
    problemId: str
    quality: str  # "clean" | "hints" | "solution" | "struggled"

class SkipRequest(BaseModel):
    problemId: str

class ResumeEnrichRequest(BaseModel):
    resume: str


# ── Helpers ─────────────────────────────────────────────────────────

def _fetch_leetcode_solved(session: str, csrf: str) -> list[str]:
    """Fetch all solved problem slugs from LeetCode GraphQL API."""
    cookies = {"csrftoken": csrf, "LEETCODE_SESSION": session}
    headers = {"x-csrftoken": csrf, "referer": "https://leetcode.com"}
    query = (
        'query q($c: String, $l: Int, $s: Int, $f: QuestionListFilterInput) '
        '{ problemsetQuestionList: questionList(categorySlug: $c, limit: $l, skip: $s, filters: $f) '
        '{ total: totalNum questions: data { titleSlug } } }'
    )

    all_slugs = set()
    skip = 0
    while True:
        resp = requests.post(
            "https://leetcode.com/graphql",
            json={
                "query": query,
                "variables": {"c": "", "l": 100, "s": skip, "f": {"status": "AC"}},
            },
            cookies=cookies,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("data", {}).get("problemsetQuestionList")
        if not result or not result.get("questions"):
            break
        for q in result["questions"]:
            all_slugs.add(q["titleSlug"])
        skip += 100
        if skip >= result.get("total", 0):
            break

    return list(all_slugs)


def _build_slug_to_id() -> dict[str, int]:
    """Map problem slug → problem ID."""
    return {p.get("slug", ""): p["id"] for p in PROB_LOOKUP.values() if p.get("slug")}


def _build_mastery_from_solved(slug_list: list[str]) -> tuple[dict, set[int]]:
    """Build mastery state from a list of solved problem slugs."""
    slug_to_id = _build_slug_to_id()
    matched_ids = [
        slug_to_id[s] for s in slug_list
        if s in slug_to_id and slug_to_id[s] in TAG_LOOKUP
    ]
    state = new_user_state()
    for pid in matched_ids:
        update_mastery(
            state, pid, TAG_LOOKUP[pid],
            used_hints=True, looked_at_solution=False, struggled=False,
        )
    return state, set(matched_ids)


def _format_profile(state: dict, completed_ids: set[int], goal: Optional[str]) -> dict:
    """Convert internal state → frontend UserProfile shape."""
    topic_levels = get_topic_levels(state, TAXONOMY)
    overall = get_overall_level(state, TAXONOMY)
    overall_tier = get_subtopic_tier(overall).lower()

    topics = []
    for topic in TAXONOMY["topics"]:
        t_name = topic["name"]
        t_data = topic_levels[t_name]
        subtopics = []
        for sub in topic["subtopics"]:
            s_name = sub["name"]
            s_data = state.get("subtopics", {}).get(s_name, {})
            score = round(s_data.get("score", 0.0), 1)
            tier = get_subtopic_tier(score).lower()
            subtopics.append({
                "id": s_name.lower().replace(" ", "-").replace("/", "-")[:30],
                "name": s_name,
                "score": score,
                "tier": tier,
                "problemsSolved": s_data.get("attempts_count", 0),
            })
        topics.append({
            "id": t_name.lower().replace(" ", "-").replace("/", "-")[:30],
            "name": t_name,
            "score": round(t_data["score"], 1),
            "tier": t_data["tier"].lower(),
            "subtopics": subtopics,
        })

    target = _goal_target_score(goal)
    return {
        "leetcodeConnected": True,
        "goal": goal,
        "targetScore": target,
        "overallScore": round(overall, 1),
        "overallTier": overall_tier,
        "totalProblemsSolved": len(completed_ids),
        "topics": topics,
    }


def _goal_target_score(goal: Optional[str]) -> int:
    return {
        "faang": 50,
        "quant": 65,
        "mid-tech": 40,
        "startup": 30,
        "general": 35,
    }.get(goal or "general", 35)


def _format_problems(candidates: list[dict]) -> list[dict]:
    """Convert internal candidate dicts → frontend Problem shape."""
    results = []
    for c in candidates:
        pid = c["id"]
        prob = PROB_LOOKUP.get(pid, {})
        slug = prob.get("slug", "")
        subtopic = c.get("primary_subtopic", "")
        topic = SUBTOPIC_TO_TOPIC.get(subtopic, "")
        results.append({
            "id": str(pid),
            "title": c.get("title", prob.get("title", "")),
            "url": f"https://leetcode.com/problems/{slug}/" if slug else "",
            "topic": topic,
            "subtopic": subtopic,
            "elo": c.get("elo", 0),
            "importance": round(c.get("importance", 0) * 100),
            "currentMastery": round(
                _state.get("subtopics", {}).get(subtopic, {}).get("score", 0.0), 1
            ),
        })
    return results


# ── Resume enrichment ───────────────────────────────────────────────

_RESUME_SYSTEM_PROMPT = """\
You are a conservative mastery estimator for reps.gg, a DSA learning platform.

You receive a user's resume and their current mastery state (per-subtopic scores, 0-100 scale). Your job is to identify subtopics where the resume provides STRONG evidence the user has more skill than their current score reflects, and output conservative score bumps.

Tier reference (0-100 scale):
- Bronze: 0-19 (beginner, no real experience)
- Silver: 20-39 (has seen it, basic competency)
- Gold: 40-59 (solid, can solve medium problems)
- Platinum: 60-79 (strong, can handle hard problems)
- Diamond: 80-100 (expert level)

Rules — be VERY conservative:
- Only bump subtopics where the resume gives CONCRETE evidence (specific coursework, projects, or job responsibilities that clearly involve that pattern).
- Never bump above Silver (max score 35) from resume alone — resume shows familiarity, not mastery. Mastery comes from practice.
- If a user already has a score >= 20 in a subtopic, do NOT bump it further — their practice data is more accurate than resume inference.
- Prefer small bumps (5-15 points) over large ones.
- "Familiar with data structures" or vague claims = no bump.
- Specific evidence examples that DO warrant bumps:
  - "Built a graph-based recommendation engine" → BFS/DFS subtopics +10-15
  - "Algorithms coursework covering DP and greedy" → Linear Recurrence DP, Greedy +10
  - "Worked on search infrastructure at Google" → Binary Search, Trees +10-15
  - "Competitive programming experience" → broad small bumps +5-10 across fundamentals
- If no LeetCode data was provided (all scores are 0), you can be slightly more generous with fundamentals if the resume shows strong CS background, but still cap at 35.

Output valid JSON: {"bumps": [{"subtopic": "exact subtopic name", "bump": number, "reason": "brief justification"}]}
If no bumps are warranted, output: {"bumps": []}
"""


def _build_resume_prompt(resume: str, state: dict) -> str:
    """Build the user prompt for resume enrichment."""
    parts = []

    parts.append("=== TAXONOMY (valid subtopic names) ===")
    for topic in TAXONOMY["topics"]:
        parts.append(f"{topic['name']}:")
        for sub in topic["subtopics"]:
            parts.append(f"  - {sub['name']}")

    parts.append("\n=== CURRENT MASTERY STATE ===")
    has_any_score = False
    for topic in TAXONOMY["topics"]:
        for sub in topic["subtopics"]:
            s_name = sub["name"]
            score = round(state.get("subtopics", {}).get(s_name, {}).get("score", 0.0), 1)
            if score > 0:
                has_any_score = True
            parts.append(f"  {s_name}: {score}")

    if not has_any_score:
        parts.append("\nNote: No LeetCode data — all scores are 0. User has not connected LeetCode or has no solved problems.")

    parts.append(f"\n=== RESUME ===\n{resume}")
    parts.append("\nAnalyze the resume and output conservative score bumps.")

    return "\n".join(parts)


def _enrich_mastery_from_resume(state: dict, resume: str) -> list[dict]:
    """Call LLM to analyze resume and return applied bumps."""
    user_prompt = _build_resume_prompt(resume, state)

    client = OpenAI()
    response = client.responses.create(
        model="gpt-5-mini",
        input=[
            {"role": "developer", "content": _RESUME_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        text={"format": {"type": "json_object"}},
    )

    raw = response.output_text
    parsed = json.loads(raw)
    bumps = parsed.get("bumps", [])

    applied = []
    from lib.mastery import _ensure_subtopic
    from lib.reco_engine import ALL_SUBTOPICS

    valid_subtopics = set(ALL_SUBTOPICS)

    for bump in bumps:
        sub_name = bump.get("subtopic", "")
        amount = bump.get("bump", 0)
        reason = bump.get("reason", "")

        # Validate
        if sub_name not in valid_subtopics:
            continue
        if amount <= 0 or amount > 35:
            continue

        current = state.get("subtopics", {}).get(sub_name, {}).get("score", 0.0)

        # Don't bump if already >= 20 (practice data is more reliable)
        if current >= 20:
            continue

        # Cap at 35 (Silver)
        new_score = min(35.0, current + amount)
        actual_bump = round(new_score - current, 1)

        if actual_bump <= 0:
            continue

        _ensure_subtopic(state, sub_name)
        state["subtopics"][sub_name]["score"] = new_score

        applied.append({
            "subtopic": sub_name,
            "oldScore": round(current, 1),
            "newScore": round(new_score, 1),
            "bump": actual_bump,
            "reason": reason,
        })

    return applied


# ── Endpoints ───────────────────────────────────────────────────────

@app.post("/api/connect")
async def connect(req: ConnectRequest):
    global _state, _completed_ids, _queue, _goal

    try:
        slugs = _fetch_leetcode_solved(req.session, req.csrfToken)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch LeetCode data: {e}")

    _state, _completed_ids = _build_mastery_from_solved(slugs)
    _queue = RecoQueue()
    _queue.load_exclusions(_completed_ids, _skip_cooldown_ids, _discarded_ids)

    return {
        "connected": True,
        "problemsMatched": len(_completed_ids),
        "totalSlugs": len(slugs),
    }


@app.get("/api/profile")
async def get_profile():
    return _format_profile(_state, _completed_ids, _goal)


@app.post("/api/recommend")
async def recommend():
    global _queue

    _queue = RecoQueue()
    _queue.load_exclusions(_completed_ids, _skip_cooldown_ids, _discarded_ids)
    _queue.fill(_state)

    # Collect the first candidate from each slot
    problems = []
    for slot in _queue.slots:
        if slot["candidates"]:
            problems.append(slot["candidates"][0])

    return {"problems": _format_problems(problems)}


@app.post("/api/solve")
async def solve(req: SolveRequest):
    global _state

    pid = int(req.problemId)
    tags = TAG_LOOKUP.get(pid)
    if not tags:
        raise HTTPException(status_code=404, detail="Problem not found in database")

    # Map frontend quality names to mastery params
    quality_map = {
        "clean":    {"used_hints": False, "looked_at_solution": False, "struggled": False},
        "hints":    {"used_hints": True,  "looked_at_solution": False, "struggled": False},
        "solution": {"used_hints": False, "looked_at_solution": True,  "struggled": False},
        "struggled": {"used_hints": False, "looked_at_solution": False, "struggled": True},
    }
    params = quality_map.get(req.quality)
    if not params:
        raise HTTPException(status_code=400, detail=f"Invalid quality: {req.quality}")

    # Snapshot scores before update
    primary = tags["primary_subtopic"]["name"]
    old_primary_score = round(_state.get("subtopics", {}).get(primary, {}).get("score", 0.0), 1)
    old_overall = round(get_overall_level(_state, TAXONOMY), 1)

    secondary_old = {}
    for sec in tags.get("secondary_subtopics", []):
        sec_name = sec["name"]
        secondary_old[sec_name] = round(
            _state.get("subtopics", {}).get(sec_name, {}).get("score", 0.0), 1
        )

    _state = update_mastery(_state, pid, tags, **params)
    _completed_ids.add(pid)

    # Find and mark the slot as completed
    for i, slot in enumerate(_queue.slots):
        if slot["candidates"] and slot["candidates"][slot["current_index"]]["id"] == pid:
            _queue.mark_completed(i)
            break

    # Build rich feedback
    new_primary_score = round(_state["subtopics"][primary]["score"], 1)
    new_primary_tier = get_subtopic_tier(new_primary_score).lower()
    old_primary_tier = get_subtopic_tier(old_primary_score).lower()
    primary_delta = round(new_primary_score - old_primary_score, 2)

    secondary_changes = []
    for sec in tags.get("secondary_subtopics", []):
        sec_name = sec["name"]
        new_sec = round(_state["subtopics"][sec_name]["score"], 1)
        old_sec = secondary_old.get(sec_name, 0.0)
        delta = round(new_sec - old_sec, 2)
        if abs(delta) > 0.01:
            secondary_changes.append({
                "subtopic": sec_name,
                "oldScore": old_sec,
                "newScore": new_sec,
                "delta": delta,
                "newTier": get_subtopic_tier(new_sec).lower(),
            })

    new_overall = round(get_overall_level(_state, TAXONOMY), 1)

    return {
        "updated": True,
        "primary": {
            "subtopic": primary,
            "topic": SUBTOPIC_TO_TOPIC.get(primary, ""),
            "oldScore": old_primary_score,
            "newScore": new_primary_score,
            "delta": primary_delta,
            "oldTier": old_primary_tier,
            "newTier": new_primary_tier,
            "tierChanged": old_primary_tier != new_primary_tier,
        },
        "secondary": secondary_changes,
        "overall": {
            "oldScore": old_overall,
            "newScore": new_overall,
            "delta": round(new_overall - old_overall, 2),
        },
    }


@app.post("/api/skip")
async def skip(req: SkipRequest):
    pid = int(req.problemId)
    _skip_cooldown_ids.add(pid)

    # Find and mark the slot as skipped
    for i, slot in enumerate(_queue.slots):
        if slot["candidates"] and slot["candidates"][slot["current_index"]]["id"] == pid:
            _queue.mark_skipped(i)
            break

    return {"skipped": True}


@app.post("/api/enrich-resume")
async def enrich_resume(req: ResumeEnrichRequest):
    global _state

    if not req.resume.strip():
        return {"enriched": False, "bumps": [], "message": "No resume provided"}

    try:
        bumps = _enrich_mastery_from_resume(_state, req.resume)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume enrichment failed: {e}")

    new_overall = round(get_overall_level(_state, TAXONOMY), 1)

    return {
        "enriched": True,
        "bumps": bumps,
        "newOverall": new_overall,
    }


@app.post("/api/goal")
async def set_goal(goal: dict):
    global _goal
    _goal = goal.get("goal")
    return {"goal": _goal}
