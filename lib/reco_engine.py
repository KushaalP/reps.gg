"""
reps.gg Recommendation Engine

LLM-driven problem recommendation with direct subtopic matching.

Flow:
1. Code assembles context (mastery state, taxonomy, prereqs, history, stale flags)
2. LLM outputs 10 problem profiles (subtopic + elo_range + importance_range)
3. Each profile → direct subtopic search (primary then secondary by weight)
4. Code filters: completed, skip cooldown, discarded, prereq-gated, elo/importance bounds
5. Queue serves one problem per slot; skips rotate to back of queue
6. Re-call LLM when queue is empty or bulk import (10+) invalidates it
"""

import json
import yaml
import time
import os
import sys
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.mastery import (
    get_subtopic_tier, get_topic_levels, get_overall_level,
)

# ── Load static data ──────────────────────────────────────────────

with open("data/core/tagged_problems.json") as f:
    TAGGED = json.load(f)

with open("data/core/problems.json") as f:
    PROBLEMS = json.load(f)

with open("taxonomy.yaml") as f:
    TAXONOMY = yaml.safe_load(f)

with open("prerequisites.yaml") as f:
    _prereqs = yaml.safe_load(f).get("prerequisites", {})

with open("data/core/embeddings.json") as f:
    _emb_data = json.load(f)

TAG_LOOKUP = {t["id"]: t for t in TAGGED}
PROB_LOOKUP = {p["id"]: p for p in PROBLEMS}

# Precompute embedding matrix
EMB_IDS = [e["id"] for e in _emb_data]
EMB_VECTORS = np.array([e["embedding"] for e in _emb_data])
EMB_VECTORS = EMB_VECTORS / np.linalg.norm(EMB_VECTORS, axis=1, keepdims=True)

# Build prereq lookup
HARD_PREREQS = {}
for sub_name, prereq_data in _prereqs.items():
    hard = prereq_data.get("hard", [])
    if hard:
        HARD_PREREQS[sub_name] = hard

PREREQ_MIN_MASTERY = 10.0

# All subtopic names for reference
ALL_SUBTOPICS = []
SUBTOPIC_TO_TOPIC = {}
for topic in TAXONOMY["topics"]:
    for sub in topic["subtopics"]:
        ALL_SUBTOPICS.append(sub["name"])
        SUBTOPIC_TO_TOPIC[sub["name"]] = topic["name"]

# Precompute per-subtopic elo stats from tagged problems
_sub_elos = {}
for t in TAGGED:
    sub = t["primary_subtopic"]["name"]
    elo = t.get("difficulty", 0)
    if elo:
        _sub_elos.setdefault(sub, []).append(elo)

import statistics
SUBTOPIC_ELO_STATS = {}
for sub, elos in _sub_elos.items():
    elos.sort()
    SUBTOPIC_ELO_STATS[sub] = {
        "min": round(elos[0]),
        "median": round(statistics.median(elos)),
        "max": round(elos[-1]),
        "count": len(elos),
    }

# ── Staleness detection ───────────────────────────────────────────

STALE_THRESHOLD_DAYS = 14  # subtopics not attempted in this many days are flagged


def get_stale_subtopics(state, now=None):
    """Return subtopics that have been attempted before but are stale."""
    if now is None:
        now = time.time()
    stale = []
    for sub_name, sub_data in state.get("subtopics", {}).items():
        last = sub_data.get("last_attempted")
        if last is None:
            continue
        days_since = (now - last) / 86400
        if days_since >= STALE_THRESHOLD_DAYS and sub_data.get("score", 0) > 0:
            stale.append({
                "name": sub_name,
                "score": round(sub_data["score"], 1),
                "tier": get_subtopic_tier(sub_data["score"]),
                "days_since": round(days_since),
            })
    stale.sort(key=lambda x: -x["days_since"])
    return stale


# ── Prereq check ──────────────────────────────────────────────────

def prereqs_met(state, subtopic):
    if subtopic not in HARD_PREREQS:
        return True
    for prereq in HARD_PREREQS[subtopic]:
        if state.get("subtopics", {}).get(prereq, {}).get("score", 0.0) < PREREQ_MIN_MASTERY:
            return False
    return True


def get_locked_subtopics(state):
    """Return list of subtopics whose hard prereqs are not met."""
    locked = []
    for sub in ALL_SUBTOPICS:
        if not prereqs_met(state, sub):
            locked.append(sub)
    return locked


# ── Build LLM context ─────────────────────────────────────────────

