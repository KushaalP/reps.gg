"""
Monte Carlo simulation for mastery model validation.

Runs 1000 random user journeys per archetype, collects distributions
of key metrics at checkpoints, outputs percentile tables.
"""

import json
import yaml
import random
import sys
import os
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.mastery import (
    new_user_state, update_mastery, get_subtopic_tier,
    get_topic_levels, get_overall_level,
)

# ── Load data ─────────────────────────────────────────────────────

with open("data/tagged_problems.json") as f:
    tagged = json.load(f)

with open("data/problems.json") as f:
    problems = json.load(f)

with open("taxonomy.yaml") as f:
    taxonomy = yaml.safe_load(f)

tag_lookup = {t["id"]: t for t in tagged}
prob_lookup = {p["id"]: p for p in problems}

by_subtopic = {}
for t in tagged:
    sub = t["primary_subtopic"]["name"]
    if sub not in by_subtopic:
        by_subtopic[sub] = []
    by_subtopic[sub].append(t)
for sub in by_subtopic:
    by_subtopic[sub].sort(key=lambda x: x["difficulty"])

subtopic_importance = {}
for topic in taxonomy["topics"]:
    for sub in topic["subtopics"]:
        subtopic_importance[sub["name"]] = sub["importance"]

ALL_SUBTOPICS = list(subtopic_importance.keys())


# ── Prerequisites ─────────────────────────────────────────────────

with open("prerequisites.yaml") as f:
    _prereqs = yaml.safe_load(f).get("prerequisites", {})

HARD_PREREQS = {}
for sub_name, prereq_data in _prereqs.items():
    hard = prereq_data.get("hard", [])
    if hard:
        HARD_PREREQS[sub_name] = hard

PREREQ_MIN_MASTERY = 10.0  # hard prereq subtopic must be at least this to unlock


def prereqs_met(state, subtopic):
    """Check if hard prerequisites are met for a subtopic."""
    if subtopic not in HARD_PREREQS:
        return True
    for prereq in HARD_PREREQS[subtopic]:
        if state["subtopics"].get(prereq, {}).get("score", 0.0) < PREREQ_MIN_MASTERY:
            return False
    return True


# ── Reco engine ───────────────────────────────────────────────────

# Targeted learner focus topics
TARGETED_TOPICS = {"Trees", "Core DP", "Graphs"}
targeted_subs = []
other_subs = []
for topic in taxonomy["topics"]:
    for sub in topic["subtopics"]:
        if topic["name"] in TARGETED_TOPICS:
            targeted_subs.append(sub["name"])
        else:
            other_subs.append(sub["name"])

# Comfort zone topics
COMFORT_TOPICS = {"Arrays & Hashing", "Two Pointers", "Sliding Window"}
comfort_subs = []
for topic in taxonomy["topics"]:
    if topic["name"] in COMFORT_TOPICS:
        for sub in topic["subtopics"]:
            comfort_subs.append(sub["name"])

# One trick topics
ONE_TRICK_TOPICS = {"Graphs", "Core DP", "Advanced DP", "Advanced Graphs"}
one_trick_subs = []
for topic in taxonomy["topics"]:
    if topic["name"] in ONE_TRICK_TOPICS:
        for sub in topic["subtopics"]:
            one_trick_subs.append(sub["name"])

# Easy problems by subtopic (elo < 1300)
easy_by_subtopic = {}
for sub, probs in by_subtopic.items():
    easy = [p for p in probs if p["difficulty"] < 1300]
    if easy:
        easy_by_subtopic[sub] = easy

# Hard problems by subtopic (elo > 2000)
hard_by_subtopic = {}
for sub, probs in by_subtopic.items():
    hard = [p for p in probs if p["difficulty"] > 2000]
    if hard:
        hard_by_subtopic[sub] = hard


