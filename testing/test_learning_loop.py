"""
Simulate a realistic learning path using the LLM reco engine.
20 rounds × 10 slots = ~200 problems, 20 LLM calls.
"""

import json
import random
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.mastery import new_user_state, update_mastery, get_subtopic_tier, get_overall_level, get_topic_levels
from lib.reco_engine import RecoQueue, TAG_LOOKUP, TAXONOMY
from dotenv import load_dotenv

load_dotenv()

# ── Learner profiles (quality distributions) ─────────────────────

PROFILES = {
    "realistic": {
        "description": "Realistic mix — mostly hints, some clean, occasional struggles",
        "quality_weights": {
            # (used_hints, looked_at_solution, struggled)
            "clean":    (False, False, False),
            "hints":    (True,  False, False),
            "solution": (False, True,  False),
            "struggled": (False, False, True),
        },
        "quality_dist": [
            ("clean",    0.30),
            ("hints",    0.40),
            ("solution", 0.20),
            ("struggled", 0.10),
        ],
        "pick_dist": [0.70, 0.20, 0.10],  # prob of picking 1st, 2nd, 3rd candidate
    },
}


def pick_quality(profile):
    """Sample a quality outcome from the profile distribution."""
    r = random.random()
    cumulative = 0
    for name, prob in profile["quality_dist"]:
        cumulative += prob
        if r < cumulative:
            return name, profile["quality_weights"][name]
    # fallback
    last = profile["quality_dist"][-1]
    return last[0], profile["quality_weights"][last[0]]


def pick_candidate(candidates, profile):
    """Pick a candidate from the list based on pick_dist."""
    if not candidates:
        return None
    pick_probs = profile["pick_dist"]
    r = random.random()
    cumulative = 0
    for i, prob in enumerate(pick_probs):
        cumulative += prob
        if r < cumulative:
            return candidates[min(i, len(candidates) - 1)]
    return candidates[0]


# ── Main simulation ──────────────────────────────────────────────

def run_learning_loop(profile_name="realistic", num_rounds=20, seed=42):
    random.seed(seed)
    profile = PROFILES[profile_name]
    state = new_user_state()
    completed_ids = set()
    os.makedirs("data/output", exist_ok=True)
    out_path = "data/output/learning_loop.txt"
    out_file = open(out_path, "w")

    def log(s=""):
        print(s)
        out_file.write(s + "\n")
        out_file.flush()

    log(f"Learning Loop Simulation: {profile_name}")
    log(f"Profile: {profile['description']}")
    log(f"Rounds: {num_rounds}, Slots per round: 10")
    log(f"Seed: {seed}")
    log("=" * 80)

    total_problems = 0

    for round_num in range(1, num_rounds + 1):
        log(f"\n{'─' * 80}")
        log(f"ROUND {round_num}")
        log(f"{'─' * 80}")

        # Build queue
        queue = RecoQueue()
        queue.load_exclusions(completed_ids, set(), set())
        queue.fill(state)

        round_problems = 0

        for slot_idx, slot in enumerate(queue.slots):
            candidates = slot["candidates"]
            slot_profile = slot["profile"]
            subtopic = slot_profile.get("subtopic", "?")
            topic = slot_profile.get("topic", "?")

            # Log all candidates in this slot
            elo_range = slot_profile.get("elo_range")
            imp_range = slot_profile.get("imp_range", [0, 1.0])
            if elo_range:
                cap_str = f", cap={elo_range[1]}" if len(elo_range) > 1 and elo_range[1] is not None else ""
                elo_str = f"floor={elo_range[0]}{cap_str}"
            else:
                elo_str = "none"
            log(f"  Slot {slot_idx+1}: {topic} > {subtopic} | elo_range: {elo_str} imp_min: {imp_range[0]}")
            for ci, c in enumerate(candidates):
                c_elo = TAG_LOOKUP.get(c["id"], {}).get("difficulty", "?")
                c_imp = TAG_LOOKUP.get(c["id"], {}).get("importance", "?")
                log(f"    {'>>>' if ci == 0 else '   '} [{c['id']}] {c['title']} | elo={c_elo} imp={c_imp} | {c['match_type']} w={c['weight']}")

            candidate = pick_candidate(candidates, profile)
            if candidate is None:
                log(f"    → no candidates, skipped")
                continue

            pid = candidate["id"]
            if pid not in TAG_LOOKUP:
                log(f"    → problem {pid} not in tag lookup, skipped")
                continue

            # Simulate quality
            quality_name, (used_hints, looked_at_solution, struggled) = pick_quality(profile)

            # Get mastery before
            primary_sub = TAG_LOOKUP[pid]["primary_subtopic"]["name"]
            mastery_before = state.get("subtopics", {}).get(primary_sub, {}).get("score", 0.0)

            # Update mastery
            update_mastery(state, pid, TAG_LOOKUP[pid],
                           used_hints=used_hints,
                           looked_at_solution=looked_at_solution,
                           struggled=struggled)

            mastery_after = state["subtopics"][primary_sub]["score"]
            change = mastery_after - mastery_before

            completed_ids.add(pid)
            round_problems += 1
            total_problems += 1

            log(f"    ✓ [{pid}] {candidate['title']} | {quality_name} | "
                f"{primary_sub}: {mastery_before:.1f} → {mastery_after:.1f} ({change:+.2f})")

        # Round summary
        overall = get_overall_level(state, TAXONOMY)
        topic_levels = get_topic_levels(state, TAXONOMY)
        log(f"\n  Round {round_num} summary: {round_problems} problems done, {total_problems} total")
        log(f"  Overall: {round(overall, 1)} ({get_subtopic_tier(overall)})")
        log(f"  Topics:")
        for topic in TAXONOMY["topics"]:
            t_name = topic["name"]
            t_data = topic_levels[t_name]
            if t_data["score"] > 0:
                log(f"    {t_name}: {t_data['score']} ({t_data['tier']})")

    # Final full mastery state
    log(f"\n{'=' * 80}")
    log(f"FINAL STATE — {total_problems} problems completed")
    log(f"{'=' * 80}")
    overall = get_overall_level(state, TAXONOMY)
    log(f"Overall: {round(overall, 1)} ({get_subtopic_tier(overall)})")
    log(f"\n--- Full Mastery ---")
    topic_levels = get_topic_levels(state, TAXONOMY)
    for topic in TAXONOMY["topics"]:
        t_name = topic["name"]
        t_data = topic_levels[t_name]
        log(f"  {t_name}: {t_data['score']} ({t_data['tier']})")
        for sub in topic["subtopics"]:
            s_data = state.get("subtopics", {}).get(sub["name"], {})
            score = round(s_data.get("score", 0.0), 1)
            count = s_data.get("attempts_count", 0)
            tier = get_subtopic_tier(score)
            if count > 0:
                log(f"    {sub['name']}: {score} ({tier}, {count} attempts)")
            else:
                log(f"    {sub['name']}: 0.0 (Bronze, untouched)")

    out_file.close()
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    run_learning_loop()