def get_exhausted_subtopics(completed_ids, skip_cooldown_ids, discarded_ids):
    """Return set of subtopics where all available problems are completed/excluded."""
    excluded = completed_ids | skip_cooldown_ids | discarded_ids
    exhausted = set()
    for sub_name in ALL_SUBTOPICS:
        all_pids = set(_PRIMARY_INDEX.get(sub_name, []))
        for pid, _ in _SECONDARY_INDEX.get(sub_name, []):
            all_pids.add(pid)
        if all_pids and all_pids.issubset(excluded):
            exhausted.add(sub_name)
    return exhausted


def build_mastery_summary(state, exhausted_subtopics=None):
    """Compact mastery summary for the LLM prompt."""
    if exhausted_subtopics is None:
        exhausted_subtopics = set()
    lines = []
    topic_levels = get_topic_levels(state, TAXONOMY)
    overall = get_overall_level(state, TAXONOMY)

    lines.append(f"Overall: {overall} ({get_subtopic_tier(overall)})")
    lines.append("")

    for topic in TAXONOMY["topics"]:
        t_name = topic["name"]
        t_data = topic_levels[t_name]
        lines.append(f"{t_name}: {t_data['score']} ({t_data['tier']})")
        for sub in topic["subtopics"]:
            s_name = sub["name"]
            s_data = state.get("subtopics", {}).get(s_name, {})
            score = round(s_data.get("score", 0.0), 1)
            count = s_data.get("attempts_count", 0)
            tier = get_subtopic_tier(score)
            flags = ""
            if not prereqs_met(state, s_name):
                flags = " [LOCKED]"
            elif s_name in exhausted_subtopics:
                flags = " [EXHAUSTED]"
            lines.append(f"  {s_name}: {score} ({tier}, {count} attempts){flags}")
        lines.append("")

    return "\n".join(lines)


def build_recent_history(state, n=5):
    """Last n attempts as context."""
    attempts = state.get("attempts", [])
    recent = attempts[-n:] if len(attempts) >= n else attempts
    if not recent:
        return "No attempts yet."

    lines = []
    for a in reversed(recent):
        pid = a["problem_id"]
        prob = PROB_LOOKUP.get(pid, {})
        title = prob.get("title", f"#{pid}")
        lines.append(
            f"- {title} | {a['primary_subtopic']} | {a['quality']} | "
            f"{a['perceived_difficulty']} | change: {a['mastery_change']:+.2f}"
        )
    return "\n".join(lines)


def build_taxonomy_summary():
    """Compact taxonomy for the prompt (topic > subtopic: importance + elo stats)."""
    lines = []
    for topic in TAXONOMY["topics"]:
        lines.append(f"{topic['name']} (importance: {topic['importance']}):")
        for sub in topic["subtopics"]:
            stats = SUBTOPIC_ELO_STATS.get(sub["name"])
            if stats:
                lines.append(f"  {sub['name']}: importance {sub['importance']}, elo {stats['min']}-{stats['max']} (median {stats['median']}, {stats['count']} problems)")
            else:
                lines.append(f"  {sub['name']}: importance {sub['importance']}")
    return "\n".join(lines)


def build_prereq_summary():
    """Compact prereq graph for the prompt."""
    lines = []
    for sub_name, prereqs in HARD_PREREQS.items():
        lines.append(f"{sub_name} requires: {', '.join(prereqs)}")
    return "\n".join(lines)


# ── LLM prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the recommendation engine for reps.gg, an adaptive DSA learning platform.

Your job: given a user's mastery state, generate 10 problem profiles that will optimally advance their learning.

Each profile targets a single subtopic. Use EXACT topic and subtopic names from the taxonomy provided.

You specify an elo_range [min, max] and importance_range [min, max] for each profile.

Guidelines for elo_range and importance_range:
- elo_range maps to problem difficulty. Each subtopic in the taxonomy includes its actual elo range (min-max) and median from our problem database. USE THESE STATS to pick realistic elo ranges. Do NOT pick elo values below a subtopic's min or above its max.
- A user's expected elo = 800 + (subtopic_mastery / 100) * 1900. Recommend problems NEAR their expected elo for that subtopic — slightly above to push, at level to reinforce. But always constrain to what actually exists in the database for that subtopic.
- importance_range controls how foundational vs niche the problems are.
  - Low mastery users (Bronze/Silver): prioritize high importance [0.6, 1.0] — these are the most transferable patterns.
  - Medium mastery users (Gold): mix of high and moderate importance [0.4, 1.0].
  - High mastery users (Platinum/Diamond): can include lower importance [0.2, 1.0] — niche patterns become valuable.