def recommend_problem(state, seen, mode="filling_gaps", subtopics=None):
    pool = subtopics or ALL_SUBTOPICS
    candidates = []
    for sub in pool:
        if sub not in by_subtopic or not by_subtopic[sub]:
            continue

        # Hard prerequisite gating (rogue ignores this)
        if mode != "rogue" and not prereqs_met(state, sub):
            continue

        imp = subtopic_importance.get(sub, 0.5)
        mastery = state["subtopics"].get(sub, {}).get("score", 0.0)
        attempts = state["subtopics"].get(sub, {}).get("attempts_count", 0)

        available_count = sum(1 for p in by_subtopic[sub] if p["id"] not in seen)
        if available_count == 0:
            continue

        if mode == "filling_gaps":
            coverage_penalty = min(attempts * 0.05, 0.5)
            score = imp * (1 - mastery / 100) * 2 - coverage_penalty + random.random() * 0.2
        elif mode == "pushing":
            coverage_penalty = min(attempts * 0.03, 0.3)
            score = (0.3 + imp * 0.7) * (1 - mastery / 150) - coverage_penalty + random.random() * 0.3
        elif mode == "rogue":
            score = random.random()
        else:
            score = random.random()

        candidates.append((sub, score, mastery))

    if not candidates:
        return None

    candidates.sort(key=lambda x: -x[1])
    if mode == "rogue":
        chosen_sub, _, mastery = random.choice(candidates)
    else:
        pick_from = candidates[:4]
        chosen_sub, _, mastery = random.choice(pick_from)

    expected_elo = 800 + (mastery / 100) * 1900

    available = [p for p in by_subtopic[chosen_sub] if p["id"] not in seen]
    if not available:
        return None

    if mode == "rogue":
        return random.choice(available)
    else:
        available.sort(key=lambda p: abs(p["difficulty"] - expected_elo))
        pick_pool = available[:max(3, len(available) // 4)]
        return random.choice(pick_pool)


# ── User archetypes ───────────────────────────────────────────────
# Each has quality_dist (how they perform) and reco_style (how problems are picked)
#
# reco_style:
#   "standard"  — normal reco engine (filling_gaps → pushing)
#   "targeted"  — focuses on 3 topics, goes deep before broadening
#   "rogue"     — random topic selection, ignores importance, chaotic difficulty

ARCHETYPES = {
    "slow_learner": {
        "description": "Struggles more often, peeks at solutions, but still progressing",
        "reco_style": "standard",
        "quality_dist": {
            "above": {"struggled": 0.25, "solution": 0.35, "hints": 0.25, "clean": 0.15},
            "at":    {"struggled": 0.10, "solution": 0.20, "hints": 0.35, "clean": 0.35},
            "below": {"struggled": 0.02, "solution": 0.08, "hints": 0.20, "clean": 0.70},
        },
    },
    "fast_learner": {
        "description": "Mostly clean solves, pushes hard, efficient",
        "reco_style": "standard",
        "quality_dist": {
            "above": {"struggled": 0.08, "solution": 0.12, "hints": 0.30, "clean": 0.50},
            "at":    {"struggled": 0.02, "solution": 0.05, "hints": 0.13, "clean": 0.80},
            "below": {"struggled": 0.00, "solution": 0.00, "hints": 0.05, "clean": 0.95},
        },
    },
    "avg_learner": {
        "description": "Typical user, balanced mix of outcomes",
        "reco_style": "standard",
        "quality_dist": {
            "above": {"struggled": 0.20, "solution": 0.25, "hints": 0.30, "clean": 0.25},
            "at":    {"struggled": 0.05, "solution": 0.12, "hints": 0.28, "clean": 0.55},
            "below": {"struggled": 0.00, "solution": 0.05, "hints": 0.10, "clean": 0.85},
        },
    },
    "targeted_learner": {
        "description": "Specs into Trees + DP + Graphs, deep focus before broadening",
        "reco_style": "targeted",
        "quality_dist": {
            "above": {"struggled": 0.15, "solution": 0.20, "hints": 0.30, "clean": 0.35},
            "at":    {"struggled": 0.03, "solution": 0.07, "hints": 0.20, "clean": 0.70},
            "below": {"struggled": 0.00, "solution": 0.02, "hints": 0.08, "clean": 0.90},
        },
    },
    "rogue": {
        "description": "Goes off-path, random topics, ignores reco — same quality as avg",
        "reco_style": "rogue",
        "quality_dist": {
            "above": {"struggled": 0.20, "solution": 0.25, "hints": 0.30, "clean": 0.25},
            "at":    {"struggled": 0.05, "solution": 0.12, "hints": 0.28, "clean": 0.55},
            "below": {"struggled": 0.00, "solution": 0.05, "hints": 0.10, "clean": 0.85},
        },
    },
    # ── Sub-rogues ────────────────────────────────────────────────
    "comfort_zone": {
        "description": "Only does Arrays, Hashing, Two Pointers — never touches graphs/DP/trees",
        "reco_style": "comfort_zone",
        "quality_dist": {
            "above": {"struggled": 0.10, "solution": 0.15, "hints": 0.25, "clean": 0.50},
            "at":    {"struggled": 0.03, "solution": 0.07, "hints": 0.15, "clean": 0.75},
            "below": {"struggled": 0.00, "solution": 0.02, "hints": 0.08, "clean": 0.90},
        },
    },
    "contest_bro": {
        "description": "Only does hards (elo>2000), skips easy/medium, fails a lot",
        "reco_style": "contest_bro",
        "quality_dist": {
            "above": {"struggled": 0.45, "solution": 0.25, "hints": 0.20, "clean": 0.10},
            "at":    {"struggled": 0.20, "solution": 0.25, "hints": 0.30, "clean": 0.25},
            "below": {"struggled": 0.05, "solution": 0.10, "hints": 0.20, "clean": 0.65},
        },
    },
    "easy_grinder": {
        "description": "Only does easy problems (elo<1300), broad coverage, mostly clean",
        "reco_style": "easy_grinder",
        "quality_dist": {
            "above": {"struggled": 0.05, "solution": 0.10, "hints": 0.25, "clean": 0.60},
            "at":    {"struggled": 0.02, "solution": 0.05, "hints": 0.13, "clean": 0.80},
            "below": {"struggled": 0.00, "solution": 0.00, "hints": 0.05, "clean": 0.95},
        },
    },
    "one_trick": {
        "description": "Specs into Graphs + DP only, nothing else",
        "reco_style": "one_trick",
        "quality_dist": {
            "above": {"struggled": 0.12, "solution": 0.18, "hints": 0.30, "clean": 0.40},
            "at":    {"struggled": 0.03, "solution": 0.07, "hints": 0.20, "clean": 0.70},
            "below": {"struggled": 0.00, "solution": 0.02, "hints": 0.08, "clean": 0.90},
        },
    },
}


def simulate_quality_archetype(archetype, mastery, problem_elo):
    """Pick quality outcome based on archetype's probability distribution."""
    expected_elo = 800 + (mastery / 100) * 1900
    gap = problem_elo - expected_elo

    if gap > 200:
        dist = archetype["quality_dist"]["above"]
    elif gap > -200:
        dist = archetype["quality_dist"]["at"]
    else:
        dist = archetype["quality_dist"]["below"]

    r = random.random()
    cumulative = 0
    for quality, prob in dist.items():
        cumulative += prob
        if r < cumulative:
            # Map to function args
            if quality == "struggled":
                perceived = "hard" if gap > 0 else "medium"
                return {"struggled": True, "perceived": perceived}
            elif quality == "solution":
                perceived = "hard" if gap > 200 else "medium"
                return {"solution": True, "perceived": perceived}
            elif quality == "hints":
                perceived = "medium"
                return {"hints": True, "perceived": perceived}
            else:  # clean
                perceived = "easy" if gap < -200 else "medium"
                return {"perceived": perceived}

    return {"perceived": "medium"}


# ── Single journey ────────────────────────────────────────────────

CHECKPOINTS = [50, 100, 150, 200, 250, 300]

def run_journey(archetype, num_problems=300):
    """Run a single user journey, return metrics at each checkpoint."""
    state = new_user_state()
    seen = set()
    ts = time.time()
    checkpoint_idx = 0
    metrics = {}
    reco_style = archetype.get("reco_style", "standard")

    for i in range(num_problems):
        attempted_subs = [s for s, d in state["subtopics"].items() if d["attempts_count"] > 0]
        avg_mastery = (sum(state["subtopics"][s]["score"] for s in attempted_subs) / len(attempted_subs)) if attempted_subs else 0

        if reco_style == "standard":
            mode = "pushing" if avg_mastery > 25 else "filling_gaps"
            p = recommend_problem(state, seen, mode=mode)

        elif reco_style == "targeted":
            # Goes one topic at a time, masters it, then moves on
            # Pick the current focus topic: lowest-mastery topic that hasn't been maxed
            topic_scores = get_topic_levels(state, taxonomy)
            # Sort topics by score, focus on the weakest one
            sorted_topics = sorted(taxonomy["topics"], key=lambda t: topic_scores[t["name"]]["score"])
            focus_topic = sorted_topics[0]["name"]
            focus_topic_subs = [s["name"] for s in sorted_topics[0]["subtopics"]]

            # Stay on this topic until it hits Silver (25+), then move on
            if topic_scores[focus_topic]["score"] >= 25:
                # Find next weakest
                for t in sorted_topics[1:]:
                    if topic_scores[t["name"]]["score"] < 25:
                        focus_topic = t["name"]
                        focus_topic_subs = [s["name"] for s in t["subtopics"]]
                        break

            mode = "pushing" if avg_mastery > 20 else "filling_gaps"
            p = recommend_problem(state, seen, mode=mode, subtopics=focus_topic_subs)
            if not p:
                p = recommend_problem(state, seen, mode=mode)

        elif reco_style == "rogue":
            if random.random() < 0.35 and attempted_subs:
                fixate_sub = random.choice(attempted_subs)
                p = recommend_problem(state, seen, mode="rogue", subtopics=[fixate_sub])
                if not p:
                    p = recommend_problem(state, seen, mode="rogue")
            else:
                p = recommend_problem(state, seen, mode="rogue")

        elif reco_style == "comfort_zone":
            # Only Arrays & Hashing, Two Pointers, Sliding Window
            mode = "pushing" if avg_mastery > 20 else "filling_gaps"
            p = recommend_problem(state, seen, mode=mode, subtopics=comfort_subs)

        elif reco_style == "contest_bro":
            # Only hard problems (elo > 2000), random subtopics
            available_hard_subs = [s for s in ALL_SUBTOPICS
                                   if s in hard_by_subtopic
                                   and any(pp["id"] not in seen for pp in hard_by_subtopic[s])]
            if available_hard_subs:
                chosen_sub = random.choice(available_hard_subs)
                unseen = [pp for pp in hard_by_subtopic[chosen_sub] if pp["id"] not in seen]
                p = random.choice(unseen) if unseen else None
            else:
                p = None

        elif reco_style == "easy_grinder":
            # Only easy problems (elo < 1300), spread across subtopics
            available_easy_subs = [s for s in ALL_SUBTOPICS
                                   if s in easy_by_subtopic
                                   and any(pp["id"] not in seen for pp in easy_by_subtopic[s])]
            if available_easy_subs:
                # Slight importance weighting
                weighted = [(s, subtopic_importance.get(s, 0.5) + random.random() * 0.3)
                            for s in available_easy_subs]
                weighted.sort(key=lambda x: -x[1])
                chosen_sub = random.choice(weighted[:6])[0]
                unseen = [pp for pp in easy_by_subtopic[chosen_sub] if pp["id"] not in seen]
                p = random.choice(unseen) if unseen else None
            else:
                p = None

        elif reco_style == "one_trick":
            # Only Graphs + DP — ignores prereqs (they just dive in)
            mode = "pushing" if avg_mastery > 20 else "filling_gaps"
            p = recommend_problem(state, seen, mode="rogue", subtopics=one_trick_subs)

        else:
            p = recommend_problem(state, seen, mode="filling_gaps")

        if not p:
            break

        primary = p["primary_subtopic"]["name"]
        mastery = state["subtopics"].get(primary, {}).get("score", 0.0)
        result = simulate_quality_archetype(archetype, mastery, p["difficulty"])

        ts += 86400
        seen.add(p["id"])
        update_mastery(
            state, p["id"], p,
            used_hints=result.get("hints", False),
            looked_at_solution=result.get("solution", False),
            struggled=result.get("struggled", False),
            perceived_difficulty=result["perceived"],
            now=ts,
        )

        if checkpoint_idx < len(CHECKPOINTS) and (i + 1) == CHECKPOINTS[checkpoint_idx]:
            attempted_subs = [s for s, d in state["subtopics"].items() if d["attempts_count"] > 0]
            avg_m = (sum(state["subtopics"][s]["score"] for s in attempted_subs) / len(attempted_subs)) if attempted_subs else 0
            overall = get_overall_level(state, taxonomy)

            tier_counts = {"Bronze": 0, "Silver": 0, "Gold": 0, "Platinum": 0, "Diamond": 0}
            for s, d in state["subtopics"].items():
                tier_counts[get_subtopic_tier(d["score"])] += 1

            metrics[CHECKPOINTS[checkpoint_idx]] = {
                "overall": overall,
                "avg_mastery": avg_m,
                "subtopics_touched": len(attempted_subs),
                "tier_counts": tier_counts,
            }
            checkpoint_idx += 1

    return metrics


# ── Monte Carlo runner ────────────────────────────────────────────

def percentile(sorted_values, p):
    """Get the p-th percentile from a sorted list."""
    if not sorted_values:
        return 0
    idx = int(len(sorted_values) * p / 100)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]


def run_monte_carlo(archetype_name, archetype, n_runs=500, num_problems=300):
    """Run n_runs journeys for an archetype, collect distributions."""
    checkpoint_data = {cp: defaultdict(list) for cp in CHECKPOINTS}

    for run in range(n_runs):
        metrics = run_journey(archetype, num_problems)
        for cp, data in metrics.items():
            checkpoint_data[cp]["overall"].append(data["overall"])
            checkpoint_data[cp]["avg_mastery"].append(data["avg_mastery"])
            checkpoint_data[cp]["subtopics_touched"].append(data["subtopics_touched"])
            for tier, count in data["tier_counts"].items():
                checkpoint_data[cp][f"tier_{tier}"].append(count)

    return checkpoint_data


def print_percentile_table(name, description, data):
    """Print a formatted percentile table for one archetype."""
    print(f"\n{'='*100}")
    print(f"  {name.upper()} — {description}")
    print(f"  ({N_RUNS} journeys, {NUM_PROBLEMS} problems each)")
    print(f"{'='*100}")

    # Overall mastery table
    print(f"\n  Overall Mastery:")
    print(f"  {'Problems':>10} {'p10':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p90':>8} {'mean':>8}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for cp in CHECKPOINTS:
        if cp not in data or not data[cp]["overall"]:
            continue
        vals = sorted(data[cp]["overall"])
        mean = sum(vals) / len(vals)
        print(f"  {cp:>10} {percentile(vals, 10):>8.1f} {percentile(vals, 25):>8.1f} "
              f"{percentile(vals, 50):>8.1f} {percentile(vals, 75):>8.1f} {percentile(vals, 90):>8.1f} {mean:>8.1f}")

    # Avg subtopic mastery table
    print(f"\n  Avg Subtopic Mastery:")
    print(f"  {'Problems':>10} {'p10':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p90':>8} {'mean':>8}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for cp in CHECKPOINTS:
        if cp not in data or not data[cp]["avg_mastery"]:
            continue
        vals = sorted(data[cp]["avg_mastery"])
        mean = sum(vals) / len(vals)
        print(f"  {cp:>10} {percentile(vals, 10):>8.1f} {percentile(vals, 25):>8.1f} "
              f"{percentile(vals, 50):>8.1f} {percentile(vals, 75):>8.1f} {percentile(vals, 90):>8.1f} {mean:>8.1f}")

    # Subtopics touched
    print(f"\n  Subtopics Touched:")
    print(f"  {'Problems':>10} {'p10':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p90':>8}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for cp in CHECKPOINTS:
        if cp not in data or not data[cp]["subtopics_touched"]:
            continue
        vals = sorted(data[cp]["subtopics_touched"])
        print(f"  {cp:>10} {percentile(vals, 10):>8} {percentile(vals, 25):>8} "
              f"{percentile(vals, 50):>8} {percentile(vals, 75):>8} {percentile(vals, 90):>8}")

    # Tier distribution at final checkpoint
    final_cp = max(cp for cp in CHECKPOINTS if cp in data and data[cp]["overall"])
    print(f"\n  Tier Distribution at {final_cp} problems (median counts):")
    for tier in ["Bronze", "Silver", "Gold", "Platinum", "Diamond"]:
        key = f"tier_{tier}"
        if key in data[final_cp]:
            vals = sorted(data[final_cp][key])
            med = percentile(vals, 50)
            p10 = percentile(vals, 10)
            p90 = percentile(vals, 90)
            bar = "█" * int(med)
            print(f"    {tier:<10} p10:{p10:>3}  median:{med:>3}  p90:{p90:>3}  {bar}")

    # What tier is the median user at each checkpoint?
    print(f"\n  Median User Tier Progression:")
    for cp in CHECKPOINTS:
        if cp not in data or not data[cp]["overall"]:
            continue
        vals = sorted(data[cp]["overall"])
        med = percentile(vals, 50)
        tier = get_subtopic_tier(med)
        print(f"    {cp:>4} problems → {med:>5.1f} [{tier}]")


# ── Main ──────────────────────────────────────────────────────────

N_RUNS = 500
NUM_PROBLEMS = 300

if __name__ == "__main__":
    start = time.time()

    all_data = {}
    for name, archetype in ARCHETYPES.items():
        print(f"\nRunning {name}... ({N_RUNS} journeys)", flush=True)
        data = run_monte_carlo(name, archetype, n_runs=N_RUNS, num_problems=NUM_PROBLEMS)
        all_data[name] = data
        print_percentile_table(name, archetype["description"], data)

    # Cross-archetype comparison
    print(f"\n{'='*100}")
    print(f"  CROSS-ARCHETYPE COMPARISON AT {NUM_PROBLEMS} PROBLEMS")
    print(f"{'='*100}")
    print(f"\n  {'Archetype':<20} {'p10':>8} {'p25':>8} {'Median':>8} {'p75':>8} {'p90':>8} {'Mean':>8}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    for name in ARCHETYPES:
        data = all_data[name]
        # Find the latest checkpoint that has data
        available_cps = [cp for cp in CHECKPOINTS if cp in data and data[cp].get("overall")]
        if not available_cps:
            print(f"  {name:<20} {'(no data)':>8}")
            continue
        final_cp = max(available_cps)
        vals = sorted(data[final_cp]["overall"])
        mean = sum(vals) / len(vals)
        suffix = f" ({final_cp}p)" if final_cp != NUM_PROBLEMS else ""
        print(f"  {name:<20} {percentile(vals, 10):>8.1f} {percentile(vals, 25):>8.1f} "
              f"{percentile(vals, 50):>8.1f} {percentile(vals, 75):>8.1f} {percentile(vals, 90):>8.1f} {mean:>8.1f}{suffix}")

    elapsed = time.time() - start
    print(f"\n  Total time: {elapsed:.1f}s")
