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
    compute_attempt_score,
)

random.seed(42)  # reproducible

# ── Load real data ──────────────────────────────────────────────────

with open("data/core/tagged_problems.json") as f:
    tagged = json.load(f)

with open("data/core/problems.json") as f:
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
    Returns a 1-10 quality score.
    """
    expected_elo = 800 + (mastery / 100) * 1900
    gap = problem_elo - expected_elo  # positive = problem is harder than expected

    r = random.random()
    if gap > 400:
        # Way above level
        if r < 0.35: return 1   # struggled
        if r < 0.65: return 4   # solution
        if r < 0.85: return 6   # hints
        return 8                # clean
    elif gap > 150:
        # Somewhat above level
        if r < 0.15: return 2   # struggled
        if r < 0.35: return 4   # solution
        if r < 0.60: return 6   # hints
        return 8                # clean
    elif gap > -150:
        # At level
        if r < 0.05: return 2   # struggled
        if r < 0.15: return 6   # hints
        return 9                # clean
    elif gap > -400:
        # Below level
        if r < 0.05: return 7   # minor hint
        return 9                # clean
    else:
        # Way below level
        return 10               # trivial


class Simulation:
    def __init__(self, name):
        self.name = name
        self.state = new_user_state()
        self.ts = time.time()
        self.attempt_num = 0
        self.seen = set()
        print_header(f"SIMULATION: {name}")

    def attempt(self, problem_id, quality=9, days_offset=1):
        self.attempt_num += 1
        self.ts += days_offset * 86400
        self.seen.add(problem_id)

        tags = tag_lookup[problem_id]
        title = prob_lookup[problem_id]["title"]
        primary = tags["primary_subtopic"]["name"]
        imp = tags["importance"]
        old_score = self.state["subtopics"].get(primary, {}).get("score", 0.0)
        old_tier = get_subtopic_tier(old_score)

        update_mastery(self.state, problem_id, tags, quality=quality, now=self.ts)

        new_score = self.state["subtopics"][primary]["score"]
        new_tier = get_subtopic_tier(new_score)
        change = new_score - old_score

        tier_str = new_tier
        if new_tier != old_tier:
            tier_str = f"{old_tier}->{new_tier}!"

        direction = "+" if change >= 0 else ""
        print(f"  #{self.attempt_num:<3} {title[:34]:<35} {primary[:24]:<25} {imp:>4.2f} q={quality:<2} "
              f"{direction}{change:>5.2f} {new_score:>6.1f} [{tier_str}]")
        return change

    def auto_attempt(self, problem, days_offset=1):
        """Attempt with simulated quality based on mastery vs difficulty."""
        primary = problem["primary_subtopic"]["name"]
        mastery = self.state["subtopics"].get(primary, {}).get("score", 0.0)
        quality = simulate_quality(mastery, problem["difficulty"])
        return self.attempt(problem["id"], quality=quality, days_offset=days_offset)

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
    sim3.attempt(p["id"], quality=1)

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
# SIMULATION 8: Easy grinder — 500 problems, only easies, broad coverage
#   Someone who grinds tons of easy problems across all topics.
#   Should progress but plateau — easy problems give diminishing returns
#   at higher mastery due to difficulty multiplier.
# ════════════════════════════════════════════════════════════════════

sim8 = Simulation("Easy grinder — 500 easy problems, broad coverage")

# Only pick easy problems (elo < 1300)
easy_by_subtopic = {}
for sub, probs in by_subtopic.items():
    easy = [p for p in probs if p["difficulty"] < 1300]
    if easy:
        easy_by_subtopic[sub] = easy

checkpoints_8 = [100, 200, 300, 400, 500]
checkpoint_idx_8 = 0

for i in range(500):
    # Pick a random subtopic with available easy problems
    available_subs = [s for s in ALL_SUBTOPICS
                      if s in easy_by_subtopic
                      and any(p["id"] not in sim8.seen for p in easy_by_subtopic[s])]
    if not available_subs:
        print(f"  Ran out of easy problems at attempt {i+1}")
        break

    # Spread across subtopics, slight importance weighting
    imp_scores = [(s, subtopic_importance.get(s, 0.5) + random.random() * 0.3) for s in available_subs]
    imp_scores.sort(key=lambda x: -x[1])
    chosen_sub = random.choice(imp_scores[:6])[0]

    unseen = [p for p in easy_by_subtopic[chosen_sub] if p["id"] not in sim8.seen]
    if not unseen:
        continue
    problem = random.choice(unseen)

    # Easy problems: mostly clean solves, perceived as easy
    r = random.random()
    if r < 0.7:
        sim8.attempt(problem["id"], quality=9)
    elif r < 0.9:
        sim8.attempt(problem["id"], quality=6)
    else:
        sim8.attempt(problem["id"], quality=4)

    if checkpoint_idx_8 < len(checkpoints_8) and (i + 1) == checkpoints_8[checkpoint_idx_8]:
        attempted_subs = [s for s, d in sim8.state["subtopics"].items() if d["attempts_count"] > 0]
        avg_mastery = sum(sim8.state["subtopics"][s]["score"] for s in attempted_subs) / len(attempted_subs) if attempted_subs else 0
        print_subheader(f"Checkpoint at {i+1} problems (avg mastery: {avg_mastery:.1f})")
        sim8.print_scores(limit=10)
        sim8.print_topic_levels()
        checkpoint_idx_8 += 1


# ════════════════════════════════════════════════════════════════════
# SIMULATION 9: Edge cases — floor and ceiling
# ════════════════════════════════════════════════════════════════════

sim9 = Simulation("Edge cases — floor (0) and ceiling (100)")

floor_sub = "Primes / Sieve of Eratosthenes"
print_subheader("Floor: struggling from 0 — should stay at 0")
print_table_header()
for p in by_subtopic.get(floor_sub, [])[:5]:
    sim9.attempt(p["id"], quality=1)

ceil_sub = "Prefix Sums"
sim9.set_mastery(ceil_sub, 97.0)
print_subheader("Ceiling: near 100, clean solving hard problems — should cap at 100")
print_table_header()
for p in [pp for pp in by_subtopic.get(ceil_sub, []) if pp["difficulty"] > 1800][:8]:
    sim9.attempt(p["id"], quality=8)

sim9.print_scores(only_nonzero=False)


# ════════════════════════════════════════════════════════════════════
# SIMULATION 10: Hard grinder — only hard problems (elo > 2000)
#   Should struggle a lot early but difficulty multiplier rewards them.
#   Compare progression to easy grinder.
# ════════════════════════════════════════════════════════════════════

sim10 = Simulation("Hard grinder — only hard problems (elo > 2000)")

hard_by_subtopic = {}
for sub, probs in by_subtopic.items():
    hard = [p for p in probs if p["difficulty"] > 2000]
    if hard:
        hard_by_subtopic[sub] = hard

checkpoints_10 = [25, 50, 100, 150]
checkpoint_idx_10 = 0

for i in range(150):
    available_subs = [s for s in ALL_SUBTOPICS
                      if s in hard_by_subtopic
                      and any(p["id"] not in sim10.seen for p in hard_by_subtopic[s])]
    if not available_subs:
        print(f"  Ran out of hard problems at attempt {i+1}")
        break

    imp_scores = [(s, subtopic_importance.get(s, 0.5) + random.random() * 0.3) for s in available_subs]
    imp_scores.sort(key=lambda x: -x[1])
    chosen_sub = random.choice(imp_scores[:6])[0]

    unseen = [p for p in hard_by_subtopic[chosen_sub] if p["id"] not in sim10.seen]
    if not unseen:
        continue
    problem = random.choice(unseen)

    # Hard problems: lots of struggling and solution-peeking at low mastery
    sim10.auto_attempt(problem)

    if checkpoint_idx_10 < len(checkpoints_10) and (i + 1) == checkpoints_10[checkpoint_idx_10]:
        attempted_subs = [s for s, d in sim10.state["subtopics"].items() if d["attempts_count"] > 0]
        avg_mastery = sum(sim10.state["subtopics"][s]["score"] for s in attempted_subs) / len(attempted_subs) if attempted_subs else 0
        print_subheader(f"Checkpoint at {i+1} problems (avg mastery: {avg_mastery:.1f})")
        sim10.print_scores(limit=10)
        sim10.print_topic_levels()
        checkpoint_idx_10 += 1


# ════════════════════════════════════════════════════════════════════
# SIMULATION 11: Secondary subtopic gains — verify secondary gains
#   are meaningful but clearly less than primary
# ════════════════════════════════════════════════════════════════════

sim11 = Simulation("Secondary subtopic gains — primary vs secondary comparison")

# Find problems with strong secondary subtopics (weight >= 0.3)
problems_with_secondaries = [t for t in tagged
                             if t.get("secondary_subtopics")
                             and any(s["weight"] >= 0.3 for s in t["secondary_subtopics"])]

print(f"  Problems with strong secondaries (weight >= 0.3): {len(problems_with_secondaries)}")

# Do 30 problems, tracking primary vs secondary gains
primary_gains = []
secondary_gains_all = []

print_subheader("30 problems with strong secondary subtopics")
print_table_header()
for p in problems_with_secondaries[:30]:
    primary = p["primary_subtopic"]["name"]
    old_primary = sim11.state["subtopics"].get(primary, {}).get("score", 0.0)

    # Track secondary scores before
    sec_before = {}
    for sec in p.get("secondary_subtopics", []):
        sec_before[sec["name"]] = sim11.state["subtopics"].get(sec["name"], {}).get("score", 0.0)

    sim11.attempt(p["id"], quality=9)

    # Measure gains
    new_primary = sim11.state["subtopics"][primary]["score"]
    p_gain = new_primary - old_primary
    primary_gains.append(p_gain)

    for sec in p.get("secondary_subtopics", []):
        sec_gain = sim11.state["subtopics"][sec["name"]]["score"] - sec_before[sec["name"]]
        if sec_gain > 0:
            secondary_gains_all.append((sec["name"], sec["weight"], sec_gain, p_gain))

print_subheader("Primary vs Secondary gain comparison")
print(f"  Avg primary gain:   {sum(primary_gains)/len(primary_gains):.3f}")
if secondary_gains_all:
    print(f"  Avg secondary gain: {sum(g[2] for g in secondary_gains_all)/len(secondary_gains_all):.3f}")
    print(f"  Avg secondary/primary ratio: {sum(g[2]/g[3] for g in secondary_gains_all if g[3] > 0)/len([g for g in secondary_gains_all if g[3] > 0]):.3f}")
    print(f"\n  Sample secondary gains:")
    for name, weight, sec_gain, pri_gain in secondary_gains_all[:8]:
        print(f"    {name[:40]:<42} weight:{weight:.1f}  gain:{sec_gain:.3f}  (primary gained {pri_gain:.3f})")


# ════════════════════════════════════════════════════════════════════
# SIMULATION 12: Solution-only learner vs clean solver
#   Same problems, compare total mastery after 50 problems each.
# ════════════════════════════════════════════════════════════════════

sim12_clean = Simulation("Clean solver — 50 problems, all clean solves")
sim12_solution = Simulation("Solution learner — same 50 problems, all solution-peeked")

# Pick 50 diverse problems via reco engine
problems_for_12 = []
temp_state = new_user_state()
temp_seen = set()
for i in range(50):
    p = recommend_problem(temp_state, temp_seen, mode="filling_gaps")
    if p:
        problems_for_12.append(p)
        temp_seen.add(p["id"])
        # Advance temp state minimally to get diverse recommendations
        primary = p["primary_subtopic"]["name"]
        if primary not in temp_state["subtopics"]:
            temp_state["subtopics"][primary] = {"score": 5, "attempts_count": 1, "last_attempted": None}

print_table_header()
for p in problems_for_12:
    sim12_clean.attempt(p["id"], quality=9)

print_table_header()
for p in problems_for_12:
    sim12_solution.attempt(p["id"], quality=4)

overall_clean = get_overall_level(sim12_clean.state, taxonomy)
overall_solution = get_overall_level(sim12_solution.state, taxonomy)

print_subheader("Comparison: Clean vs Solution learner (50 identical problems)")
print(f"  Clean solver overall:    {overall_clean:.1f} [{get_subtopic_tier(overall_clean)}]")
print(f"  Solution learner overall: {overall_solution:.1f} [{get_subtopic_tier(overall_solution)}]")
print(f"  Ratio: {overall_clean/overall_solution:.2f}x" if overall_solution > 0 else "")

# Compare individual subtopics
clean_subs = sim12_clean.state["subtopics"]
sol_subs = sim12_solution.state["subtopics"]
print(f"\n  {'Subtopic':<42} {'Clean':>6} {'Soln':>6} {'Ratio':>6}")
print(f"  {'-'*42} {'-'*6} {'-'*6} {'-'*6}")
for sub in sorted(clean_subs.keys(), key=lambda s: -clean_subs[s]["score"]):
    c = clean_subs[sub]["score"]
    s = sol_subs.get(sub, {}).get("score", 0)
    ratio = f"{c/s:.2f}" if s > 0 else "inf"
    print(f"  {sub[:41]:<42} {c:>6.1f} {s:>6.1f} {ratio:>6}")


# ════════════════════════════════════════════════════════════════════
# SIMULATION 13: Mastery rate variance — narrow vs broad subtopic
#   Narrow (target=3) should reach Gold much faster than broad (target=18)
# ════════════════════════════════════════════════════════════════════

sim13 = Simulation("Mastery rate — narrow (target=3) vs broad (target=18) subtopic")

# Find narrow and broad subtopics from config
from lib.mastery import MASTERY_RATES, get_mastery_rate

narrow_sub = "Partitioning (Dutch National Flag)"   # target=3
broad_sub = "Frequency Counting / Hash Map Lookup"  # target=18

print(f"  Narrow: {narrow_sub} (rate: {get_mastery_rate(narrow_sub):.3f})")
print(f"  Broad:  {broad_sub} (rate: {get_mastery_rate(broad_sub):.3f})")

print_subheader(f"Narrow subtopic: {narrow_sub}")
print_table_header()
for p in by_subtopic.get(narrow_sub, [])[:12]:
    sim13.attempt(p["id"], quality=9)

print_subheader(f"Broad subtopic: {broad_sub}")
print_table_header()
for p in by_subtopic.get(broad_sub, [])[:12]:
    sim13.attempt(p["id"], quality=9)

narrow_score = sim13.state["subtopics"].get(narrow_sub, {}).get("score", 0)
broad_score = sim13.state["subtopics"].get(broad_sub, {}).get("score", 0)
print_subheader("Comparison after 12 clean solves each")
print(f"  {narrow_sub:<45} {narrow_score:>6.1f} [{get_subtopic_tier(narrow_score)}]")
print(f"  {broad_sub:<45} {broad_score:>6.1f} [{get_subtopic_tier(broad_score)}]")


# ════════════════════════════════════════════════════════════════════
# SIMULATION 14: Diminishing returns verification
#   Same clean solves at Bronze (5), Silver (25), Gold (45), Plat (65)
#   Gains should taper noticeably after Gold.
# ════════════════════════════════════════════════════════════════════

sim14 = Simulation("Diminishing returns — same solves at different mastery levels")

test_sub = "DFS Connected Components"
test_problems = [p for p in by_subtopic.get(test_sub, [])
                 if 1400 < p["difficulty"] < 1800][:20]

starting_levels = [5, 25, 45, 65, 85]

print_subheader(f"5 clean medium solves at each starting mastery in: {test_sub}")
print(f"\n  {'Start':>7} {'End':>7} {'Total Gain':>10} {'Avg/Solve':>10} {'Tier Change'}")
print(f"  {'-'*7} {'-'*7} {'-'*10} {'-'*10} {'-'*20}")

for start in starting_levels:
    # Fresh state for each starting level
    dr_state = new_user_state()
    dr_state["subtopics"][test_sub] = {"score": start, "attempts_count": 0, "last_attempted": None}
    dr_seen = set()

    old_tier = get_subtopic_tier(start)
    for p in test_problems[:5]:
        if p["id"] not in dr_seen:
            update_mastery(dr_state, p["id"], p, quality=9)
            dr_seen.add(p["id"])

    end_score = dr_state["subtopics"][test_sub]["score"]
    total_gain = end_score - start
    new_tier = get_subtopic_tier(end_score)
    tier_change = f"{old_tier}->{new_tier}" if old_tier != new_tier else old_tier
    print(f"  {start:>7.0f} {end_score:>7.1f} {total_gain:>10.2f} {total_gain/5:>10.2f} {tier_change}")


# ════════════════════════════════════════════════════════════════════
# SIMULATION 15: Single topic specialist — only Trees
#   Should hit high mastery in Trees but low overall.
#   Tests topic-level aggregation and overall score.
# ════════════════════════════════════════════════════════════════════

sim15 = Simulation("Single topic specialist — 80 problems, only Trees")

tree_subtopics = []
for topic in taxonomy["topics"]:
    if topic["name"] == "Trees":
        tree_subtopics = [s["name"] for s in topic["subtopics"]]
        break

print(f"  Tree subtopics: {tree_subtopics}")

checkpoints_15 = [20, 40, 60, 80]
checkpoint_idx_15 = 0

for i in range(80):
    p = recommend_problem(sim15.state, sim15.seen, subtopics=tree_subtopics, mode="filling_gaps")
    if not p:
        p = recommend_problem(sim15.state, sim15.seen, subtopics=tree_subtopics, mode="pushing")
    if not p:
        print(f"  Ran out of tree problems at attempt {i+1}")
        break
    sim15.auto_attempt(p)

    if checkpoint_idx_15 < len(checkpoints_15) and (i + 1) == checkpoints_15[checkpoint_idx_15]:
        print_subheader(f"Checkpoint at {i+1} problems")
        sim15.print_scores()
        sim15.print_topic_levels()
        checkpoint_idx_15 += 1


# ════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════

print_header("TEST SUITE SUMMARY")
print("""
  1.  Realistic beginner:    Reco engine serves high-importance first, scales difficulty
  2.  Experienced user:      Pre-set mastery, pushing phase with harder/niche problems
  3.  Struggle + recovery:   Drop from struggling, reco adapts to rebuild
  4.  Importance contrast:   High-importance gains >> low-importance at low mastery
  5.  Breadth vs depth:      Single subtopic focus vs broad coverage
  6.  Full 150-problem journey: Mode transitions from filling_gaps to pushing
  7.  Extended 300-problem journey: Coverage tracking, mode transitions
  8.  Easy grinder:          500 easy problems, broad coverage — should plateau
  9.  Edge cases:            Floor stays 0, ceiling caps at 100
  10. Hard grinder:          150 hard problems (elo>2000) — lots of struggling early
  11. Secondary gains:       Verify secondary subtopics gain less than primary
  12. Clean vs solution:     Same 50 problems, clean solver vs solution-peeker
  13. Mastery rate variance: Narrow subtopic (target=3) vs broad (target=18)
  14. Diminishing returns:   Same solves at Bronze/Silver/Gold/Plat/Diamond start
  15. Topic specialist:      80 Tree problems only — high Trees, low overall
""")