- Ranges should be tight enough to be useful but not so tight that no problems match. A spread of 0.2-0.3 for importance and 200-400 for elo is typical.

Guidelines for what to recommend:
- Never recommend subtopics marked [LOCKED] — their prerequisites are not met.
- Never recommend subtopics marked [EXHAUSTED] — no problems remain for that subtopic.
- Prioritize subtopics that are lagging relative to the user's overall level.
- Introduce variety — don't recommend the same subtopic multiple times unless they desperately need it.
- If stale subtopics are flagged, include 1-2 review profiles at the user's current level for those subtopics.
- Consider the prerequisite graph: if a user is weak in a prereq, strengthening it benefits downstream subtopics.
- Balance breadth and depth — don't hyper-focus on one topic unless that's what the user needs.

Output valid JSON with the key "recommendations" containing an array of 10 objects. Format:
{"recommendations": [
  {
    "topic": "Arrays & Hashing",
    "subtopic": "Frequency Counting / Hash Map Lookup",
    "elo_range": [800, 1200],
    "importance_range": [0.7, 1.0]
  }
]}
"""


def build_user_prompt(state, topic_filter=None, stale_subtopics=None, exhausted_subtopics=None):
    parts = []

    parts.append("=== TAXONOMY ===")
    parts.append(build_taxonomy_summary())

    parts.append("\n=== PREREQUISITE GRAPH (hard requirements) ===")
    parts.append(build_prereq_summary())

    parts.append("\n=== USER MASTERY STATE ===")
    parts.append(build_mastery_summary(state, exhausted_subtopics or set()))

    parts.append("\n=== RECENT HISTORY (last 5 attempts) ===")
    parts.append(build_recent_history(state))

    if stale_subtopics:
        parts.append("\n=== STALE SUBTOPICS (due for review) ===")
        for s in stale_subtopics[:5]:
            parts.append(f"- {s['name']}: {s['score']} ({s['tier']}), {s['days_since']} days since last attempt")

    if topic_filter:
        parts.append(f"\n=== ACTIVE TOPIC FILTER ===")
        parts.append(f"User has filtered to: {topic_filter}. ALL 10 recommendations must be within this topic.")

    parts.append("\nGenerate 10 problem profiles.")

    return "\n".join(parts)


# ── LLM call ──────────────────────────────────────────────────────

def call_llm(state, topic_filter=None, exhausted_subtopics=None):
    """Call the LLM to generate 10 problem profiles."""
    stale = get_stale_subtopics(state)
    user_prompt = build_user_prompt(state, topic_filter, stale, exhausted_subtopics)

    client = OpenAI()
    response = client.responses.create(
        model="gpt-5-mini",
        input=[
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        reasoning={"effort": "low"},
        text={"format": {"type": "json_object"}},
    )

    raw = response.output_text
    parsed = json.loads(raw)

    # Handle both {"recommendations": [...]} and [...] formats
    if isinstance(parsed, list):
        profiles = parsed
    elif isinstance(parsed, dict):
        # Try common keys
        for key in ["recommendations", "profiles", "problems", "problem_profiles"]:
            if key in parsed:
                profiles = parsed[key]
                break
        else:
            # If dict has no known key, check if values contain a list
            for v in parsed.values():
                if isinstance(v, list):
                    profiles = v
                    break
            else:
                print(f"DEBUG: Unexpected LLM response structure: {list(parsed.keys())}")
                profiles = []
    else:
        profiles = []

    if not profiles:
        print(f"DEBUG: Raw LLM response: {raw[:500]}")
    else:
        print(f"\n--- Raw LLM Output ---\n{raw}\n--- End LLM Output ---\n")

    return profiles


# ── Embedding search + filtering ──────────────────────────────────

def embed_query(query_text):
    """Embed a single query string using the same model as our DB."""
    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=[query_text],
    )
    vec = np.array(response.data[0].embedding)
    return vec / np.linalg.norm(vec)


def search_candidates(query_vec, top_k=50):
    """Return top_k most similar problem IDs with scores."""
    scores = EMB_VECTORS @ query_vec
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(EMB_IDS[i], float(scores[i])) for i in top_indices]


def filter_candidates(
    candidates,
    elo_range,
    importance_range,
    state,
    completed_ids,
    skip_cooldown_ids,
    discarded_ids,
    max_results=5,
    elo_expand_step=50,
    importance_expand_step=0.05,
    max_expansions=5,
):
    """
    Filter candidates by elo, importance, prereqs, and exclusion lists.
    If too few pass, widen bounds incrementally.
    """
    elo_min, elo_max = elo_range
    imp_min, imp_max = importance_range

    for expansion in range(max_expansions + 1):
        current_elo_min = elo_min - (expansion * elo_expand_step)
        current_elo_max = elo_max + (expansion * elo_expand_step)
        current_imp_min = max(0.0, imp_min - (expansion * importance_expand_step))
        current_imp_max = min(1.0, imp_max + (expansion * importance_expand_step))

        results = []
        for pid, sim_score in candidates:
            # Exclusion filters
            if pid in completed_ids or pid in skip_cooldown_ids or pid in discarded_ids:
                continue

            tags = TAG_LOOKUP.get(pid)
            if not tags:
                continue

            # Prereq gate
            primary_sub = tags["primary_subtopic"]["name"]
            if not prereqs_met(state, primary_sub):
                continue

            # Elo filter
            prob_elo = tags.get("difficulty", 0)
            if prob_elo < current_elo_min or prob_elo > current_elo_max:
                continue

            # Importance filter
            prob_imp = tags.get("importance", 0)
            if prob_imp < current_imp_min or prob_imp > current_imp_max:
                continue

            prob = PROB_LOOKUP.get(pid, {})
            results.append({
                "id": pid,
                "title": prob.get("title", ""),
                "slug": prob.get("slug", ""),
                "elo": prob_elo,
                "importance": prob_imp,
                "primary_subtopic": primary_sub,
                "similarity": round(sim_score, 4),
            })

            if len(results) >= max_results:
                break

        if results:
            return results

    return []


# ── Direct subtopic search ────────────────────────────────────────

# Build secondary subtopic index: subtopic_name -> [(problem_id, weight)]
_SECONDARY_INDEX = {}
for _t in TAGGED:
    for _s in _t.get("secondary_subtopics", []):
        _SECONDARY_INDEX.setdefault(_s["name"], []).append((_t["id"], _s["weight"]))
# Sort by weight descending
for _sub in _SECONDARY_INDEX:
    _SECONDARY_INDEX[_sub].sort(key=lambda x: -x[1])

# Build primary subtopic index: subtopic_name -> [problem_id]
_PRIMARY_INDEX = {}
for _t in TAGGED:
    _PRIMARY_INDEX.setdefault(_t["primary_subtopic"]["name"], []).append(_t["id"])


def search_by_subtopic(
    subtopic,
    elo_range,
    importance_range,
    state,
    completed_ids,
    skip_cooldown_ids,
    discarded_ids,
    max_results=5,
    elo_expand_step=50,
    importance_expand_step=0.05,
    max_expansions=5,
):
    """
    Search for problems by subtopic name with elo/importance filters.
    Primary matches first, then secondary (sorted by weight) if needed.
    Widens bounds incrementally if too few results.
    """

    def _filter(pid, elo_min, elo_max, imp_min, imp_max):
        if pid in completed_ids or pid in skip_cooldown_ids or pid in discarded_ids:
            return None
        tags = TAG_LOOKUP.get(pid)
        if not tags:
            return None
        primary_sub = tags["primary_subtopic"]["name"]
        if not prereqs_met(state, primary_sub):
            return None
        prob_elo = tags.get("difficulty", 0)
        if prob_elo < elo_min or prob_elo > elo_max:
            return None
        prob_imp = tags.get("importance", 0)
        if prob_imp < imp_min or prob_imp > imp_max:
            return None
        prob = PROB_LOOKUP.get(pid, {})
        return {
            "id": pid,
            "title": prob.get("title", ""),
            "slug": prob.get("slug", ""),
            "elo": prob_elo,
            "importance": prob_imp,
            "primary_subtopic": primary_sub,
            "match_type": None,  # filled by caller
            "weight": None,
        }

    elo_min, elo_max = elo_range
    imp_min, imp_max = importance_range
    min_secondary_weight = 0.15

    all_candidates = []
    seen_ids = set()

    for expansion in range(max_expansions + 1):
        cur_elo_min = elo_min - (expansion * elo_expand_step)
        cur_elo_max = elo_max + (expansion * elo_expand_step)
        cur_imp_min = max(0.0, imp_min - (expansion * importance_expand_step))
        cur_imp_max = min(1.0, imp_max + (expansion * importance_expand_step))
        decay = 1.0 - (expansion * 0.1)

        for pid in _PRIMARY_INDEX.get(subtopic, []):
            if pid in seen_ids:
                continue
            r = _filter(pid, cur_elo_min, cur_elo_max, cur_imp_min, cur_imp_max)
            if r:
                w = TAG_LOOKUP[pid]["primary_subtopic"]["weight"]
                r["match_type"] = "primary"
                r["weight"] = w
                r["score"] = 1.0 * w * decay
                all_candidates.append(r)
                seen_ids.add(pid)

        for pid, weight in _SECONDARY_INDEX.get(subtopic, []):
            if pid in seen_ids or weight < min_secondary_weight:
                continue
            r = _filter(pid, cur_elo_min, cur_elo_max, cur_imp_min, cur_imp_max)
            if r:
                r["match_type"] = "secondary"
                r["weight"] = weight
                r["score"] = 0.5 * weight * decay
                all_candidates.append(r)
                seen_ids.add(pid)

    all_candidates.sort(key=lambda x: -x["score"])
    return all_candidates[:max_results]


# ── Queue management ──────────────────────────────────────────────

class RecoQueue:
    """
    Manages the recommendation queue.

    Structure: list of slots, each slot has:
      - profile: the LLM-generated profile
      - candidates: list of up to 5 problems
      - current_index: which candidate is being served
      - completed: whether the user finished a problem from this slot
    """

    def __init__(self):
        self.slots = []
        self._completed_ids = set()
        self._skip_cooldown_ids = set()
        self._discarded_ids = set()

    def load_exclusions(self, completed_ids, skip_cooldown_ids, discarded_ids):
        self._completed_ids = set(completed_ids)
        self._skip_cooldown_ids = set(skip_cooldown_ids)
        self._discarded_ids = set(discarded_ids)

    def fill(self, state, topic_filter=None, use_embeddings=False):
        """Call LLM and fill the queue with 10 slots."""
        exhausted = get_exhausted_subtopics(
            self._completed_ids, self._skip_cooldown_ids, self._discarded_ids
        )
        profiles = call_llm(state, topic_filter, exhausted)
        self.slots = []

        if not profiles:
            return

        if use_embeddings:
            # Embedding-based search (legacy)
            queries = [p.get("query", f"Topic: {p.get('topic','')}. Primary subtopic: {p.get('subtopic','')}.") for p in profiles]
            client = OpenAI()
            response = client.embeddings.create(
                model="text-embedding-3-large",
                input=queries,
            )
            query_vecs = np.array([r.embedding for r in response.data])
            query_vecs = query_vecs / np.linalg.norm(query_vecs, axis=1, keepdims=True)

            for i, profile in enumerate(profiles):
                candidates_raw = search_candidates(query_vecs[i], top_k=50)
                candidates = filter_candidates(
                    candidates_raw,
                    elo_range=profile.get("elo_range", [800, 2500]),
                    importance_range=profile.get("importance_range", [0.0, 1.0]),
                    state=state,
                    completed_ids=self._completed_ids,
                    skip_cooldown_ids=self._skip_cooldown_ids,
                    discarded_ids=self._discarded_ids,
                    max_results=5,
                )
                self.slots.append({
                    "profile": profile,
                    "candidates": candidates,
                    "current_index": 0,
                    "completed": False,
                })
        else:
            # Direct subtopic search
            for profile in profiles:
                subtopic = profile.get("subtopic")

                candidates = []
                if subtopic:
                    candidates = search_by_subtopic(
                        subtopic,
                        elo_range=profile.get("elo_range", [800, 2500]),
                        importance_range=profile.get("importance_range", [0.0, 1.0]),
                        state=state,
                        completed_ids=self._completed_ids,
                        skip_cooldown_ids=self._skip_cooldown_ids,
                        discarded_ids=self._discarded_ids,
                        max_results=5,
                    )
                self.slots.append({
                    "profile": profile,
                    "candidates": candidates,
                    "current_index": 0,
                    "completed": False,
                })

    def get_next(self):
        """Get the next problem to serve. Returns (slot_index, problem) or None."""
        for i, slot in enumerate(self.slots):
            if slot["completed"]:
                continue
            if slot["current_index"] < len(slot["candidates"]):
                return i, slot["candidates"][slot["current_index"]]
        return None

    def mark_completed(self, slot_index):
        """User completed a problem from this slot."""
        self.slots[slot_index]["completed"] = True
        problem = self.slots[slot_index]["candidates"][self.slots[slot_index]["current_index"]]
        self._completed_ids.add(problem["id"])

    def mark_skipped(self, slot_index):
        """User skipped the current problem — advance to next candidate, move slot to back."""
        slot = self.slots[slot_index]
        problem = slot["candidates"][slot["current_index"]]
        self._skip_cooldown_ids.add(problem["id"])
        slot["current_index"] += 1

        # Move this slot to the back of the queue
        self.slots.pop(slot_index)
        self.slots.append(slot)

    def mark_discarded(self, slot_index):
        """User discarded the current problem — never show again, advance candidate."""
        slot = self.slots[slot_index]
        problem = slot["candidates"][slot["current_index"]]
        self._discarded_ids.add(problem["id"])
        slot["current_index"] += 1

        # Move to back
        self.slots.pop(slot_index)
        self.slots.append(slot)

    def is_empty(self):
        """True if all slots are completed or exhausted."""
        for slot in self.slots:
            if not slot["completed"] and slot["current_index"] < len(slot["candidates"]):
                return False
        return True

    def summary(self):
        """Human-readable queue state."""
        lines = []
        for i, slot in enumerate(self.slots):
            profile = slot["profile"]
            status = "DONE" if slot["completed"] else f"{slot['current_index']}/{len(slot['candidates'])}"
            topic = profile.get("topic", "?")
            subtopic = profile.get("subtopic", "?")
            lines.append(f"Slot {i+1} [{status}]: {topic} > {subtopic}")
            if slot["candidates"]:
                current = slot["candidates"][min(slot["current_index"], len(slot["candidates"]) - 1)]
                lines.append(f"  Current: {current['title']} (elo={current['elo']}, imp={current['importance']})")
            else:
                lines.append(f"  No candidates found")
            lines.append("")
        return "\n".join(lines)


# ── Test harness ──────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from lib.mastery import new_user_state

    out_path = "data/output/reco_engine_test.txt"
    out_file = open(out_path, "w")

    def log(s=""):
        print(s)
        out_file.write(s + "\n")

    def run_test(label, state, topic_filter=None):
        log("=" * 60)
        log(label)
        log("=" * 60)

        queue = RecoQueue()
        queue.load_exclusions(set(), set(), set())
        queue.fill(state, topic_filter)

        log("\n--- Queue Summary ---\n")
        log(queue.summary())

        log("--- Serving problems ---\n")
        served = 0
        while not queue.is_empty() and served < 10:
            result = queue.get_next()
            if result is None:
                break
            slot_idx, problem = result
            log(f"  Serve: {problem['title']} | {problem['primary_subtopic']} | elo={problem['elo']} | imp={problem['importance']}")
            queue.mark_completed(slot_idx)
            served += 1
        log(f"\nServed {served} problems.\n\n")

    # Test 1: Fresh user
    run_test("Test 1: Fresh user (no mastery)", new_user_state())

    # Test 2: Mid-level user (Gold in foundations, Bronze elsewhere)
    mid_state = new_user_state()
    gold_subs = [
        "Frequency Counting / Hash Map Lookup", "Prefix Sums", "Complement Search (Two Sum Pattern)",
        "Sorting + Comparison", "Opposite-Direction (Converging)", "Same-Direction (Fast/Slow on Arrays)",
        "Standard Binary Search", "Stack-Based Simulation", "Monotonic Stack",
        "DFS Traversal (Inorder, Preorder, Postorder)", "BFS / Level-Order Traversal",
        "Reversal (Full and Partial)", "Fast/Slow Pointers (Cycle, Middle)",
    ]
    for sub in gold_subs:
        mid_state["subtopics"][sub] = {"score": 45.0, "attempts_count": 15, "last_attempted": time.time() - 86400 * 3}
    # Some silver
    silver_subs = [
        "Fixed-Size Window", "Variable-Size Window (Expand/Contract)",
        "Combinations / Subsets", "Permutations", "Top-K Elements",
        "BFS Shortest Path (Unweighted)", "DFS Connected Components",
    ]
    for sub in silver_subs:
        mid_state["subtopics"][sub] = {"score": 25.0, "attempts_count": 8, "last_attempted": time.time() - 86400 * 7}

    run_test("Test 2: Mid-level user (Gold foundations, Silver in mid-topics)", mid_state)

    # Test 3: Topic filter — user wants to focus on DP
    run_test("Test 3: Mid-level user filtered to Core DP", mid_state, topic_filter="Core DP")

    out_file.close()
    log(f"Output saved to {out_path}")
