"""
Persona-based mastery simulations with deliberate problem selection.

Each persona has a distinct learning style and the "LLM reco engine"
picks problems accordingly — not a scoring formula, but deliberate logic.

Personas:
  1. Slow Learner    — struggles often, sticks to easier problems, needs time
  2. Fast Learner    — clean solves, pushes hard, efficient
  3. Avg Learner     — mixed results, standard progression
  4. Targeted Learner — deep focus on Trees + DP + Graphs
  5. The Rogue       — random jumps, no structure, goes off-path
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
    get_topic_levels, get_overall_level, classify_quality,
)

random.seed(99)

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
topic_for_subtopic = {}
for topic in taxonomy["topics"]:
    for sub in topic["subtopics"]:
        subtopic_importance[sub["name"]] = sub["importance"]
        topic_for_subtopic[sub["name"]] = topic["name"]

ALL_SUBTOPICS = list(subtopic_importance.keys())

# Group subtopics by topic
subtopics_by_topic = {}
for topic in taxonomy["topics"]:
    subtopics_by_topic[topic["name"]] = [s["name"] for s in topic["subtopics"]]


# ── Printing ──────────────────────────────────────────────────────

def print_header(title):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print(f"{'='*100}")

def print_attempt(num, title, subtopic, elo, imp, quality, perceived, change, score, tier_str):
    print(f"  #{num:<3} {title[:38]:<40} {subtopic[:28]:<30} elo:{elo:>4}  imp:{imp:.2f}  "
          f"{quality:<20} {perceived:<6} {'+' if change >= 0 else ''}{change:>5.2f} → {score:>5.1f} [{tier_str}]")

def print_checkpoint(state, num, taxonomy):
    attempted = [(n, d) for n, d in state["subtopics"].items() if d["attempts_count"] > 0]
    attempted.sort(key=lambda x: -x[1]["score"])

    avg_m = sum(d["score"] for _, d in attempted) / len(attempted) if attempted else 0
    overall = get_overall_level(state, taxonomy)

    tier_counts = {"Bronze": 0, "Silver": 0, "Gold": 0, "Platinum": 0, "Diamond": 0}
    for _, d in attempted:
        tier_counts[get_subtopic_tier(d["score"])] += 1

    print(f"\n  ┌─ CHECKPOINT @ {num} problems ────────────────────────────────────────────────────")
    print(f"  │  Overall: {overall:.1f} [{get_subtopic_tier(overall)}]    Avg mastery: {avg_m:.1f}    Subtopics touched: {len(attempted)}")
    print(f"  │  Tiers: {' | '.join(f'{t}: {c}' for t, c in tier_counts.items() if c > 0)}")
    print(f"  │")
    print(f"  │  Top subtopics:")
    for name, data in attempted[:8]:
        print(f"  │    {name:<45} {data['score']:>5.1f} [{get_subtopic_tier(data['score'])}]  ({data['attempts_count']} problems)")
    if len(attempted) > 8:
        bottom = attempted[-3:]
        print(f"  │  Bottom subtopics:")
        for name, data in bottom:
            print(f"  │    {name:<45} {data['score']:>5.1f} [{get_subtopic_tier(data['score'])}]  ({data['attempts_count']} problems)")

    print(f"  │")
    topic_levels = get_topic_levels(state, taxonomy)
    print(f"  │  Topics:")
    for topic in taxonomy["topics"]:
        info = topic_levels[topic["name"]]
        if info["score"] > 0:
            print(f"  │    {topic['name']:<40} {info['score']:>5.1f} [{info['tier']}]")
    print(f"  └───────────────────────────────────────────────────────────────────────────────────")


# ── Problem pickers ───────────────────────────────────────────────

def pick_problem(state, seen, subtopics, elo_min=0, elo_max=9999, prefer_importance=True):
    """Pick a problem from given subtopics within elo range."""
    # Score subtopics
    candidates = []
    for sub in subtopics:
        if sub not in by_subtopic:
            continue
        available = [p for p in by_subtopic[sub] if p["id"] not in seen
                     and elo_min <= p["difficulty"] <= elo_max]
        if not available:
            continue
        imp = subtopic_importance.get(sub, 0.5)
        mastery = state["subtopics"].get(sub, {}).get("score", 0.0)
        attempts = state["subtopics"].get(sub, {}).get("attempts_count", 0)

        if prefer_importance:
            score = imp * (1 - mastery / 100) - min(attempts * 0.04, 0.4)
        else:
            score = random.random()
        candidates.append((sub, score, available))

    if not candidates:
        return None

    candidates.sort(key=lambda x: -x[1])
    # Pick from top few
    pick_from = candidates[:max(3, len(candidates) // 3)]
    chosen_sub, _, available = random.choice(pick_from)

    # Pick problem at appropriate difficulty within range
    mastery = state["subtopics"].get(chosen_sub, {}).get("score", 0.0)
    expected_elo = 800 + (mastery / 100) * 1900
    available.sort(key=lambda p: abs(p["difficulty"] - expected_elo))
    pool = available[:max(2, len(available) // 3)]
    return random.choice(pool)


def pick_problem_any(seen, subtopics=None, elo_min=0, elo_max=9999):
    """Pick a random problem, no mastery consideration."""
    subs = subtopics or ALL_SUBTOPICS
    all_available = []
    for sub in subs:
        if sub not in by_subtopic:
            continue
        for p in by_subtopic[sub]:
            if p["id"] not in seen and elo_min <= p["difficulty"] <= elo_max:
                all_available.append(p)
    if not all_available:
        return None
    return random.choice(all_available)


# ── Quality simulators per persona ────────────────────────────────

def quality_slow(mastery, elo):
    """Slow learner: struggles often, needs hints/solutions."""
    expected = 800 + (mastery / 100) * 1900
    gap = elo - expected
    r = random.random()
    if gap > 200:
        if r < 0.40: return True, False, True, "hard"     # struggled
        if r < 0.70: return False, True, False, "hard"     # solution
        if r < 0.90: return True, False, False, "hard"     # hints
        return False, False, False, "hard"                  # clean (rare)
    elif gap > -100:
        if r < 0.20: return True, False, True, "medium"
        if r < 0.45: return False, True, False, "medium"
        if r < 0.75: return True, False, False, "medium"
        return False, False, False, "medium"
    else:
        if r < 0.05: return True, False, True, "easy"
        if r < 0.15: return False, True, False, "easy"
        if r < 0.35: return True, False, False, "easy"
        return False, False, False, "easy"


def quality_fast(mastery, elo):
    """Fast learner: mostly clean, rarely struggles."""
    expected = 800 + (mastery / 100) * 1900
    gap = elo - expected
    r = random.random()
    if gap > 300:
        if r < 0.10: return True, False, True, "hard"
        if r < 0.25: return False, True, False, "hard"
        if r < 0.50: return True, False, False, "hard"
        return False, False, False, "hard"
    elif gap > -100:
        if r < 0.03: return True, False, True, "medium"
        if r < 0.08: return True, False, False, "medium"
        return False, False, False, "medium"
    else:
        return False, False, False, "easy"


def quality_avg(mastery, elo):
    """Average learner: balanced results."""
    expected = 800 + (mastery / 100) * 1900
    gap = elo - expected
    r = random.random()
    if gap > 300:
        if r < 0.30: return True, False, True, "hard"
        if r < 0.55: return False, True, False, "hard"
        if r < 0.80: return True, False, False, "hard"
        return False, False, False, "hard"
    elif gap > 100:
        if r < 0.10: return True, False, True, "hard"
        if r < 0.30: return False, True, False, "medium"
        if r < 0.55: return True, False, False, "medium"
        return False, False, False, "medium"
    elif gap > -200:
        if r < 0.05: return True, False, True, "medium"
        if r < 0.12: return True, False, False, "medium"
        return False, False, False, "medium"
    else:
        if r < 0.05: return True, False, False, "easy"
        return False, False, False, "easy"


def quality_targeted(mastery, elo):
    """Targeted learner: consistent, slightly above average in focus areas."""
    expected = 800 + (mastery / 100) * 1900
    gap = elo - expected
    r = random.random()
    if gap > 300:
        if r < 0.15: return True, False, True, "hard"
        if r < 0.35: return False, True, False, "hard"
        if r < 0.60: return True, False, False, "medium"
        return False, False, False, "medium"
    elif gap > 0:
        if r < 0.05: return True, False, True, "medium"
        if r < 0.15: return True, False, False, "medium"
        return False, False, False, "medium"
    else:
        if r < 0.03: return True, False, False, "easy"
        return False, False, False, "easy"


def quality_rogue(mastery, elo):
    """The rogue: inconsistent, sometimes great, sometimes terrible."""
    expected = 800 + (mastery / 100) * 1900
    gap = elo - expected
    r = random.random()
    # Rogue has high variance — sometimes nails it, sometimes fails hard
    if gap > 400:
        if r < 0.50: return True, False, True, "hard"
        if r < 0.75: return False, True, False, "hard"
        if r < 0.90: return True, False, False, "hard"
        return False, False, False, "hard"
    elif gap > 100:
        if r < 0.25: return True, False, True, "hard"
        if r < 0.45: return False, True, False, "medium"
        if r < 0.65: return True, False, False, "medium"
        return False, False, False, "medium"
    elif gap > -200:
        if r < 0.10: return True, False, True, "medium"
        if r < 0.20: return True, False, False, "medium"
        return False, False, False, "easy"
    else:
        return False, False, False, "easy"


# ── Attempt helper ────────────────────────────────────────────────

def do_attempt(state, seen, problem, quality_fn, attempt_num, ts):
    """Execute one attempt and print it."""
    pid = problem["id"]
    tags = problem
    title = prob_lookup[pid]["title"]
    primary = tags["primary_subtopic"]["name"]
    elo = tags["difficulty"]
    imp = tags["importance"]

    mastery = state["subtopics"].get(primary, {}).get("score", 0.0)
    old_tier = get_subtopic_tier(mastery)

    hints, solution, struggled, perceived = quality_fn(mastery, elo)

    seen.add(pid)
    update_mastery(state, pid, tags, hints, solution, struggled, perceived, now=ts)

    new_score = state["subtopics"][primary]["score"]
    new_tier = get_subtopic_tier(new_score)
    change = new_score - mastery
    quality = classify_quality(hints, solution, struggled)

    tier_str = new_tier
    if new_tier != old_tier:
        tier_str = f"{old_tier}→{new_tier}!"

    print_attempt(attempt_num, title, primary, elo, imp, quality, perceived, change, new_score, tier_str)
    return change


# ══════════════════════════════════════════════════════════════════
#  PERSONA 1: SLOW LEARNER
#  Struggles often. LLM reco keeps them on easier problems, doesn't
#  push too hard. Gradually expands difficulty as they build confidence.
#  Lots of solution-peeking and hints. 200 problems.
# ══════════════════════════════════════════════════════════════════

print_header("PERSONA 1: SLOW LEARNER")
print("  Struggles often, uses hints/solutions frequently.")
print("  LLM serves easy problems first, slowly increases difficulty.")
print("  Sticks to high-importance fundamentals for a long time.")

state = new_user_state()
seen = set()
ts = time.time()
n = 0

# Phase 1 (1-40): Easy problems, core fundamentals only
print(f"\n  ── Phase 1: Fundamentals (easy problems, core subtopics) ──")
core_subs = [s for s in ALL_SUBTOPICS if subtopic_importance.get(s, 0) >= 0.8]
for i in range(40):
    p = pick_problem(state, seen, core_subs, elo_max=1400)
    if not p:
        p = pick_problem(state, seen, core_subs, elo_max=1800)
    if not p:
        break
    n += 1; ts += 86400 * 2  # slow learner takes 2 days per problem
    do_attempt(state, seen, p, quality_slow, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 2 (41-80): Still easy-medium, broaden to mid-importance
print(f"\n  ── Phase 2: Broadening (easy-medium, more subtopics) ──")
mid_subs = [s for s in ALL_SUBTOPICS if subtopic_importance.get(s, 0) >= 0.6]
for i in range(40):
    p = pick_problem(state, seen, mid_subs, elo_max=1600)
    if not p:
        p = pick_problem(state, seen, mid_subs, elo_max=2000)
    if not p:
        break
    n += 1; ts += 86400 * 2
    do_attempt(state, seen, p, quality_slow, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 3 (81-130): Medium problems, all subtopics
print(f"\n  ── Phase 3: Progressing (medium problems, full coverage) ──")
for i in range(50):
    p = pick_problem(state, seen, ALL_SUBTOPICS, elo_min=1000, elo_max=1800)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS, elo_max=2000)
    if not p:
        break
    n += 1; ts += 86400 * 2
    do_attempt(state, seen, p, quality_slow, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 4 (131-200): Medium-hard, LLM pushes slightly
print(f"\n  ── Phase 4: Pushing gently (medium-hard) ──")
for i in range(70):
    p = pick_problem(state, seen, ALL_SUBTOPICS, elo_min=1200, elo_max=2000)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_slow, n, ts)

print_checkpoint(state, n, taxonomy)


# ══════════════════════════════════════════════════════════════════
#  PERSONA 2: FAST LEARNER
#  Mostly clean solves. LLM pushes harder problems quickly.
#  Efficient coverage — hits each subtopic, moves on.
# ══════════════════════════════════════════════════════════════════

print_header("PERSONA 2: FAST LEARNER")
print("  Mostly clean solves, rarely struggles.")
print("  LLM pushes difficulty quickly, broad then deep.")

state = new_user_state()
seen = set()
ts = time.time()
n = 0

# Phase 1 (1-40): Medium problems, rapid coverage of high-importance
print(f"\n  ── Phase 1: Rapid coverage (medium, high importance) ──")
high_subs = [s for s in ALL_SUBTOPICS if subtopic_importance.get(s, 0) >= 0.7]
for i in range(40):
    p = pick_problem(state, seen, high_subs, elo_min=1200, elo_max=1800)
    if not p:
        p = pick_problem(state, seen, high_subs)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_fast, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 2 (41-90): Medium-hard, expand to all subtopics
print(f"\n  ── Phase 2: Expanding + pushing (medium-hard, all subtopics) ──")
for i in range(50):
    p = pick_problem(state, seen, ALL_SUBTOPICS, elo_min=1400, elo_max=2200)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_fast, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 3 (91-150): Hard problems, deep dives into weak areas
print(f"\n  ── Phase 3: Deep dives (hard problems, targeting weaknesses) ──")
for i in range(60):
    # Target weakest subtopics
    weak_subs = sorted(ALL_SUBTOPICS,
                       key=lambda s: state["subtopics"].get(s, {}).get("score", 0.0))[:25]
    p = pick_problem(state, seen, weak_subs, elo_min=1600, elo_max=2500)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS, elo_min=1400)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_fast, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 4 (151-200): Very hard, polish
print(f"\n  ── Phase 4: Polish (hard/very hard, broad) ──")
for i in range(50):
    p = pick_problem(state, seen, ALL_SUBTOPICS, elo_min=1800, elo_max=2800)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS, elo_min=1400)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_fast, n, ts)

print_checkpoint(state, n, taxonomy)


# ══════════════════════════════════════════════════════════════════
#  PERSONA 3: AVG LEARNER
#  Mixed results. LLM gives a balanced curriculum — fundamentals
#  first, then gradual expansion. Standard pacing.
# ══════════════════════════════════════════════════════════════════

print_header("PERSONA 3: AVG LEARNER")
print("  Mixed results — some clean, some hints, occasional struggle.")
print("  LLM gives balanced curriculum, standard pacing.")

state = new_user_state()
seen = set()
ts = time.time()
n = 0

# Phase 1 (1-50): Easy-medium, high importance first
print(f"\n  ── Phase 1: Foundations (easy-medium, high importance) ──")
for i in range(50):
    high_subs = [s for s in ALL_SUBTOPICS if subtopic_importance.get(s, 0) >= 0.7]
    p = pick_problem(state, seen, high_subs, elo_max=1600)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS, elo_max=1600)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_avg, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 2 (51-120): Medium, broaden coverage
print(f"\n  ── Phase 2: Broadening (medium, all subtopics) ──")
for i in range(70):
    p = pick_problem(state, seen, ALL_SUBTOPICS, elo_min=1100, elo_max=1900)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_avg, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 3 (121-200): Medium-hard, push where strong, consolidate where weak
print(f"\n  ── Phase 3: Pushing + consolidating (medium-hard) ──")
for i in range(80):
    # Alternate: push strong subtopics harder, give weak ones easier problems
    if random.random() < 0.4:
        # Push strong
        strong_subs = sorted(ALL_SUBTOPICS,
                             key=lambda s: -state["subtopics"].get(s, {}).get("score", 0.0))[:20]
        p = pick_problem(state, seen, strong_subs, elo_min=1600, elo_max=2400)
    else:
        # Consolidate weak
        weak_subs = sorted(ALL_SUBTOPICS,
                           key=lambda s: state["subtopics"].get(s, {}).get("score", 0.0))[:30]
        p = pick_problem(state, seen, weak_subs, elo_min=1000, elo_max=1800)

    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_avg, n, ts)

print_checkpoint(state, n, taxonomy)


# ══════════════════════════════════════════════════════════════════
#  PERSONA 4: TARGETED LEARNER
#  Focuses on Trees, DP, and Graphs. Goes deep in these topics.
#  Occasionally touches other topics but 80% focused.
# ══════════════════════════════════════════════════════════════════

print_header("PERSONA 4: TARGETED LEARNER (Trees + DP + Graphs)")
print("  Deep focus on Trees, Core DP, and Graphs.")
print("  80% of problems from focus areas, 20% from other topics.")

state = new_user_state()
seen = set()
ts = time.time()
n = 0

focus_topics = ["Trees", "Core DP", "Graphs"]
focus_subs = []
other_subs = []
for sub in ALL_SUBTOPICS:
    if topic_for_subtopic.get(sub) in focus_topics:
        focus_subs.append(sub)
    else:
        other_subs.append(sub)

print(f"  Focus subtopics ({len(focus_subs)}): {', '.join(focus_subs[:8])}...")
print(f"  Other subtopics ({len(other_subs)})")

# Phase 1 (1-60): Focus area fundamentals
print(f"\n  ── Phase 1: Focus area fundamentals (easy-medium) ──")
for i in range(60):
    if random.random() < 0.85:
        p = pick_problem(state, seen, focus_subs, elo_max=1700)
    else:
        p = pick_problem(state, seen, other_subs, elo_max=1500)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_targeted, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 2 (61-130): Push focus areas harder
print(f"\n  ── Phase 2: Pushing focus areas (medium-hard) ──")
for i in range(70):
    if random.random() < 0.80:
        p = pick_problem(state, seen, focus_subs, elo_min=1300, elo_max=2200)
    else:
        p = pick_problem(state, seen, other_subs, elo_max=1800)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_targeted, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 3 (131-200): Deep mastery in focus + fill other gaps
print(f"\n  ── Phase 3: Deep mastery + filling gaps ──")
for i in range(70):
    if random.random() < 0.70:
        p = pick_problem(state, seen, focus_subs, elo_min=1500, elo_max=2600)
    else:
        p = pick_problem(state, seen, other_subs, elo_max=2000)
    if not p:
        p = pick_problem(state, seen, ALL_SUBTOPICS)
    if not p:
        break
    n += 1; ts += 86400
    do_attempt(state, seen, p, quality_targeted, n, ts)

print_checkpoint(state, n, taxonomy)


# ══════════════════════════════════════════════════════════════════
#  PERSONA 5: THE ROGUE
#  No structure. Picks random topics, random difficulties.
#  Sometimes does a hard problem at Bronze, sometimes an easy at Gold.
#  Doesn't follow recommendations — just vibes.
# ══════════════════════════════════════════════════════════════════

print_header("PERSONA 5: THE ROGUE")
print("  No structure. Random topics, random difficulties.")
print("  Ignores recommendations, just picks whatever looks interesting.")
print("  Sometimes way above level, sometimes way below.")

state = new_user_state()
seen = set()
ts = time.time()
n = 0

# Phase 1 (1-50): Random everything
print(f"\n  ── Phase 1: Random chaos ──")
for i in range(50):
    # Random elo range — sometimes easy, sometimes hard
    r = random.random()
    if r < 0.3:
        p = pick_problem_any(seen, elo_max=1300)  # easy
    elif r < 0.5:
        p = pick_problem_any(seen, elo_min=2000)   # hard
    else:
        p = pick_problem_any(seen, elo_min=1200, elo_max=2000)  # medium
    if not p:
        p = pick_problem_any(seen)
    if not p:
        break
    n += 1; ts += 86400 * random.randint(1, 4)  # inconsistent pacing
    do_attempt(state, seen, p, quality_rogue, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 2 (51-120): Gets slightly more focused but still chaotic
print(f"\n  ── Phase 2: Slightly more focused chaos ──")
for i in range(70):
    # Sometimes fixates on one subtopic for a burst
    if random.random() < 0.3 and state["subtopics"]:
        # Fixate on a random attempted subtopic
        fixate_sub = random.choice(list(state["subtopics"].keys()))
        p = pick_problem_any(seen, subtopics=[fixate_sub])
    else:
        # Still random
        r = random.random()
        if r < 0.25:
            p = pick_problem_any(seen, elo_max=1300)
        elif r < 0.45:
            p = pick_problem_any(seen, elo_min=2000)
        else:
            p = pick_problem_any(seen)
    if not p:
        p = pick_problem_any(seen)
    if not p:
        break
    n += 1; ts += 86400 * random.randint(1, 3)
    do_attempt(state, seen, p, quality_rogue, n, ts)

print_checkpoint(state, n, taxonomy)

# Phase 3 (121-200): Continues the pattern
print(f"\n  ── Phase 3: More chaos ──")
for i in range(80):
    if random.random() < 0.35 and state["subtopics"]:
        fixate_sub = random.choice(list(state["subtopics"].keys()))
        p = pick_problem_any(seen, subtopics=[fixate_sub])
    else:
        p = pick_problem_any(seen)
    if not p:
        p = pick_problem_any(seen)
    if not p:
        break
    n += 1; ts += 86400 * random.randint(1, 3)
    do_attempt(state, seen, p, quality_rogue, n, ts)

print_checkpoint(state, n, taxonomy)


# ══════════════════════════════════════════════════════════════════
#  FINAL COMPARISON
# ══════════════════════════════════════════════════════════════════

print_header("FINAL COMPARISON")
print(f"  All personas after 200 problems:")
print(f"  (See individual checkpoints above for progression details)")
