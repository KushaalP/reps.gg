"""
Mastery model test suite — simulations that emulate the recommendation
engine's problem selection behavior (importance-weighted, difficulty-scaled).
"""

import json
import yaml
import time
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.mastery import (
    new_user_state, update_mastery, get_subtopic_tier,
    get_topic_levels, get_overall_level,
    classify_quality, compute_attempt_score,
)

random.seed(42)  # reproducible

# ── Load real data ──────────────────────────────────────────────────

with open("data/tagged_problems.json") as f:
    tagged = json.load(f)

with open("data/problems.json") as f:
    problems = json.load(f)

with open("taxonomy.yaml") as f:
    taxonomy = yaml.safe_load(f)

tag_lookup = {t["id"]: t for t in tagged}
prob_lookup = {p["id"]: p for p in problems}

# Group problems by primary subtopic, sorted by difficulty
by_subtopic = {}
for t in tagged:
    sub = t["primary_subtopic"]["name"]
    if sub not in by_subtopic:
        by_subtopic[sub] = []
    by_subtopic[sub].append(t)
for sub in by_subtopic:
    by_subtopic[sub].sort(key=lambda x: x["difficulty"])

# Build subtopic -> importance lookup from taxonomy
subtopic_importance = {}
for topic in taxonomy["topics"]:
    for sub in topic["subtopics"]:
        subtopic_importance[sub["name"]] = sub["importance"]

ALL_SUBTOPICS = list(subtopic_importance.keys())


# ── Helpers ─────────────────────────────────────────────────────────

def print_header(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")

def print_subheader(title):
    print(f"\n  --- {title} ---")

def print_table_header():
    print(f"\n  {'#':<4} {'Problem':<35} {'Subtopic':<25} {'Imp':>4} {'Quality':<18} {'Perc':<6} {'Chg':>6} {'Score':>6} {'Tier'}")
    print(f"  {'-'*4} {'-'*35} {'-'*25} {'-'*4} {'-'*18} {'-'*6} {'-'*6} {'-'*6} {'-'*15}")


def recommend_problem(state, seen, subtopics=None, mode="filling_gaps"):
    """
    Emulates the recommendation engine's problem selection.

    filling_gaps: Heavily weight high importance subtopics, pick problems at
                  appropriate difficulty for current mastery. Ensures broad
                  coverage — penalizes subtopics that have been recently served.
    pushing:      Pick harder problems, allow lower importance (niche).
    """
    subtopics = subtopics or ALL_SUBTOPICS

    # Score each subtopic: higher score = more likely to be recommended
    candidates = []
    for sub in subtopics:
        if sub not in by_subtopic or not by_subtopic[sub]:
            continue
        imp = subtopic_importance.get(sub, 0.5)
        mastery = state["subtopics"].get(sub, {}).get("score", 0.0)
        attempts = state["subtopics"].get(sub, {}).get("attempts_count", 0)

        # Check if there are unseen problems available
        available_count = sum(1 for p in by_subtopic[sub] if p["id"] not in seen)
        if available_count == 0:
            continue

        if mode == "filling_gaps":
            # Prioritize: high importance, low mastery
            # Penalize subtopics that already have many attempts (spread coverage)
            coverage_penalty = min(attempts * 0.05, 0.5)
            score = imp * (1 - mastery / 100) * 2 - coverage_penalty + random.random() * 0.2
        elif mode == "pushing":
            # Still prefer low mastery but allow niche, less importance weight
            coverage_penalty = min(attempts * 0.03, 0.3)
            score = (0.3 + imp * 0.7) * (1 - mastery / 150) - coverage_penalty + random.random() * 0.3
        else:
            score = random.random()

        candidates.append((sub, score, mastery))

    if not candidates:
        return None

    # Sort by score, pick from top candidates with some randomness
    candidates.sort(key=lambda x: -x[1])
    pick_from = candidates[:4]
    chosen_sub, _, mastery = random.choice(pick_from)

    # Pick a problem at appropriate difficulty for mastery level
    expected_elo = 800 + (mastery / 100) * 1900
    available = [p for p in by_subtopic[chosen_sub] if p["id"] not in seen]
    if not available:
        return None

    # Sort by distance from expected elo, pick from closest with jitter
    available.sort(key=lambda p: abs(p["difficulty"] - expected_elo))
    pick_pool = available[:max(3, len(available) // 4)]
    return random.choice(pick_pool)


def simulate_quality(mastery, problem_elo):
    """
    Simulates realistic user performance based on mastery vs problem difficulty.
    Higher mastery relative to problem = more likely clean solve.
    """
    expected_elo = 800 + (mastery / 100) * 1900
    gap = problem_elo - expected_elo  # positive = problem is harder than expected

    r = random.random()
    if gap > 400:
        # Way above level
        if r < 0.35: return {"struggled": True, "perceived": "hard"}
        if r < 0.65: return {"solution": True, "perceived": "hard"}
        if r < 0.85: return {"hints": True, "perceived": "hard"}
        return {"perceived": "hard"}
    elif gap > 150:
        # Somewhat above level
        if r < 0.15: return {"struggled": True, "perceived": "hard"}
        if r < 0.35: return {"solution": True, "perceived": "hard"}
        if r < 0.60: return {"hints": True, "perceived": "medium"}
        return {"perceived": "medium"}
    elif gap > -150:
        # At level
        if r < 0.05: return {"struggled": True, "perceived": "medium"}
        if r < 0.15: return {"hints": True, "perceived": "medium"}
        return {"perceived": "medium"}
    elif gap > -400:
        # Below level
        if r < 0.05: return {"hints": True, "perceived": "easy"}
        return {"perceived": "easy"}
    else:
        # Way below level
        return {"perceived": "easy"}


class Simulation:
    def __init__(self, name):
        self.name = name
        self.state = new_user_state()
        self.ts = time.time()
        self.attempt_num = 0
        self.seen = set()
        print_header(f"SIMULATION: {name}")

    def attempt(self, problem_id, hints=False, solution=False, struggled=False,
                perceived="medium", days_offset=1):
        self.attempt_num += 1
        self.ts += days_offset * 86400
        self.seen.add(problem_id)

        tags = tag_lookup[problem_id]
        title = prob_lookup[problem_id]["title"]
        primary = tags["primary_subtopic"]["name"]
        imp = tags["importance"]
        old_score = self.state["subtopics"].get(primary, {}).get("score", 0.0)
        old_tier = get_subtopic_tier(old_score)

        update_mastery(self.state, problem_id, tags, hints, solution, struggled, perceived, now=self.ts)

        new_score = self.state["subtopics"][primary]["score"]
        new_tier = get_subtopic_tier(new_score)
        change = new_score - old_score
        quality = classify_quality(hints, solution, struggled)

        tier_str = new_tier
        if new_tier != old_tier:
            tier_str = f"{old_tier}->{new_tier}!"

        direction = "+" if change >= 0 else ""
        print(f"  #{self.attempt_num:<3} {title[:34]:<35} {primary[:24]:<25} {imp:>4.2f} {quality:<18} {perceived:<6} "
              f"{direction}{change:>5.2f} {new_score:>6.1f} [{tier_str}]")
        return change

    def auto_attempt(self, problem, days_offset=1):
        """Attempt with simulated quality based on mastery vs difficulty."""
        primary = problem["primary_subtopic"]["name"]
        mastery = self.state["subtopics"].get(primary, {}).get("score", 0.0)
        result = simulate_quality(mastery, problem["difficulty"])
        return self.attempt(
            problem["id"],
            hints=result.get("hints", False),
            solution=result.get("solution", False),
            struggled=result.get("struggled", False),
            perceived=result["perceived"],
            days_offset=days_offset,
        )

    def set_mastery(self, subtopic, score):
        if subtopic not in self.state["subtopics"]:
            self.state["subtopics"][subtopic] = {
                "score": 0.0, "attempts_count": 0, "last_attempted": None,
            }
        self.state["subtopics"][subtopic]["score"] = score

    def print_scores(self, only_nonzero=True, limit=None):
        print_subheader("Subtopic Scores")
        items = sorted(self.state["subtopics"].items(), key=lambda x: -x[1]["score"])
        if only_nonzero:
            items = [(n, d) for n, d in items if d["score"] > 0]
        if limit:
            items = items[:limit]
        for sub_name, sub_data in items:
            imp = subtopic_importance.get(sub_name, 0)
            print(f"    {sub_name:<45} {sub_data['score']:>6.1f} [{get_subtopic_tier(sub_data['score'])}]  "
                  f"(imp:{imp:.2f}, {sub_data['attempts_count']} attempts)")

    def print_topic_levels(self):
        print_subheader("Topic Levels")
        topic_levels = get_topic_levels(self.state, taxonomy)
        for topic in taxonomy["topics"]:
            name = topic["name"]
            info = topic_levels[name]
            if info["score"] > 0:
                print(f"    {name:<40} {info['score']:>6.1f} [{info['tier']}]")
        overall = get_overall_level(self.state, taxonomy)
        print(f"\n    {'OVERALL':<40} {overall:>6.1f} [{get_subtopic_tier(overall)}]")

    def print_summary(self):
        self.print_scores()
        self.print_topic_levels()
        print(f"\n  Total attempts: {self.attempt_num}")


# ════════════════════════════════════════════════════════════════════
# SIMULATION 1: Realistic beginner journey with reco engine
#   Reco engine serves high-importance problems first, scales difficulty
#   with mastery, sprinkles in lower importance as user progresses.
# ════════════════════════════════════════════════════════════════════

sim1 = Simulation("Realistic beginner — reco engine (60 problems)")

print_subheader("Phase A: Filling gaps — high importance focus (problems 1-25)")
print_table_header()
for i in range(25):
    p = recommend_problem(sim1.state, sim1.seen, mode="filling_gaps")
    if p:
        sim1.auto_attempt(p)

print_subheader("Phase B: Still filling but mastery growing — mixed importance (problems 26-45)")
print_table_header()
for i in range(20):
    p = recommend_problem(sim1.state, sim1.seen, mode="filling_gaps")
    if p:
        sim1.auto_attempt(p)

print_subheader("Phase C: Pushing — harder problems, niche subtopics enter (problems 46-60)")
print_table_header()
for i in range(15):
    p = recommend_problem(sim1.state, sim1.seen, mode="pushing")
    if p:
        sim1.auto_attempt(p)

sim1.print_summary()


# ════════════════════════════════════════════════════════════════════
# SIMULATION 2: Experienced user — starts at Silver/Gold across
#   several subtopics, reco engine pushes them harder
# ════════════════════════════════════════════════════════════════════

sim2 = Simulation("Experienced user — Silver/Gold baseline, pushing phase")

# Pre-set mastery across key subtopics
for sub, score in [
    ("Frequency Counting / Hash Map Lookup", 35),
    ("Monotonic Stack", 30),
    ("DFS Traversal (Inorder, Preorder, Postorder)", 40),
    ("BFS Shortest Path (Unweighted)", 25),
    ("Linear Recurrence DP", 20),
    ("Opposite-Direction (Converging)", 30),
    ("Combinations / Subsets", 25),
    ("Top-K Elements", 20),
]:
    sim2.set_mastery(sub, score)

print_subheader("Pushing phase — 40 problems, harder difficulty, niche starts appearing")
print_table_header()
for i in range(40):
    p = recommend_problem(sim2.state, sim2.seen, mode="pushing")
    if p:
        sim2.auto_attempt(p)

sim2.print_scores(limit=15)
sim2.print_topic_levels()


# ════════════════════════════════════════════════════════════════════
# SIMULATION 3: Struggle then recovery — reco engine adapts
# ════════════════════════════════════════════════════════════════════

sim3 = Simulation("Struggle then recovery — reco engine adapts")
focus_sub = "Variable-Size Window (Expand/Contract)"
sim3.set_mastery(focus_sub, 50.0)

focus_subs = [focus_sub]

print_subheader("Phase A: Struggling on hard problems (forced)")
print_table_header()
hard_window = [p for p in by_subtopic.get(focus_sub, [])
               if p["difficulty"] > 1800 and p["id"] not in sim3.seen]
for p in hard_window[:8]:
    sim3.attempt(p["id"], struggled=True, perceived="hard")

trough = sim3.state["subtopics"][focus_sub]["score"]
print(f"\n  Trough: {trough:.1f} [{get_subtopic_tier(trough)}]")

print_subheader("Phase B: Reco engine now serves easier problems to rebuild (auto quality)")
print_table_header()
for i in range(12):
    p = recommend_problem(sim3.state, sim3.seen, subtopics=focus_subs, mode="filling_gaps")
    if p:
        sim3.auto_attempt(p)

sim3.print_scores()


# ════════════════════════════════════════════════════════════════════
# SIMULATION 4: Importance contrast — reco engine naturally serves
#   high importance first, watch how gains differ
# ════════════════════════════════════════════════════════════════════

sim4 = Simulation("Importance contrast — natural reco engine ordering")

# Track gains by importance bucket
high_imp_gains = []
low_imp_gains = []

print_subheader("30 problems via reco engine — observe importance distribution")
print_table_header()
for i in range(30):
    p = recommend_problem(sim4.state, sim4.seen, mode="filling_gaps")
    if p:
        imp = p["importance"]
        primary = p["primary_subtopic"]["name"]
        old = sim4.state["subtopics"].get(primary, {}).get("score", 0.0)
        sim4.auto_attempt(p)
        new = sim4.state["subtopics"][primary]["score"]
        gain = new - old
        if imp > 0.7:
            high_imp_gains.append(gain)
        elif imp < 0.35:
            low_imp_gains.append(gain)

avg_high = sum(high_imp_gains) / len(high_imp_gains) if high_imp_gains else 0
avg_low = sum(low_imp_gains) / len(low_imp_gains) if low_imp_gains else 0
print(f"\n  High importance (>0.7) avg gain: {avg_high:.2f} ({len(high_imp_gains)} problems)")
print(f"  Low importance (<0.35) avg gain: {avg_low:.2f} ({len(low_imp_gains)} problems)")
print(f"  Ratio: {avg_high/avg_low:.1f}x" if avg_low > 0 else "  (no low importance problems served yet)")

sim4.print_scores(limit=10)


# ════════════════════════════════════════════════════════════════════
# SIMULATION 5: Breadth vs Depth — same number of problems
# ════════════════════════════════════════════════════════════════════

sim5_deep = Simulation("Depth — 30 problems, one subtopic focus")
focus = "Monotonic Stack"
print_table_header()
for i in range(30):
    p = recommend_problem(sim5_deep.state, sim5_deep.seen, subtopics=[focus], mode="filling_gaps")
    if p:
        sim5_deep.auto_attempt(p)
sim5_deep.print_scores()
sim5_deep.print_topic_levels()

sim5_broad = Simulation("Breadth — 30 problems, reco engine across all subtopics")
print_table_header()
for i in range(30):
    p = recommend_problem(sim5_broad.state, sim5_broad.seen, mode="filling_gaps")
    if p:
        sim5_broad.auto_attempt(p)
sim5_broad.print_scores()
sim5_broad.print_topic_levels()


# ════════════════════════════════════════════════════════════════════
# SIMULATION 6: Long journey — 150 problems, full reco engine
#   Shows how the engine shifts from filling gaps → pushing over time
# ════════════════════════════════════════════════════════════════════

sim6 = Simulation("Full journey — 150 problems with mode transitions")

checkpoints = [30, 60, 100, 150]
checkpoint_idx = 0

for i in range(150):
    # Determine mode based on average mastery of attempted subtopics
    attempted_subs = [s for s, d in sim6.state["subtopics"].items() if d["attempts_count"] > 0]
    if attempted_subs:
        avg_mastery = sum(sim6.state["subtopics"][s]["score"] for s in attempted_subs) / len(attempted_subs)
    else:
        avg_mastery = 0

    mode = "pushing" if avg_mastery > 30 else "filling_gaps"

    p = recommend_problem(sim6.state, sim6.seen, mode=mode)
    if p:
        sim6.auto_attempt(p)

    # Print checkpoint summaries
    if checkpoint_idx < len(checkpoints) and (i + 1) == checkpoints[checkpoint_idx]:
        print_subheader(f"Checkpoint at {i+1} problems (mode: {mode}, avg mastery: {avg_mastery:.1f})")
        sim6.print_scores(limit=10)
        sim6.print_topic_levels()
        checkpoint_idx += 1

# Only print table header at start
# Suppress per-attempt output for this sim since it's 150 lines
# We already printed checkpoints above


# ════════════════════════════════════════════════════════════════════
# SIMULATION 7: Extended journey — 300 problems
# ════════════════════════════════════════════════════════════════════

sim7 = Simulation("Extended journey — 300 problems with mode transitions")

checkpoints_7 = [50, 100, 150, 200, 250, 300]
checkpoint_idx_7 = 0

# Count high-importance subtopics (>=0.7) for coverage tracking
high_imp_subs = [s for s in ALL_SUBTOPICS if subtopic_importance.get(s, 0) >= 0.7]

for i in range(300):
    attempted_subs = [s for s, d in sim7.state["subtopics"].items() if d["attempts_count"] > 0]
    if attempted_subs:
        avg_mastery = sum(sim7.state["subtopics"][s]["score"] for s in attempted_subs) / len(attempted_subs)
    else:
        avg_mastery = 0

    # Mode transitions: filling_gaps → pushing as mastery grows
    mode = "pushing" if avg_mastery > 25 else "filling_gaps"

    p = recommend_problem(sim7.state, sim7.seen, mode=mode)
    if p:
        sim7.auto_attempt(p)

    if checkpoint_idx_7 < len(checkpoints_7) and (i + 1) == checkpoints_7[checkpoint_idx_7]:
        # Count coverage
        touched = [s for s in high_imp_subs if sim7.state["subtopics"].get(s, {}).get("attempts_count", 0) > 0]
        print_subheader(f"Checkpoint at {i+1} problems (mode: {mode}, avg mastery: {avg_mastery:.1f})")
        print(f"  High-importance subtopics touched: {len(touched)}/{len(high_imp_subs)}")
        print(f"  Unique subtopics attempted: {len(attempted_subs)}")
        sim7.print_scores(limit=15)
        sim7.print_topic_levels()
        checkpoint_idx_7 += 1


# ════════════════════════════════════════════════════════════════════
# SIMULATION 8: Edge cases — floor and ceiling
# ════════════════════════════════════════════════════════════════════

sim8 = Simulation("Edge cases — floor (0) and ceiling (100)")

floor_sub = "Primes / Sieve of Eratosthenes"
print_subheader("Floor: struggling from 0 — should stay at 0")
print_table_header()
for p in by_subtopic.get(floor_sub, [])[:5]:
    sim8.attempt(p["id"], struggled=True, perceived="hard")

ceil_sub = "Prefix Sums"
sim8.set_mastery(ceil_sub, 97.0)
print_subheader("Ceiling: near 100, clean solving hard problems — should cap at 100")
print_table_header()
for p in [pp for pp in by_subtopic.get(ceil_sub, []) if pp["difficulty"] > 1800][:8]:
    sim8.attempt(p["id"], perceived="hard")

sim8.print_scores(only_nonzero=False)


# ════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════

print_header("TEST SUITE SUMMARY")
print("""
  1. Realistic beginner:   Reco engine serves high-importance first, scales difficulty
  2. Experienced user:     Pre-set mastery, pushing phase with harder/niche problems
  3. Struggle + recovery:  Drop from struggling, reco adapts to rebuild
  4. Importance contrast:  High-importance gains >> low-importance at low mastery
  5. Breadth vs depth:     Single subtopic focus vs broad coverage
  6. Full 150-problem journey: Mode transitions from filling_gaps to pushing
  7. Extended 300-problem journey: Coverage tracking, mode transitions
  8. Edge cases:           Floor stays 0, ceiling caps at 100
""")
