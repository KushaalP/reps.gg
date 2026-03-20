"""
Test the reco engine across realistic mastery profiles and edge cases.
10 profiles, 1 LLM call each.
"""

import json
import yaml
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.mastery import new_user_state, update_mastery, get_subtopic_tier, get_overall_level
from lib.reco_engine import RecoQueue, TAG_LOOKUP, PROB_LOOKUP, ALL_SUBTOPICS, TAXONOMY
from dotenv import load_dotenv

load_dotenv()


def build_real_profile():
    """Build the user's actual mastery profile from LeetCode."""
    import requests

    with open("data/core/tagged_problems.json") as f:
        tagged = json.load(f)
    with open("data/core/problems.json") as f:
        problems = json.load(f)

    tag_lookup = {t["id"]: t for t in tagged}
    slug_to_id = {p["slug"]: p["id"] for p in problems}

    CSRF = os.getenv("LEETCODE_CSRF_TOKEN")
    SESSION = os.getenv("LEETCODE_SESSION")
    COOKIES = {"csrftoken": CSRF, "LEETCODE_SESSION": SESSION}

    all_slugs = set()
    skip = 0
    while True:
        resp = requests.post(
            "https://leetcode.com/graphql",
            json={
                "query": 'query q($c: String, $l: Int, $s: Int, $f: QuestionListFilterInput) { problemsetQuestionList: questionList(categorySlug: $c, limit: $l, skip: $s, filters: $f) { total: totalNum questions: data { titleSlug } } }',
                "variables": {"c": "", "l": 100, "s": skip, "f": {"status": "AC"}},
            },
            cookies=COOKIES,
            headers={"x-csrftoken": CSRF, "referer": "https://leetcode.com"},
        )
        result = resp.json()["data"]["problemsetQuestionList"]
        if not result["questions"]:
            break
        for q in result["questions"]:
            all_slugs.add(q["titleSlug"])
        skip += 100
        if skip >= result["total"]:
            break

    matched_ids = [slug_to_id[s] for s in all_slugs if s in slug_to_id and slug_to_id[s] in tag_lookup]
    state = new_user_state()
    for pid in matched_ids:
        update_mastery(state, pid, tag_lookup[pid], quality=6)
    return state, set(matched_ids)


def set_sub(state, name, score, attempts, days_ago=3):
    state["subtopics"][name] = {
        "score": score,
        "attempts_count": attempts,
        "last_attempted": time.time() - 86400 * days_ago,
    }


# ── Profile builders ──────────────────────────────────────────────

def build_friend_profile():
    """Build rashmith's mastery profile from LeetCode."""
    import requests

    with open("data/core/tagged_problems.json") as f:
        tagged = json.load(f)
    with open("data/core/problems.json") as f:
        problems = json.load(f)

    tag_lookup = {t["id"]: t for t in tagged}
    slug_to_id = {p["slug"]: p["id"] for p in problems}

    CSRF = os.getenv("FRIEND_LEETCODE_CSRF_TOKEN")
    SESSION = os.getenv("FRIEND_LEETCODE_SESSION")
    COOKIES = {"csrftoken": CSRF, "LEETCODE_SESSION": SESSION}

    all_slugs = set()
    skip = 0
    while True:
        resp = requests.post(
            "https://leetcode.com/graphql",
            json={
                "query": 'query q($c: String, $l: Int, $s: Int, $f: QuestionListFilterInput) { problemsetQuestionList: questionList(categorySlug: $c, limit: $l, skip: $s, filters: $f) { total: totalNum questions: data { titleSlug } } }',
                "variables": {"c": "", "l": 100, "s": skip, "f": {"status": "AC"}},
            },
            cookies=COOKIES,
            headers={"x-csrftoken": CSRF, "referer": "https://leetcode.com"},
        )
        result = resp.json()["data"]["problemsetQuestionList"]
        if not result["questions"]:
            break
        for q in result["questions"]:
            all_slugs.add(q["titleSlug"])
        skip += 100
        if skip >= result["total"]:
            break

    matched_ids = [slug_to_id[s] for s in all_slugs if s in slug_to_id and slug_to_id[s] in tag_lookup]
    state = new_user_state()
    for pid in matched_ids:
        update_mastery(state, pid, tag_lookup[pid], quality=6)
    return state, set(matched_ids)


def profile_fresh():
    return "1. Fresh User", new_user_state(), set()


def profile_real():
    state, completed = build_real_profile()
    return "2. Real Profile (kushaal)", state, completed


def profile_friend():
    state, completed = build_friend_profile()
    return "3. Real Profile (rashmith)", state, completed


def profile_arrays_only():
    state = new_user_state()
    for sub in ["Frequency Counting / Hash Map Lookup", "Prefix Sums", "Sorting + Comparison",
                "Complement Search (Two Sum Pattern)", "Matrix Traversal (Diagonal, Valid Sudoku, etc)",
                "Kadane's Algorithm (Max Subarray)"]:
        set_sub(state, sub, 45.0, 20, days_ago=2)
    return "4. Arrays-Only Beginner", state, set()


def profile_balanced_mid():
    state = new_user_state()
    for topic in TAXONOMY["topics"]:
        for sub in topic["subtopics"]:
            set_sub(state, sub["name"], 35.0, 10, days_ago=5)
    return "5. Balanced Mid (Silver/Gold everywhere)", state, set()


def profile_advanced():
    state = new_user_state()
    for topic in TAXONOMY["topics"]:
        for sub in topic["subtopics"]:
            set_sub(state, sub["name"], 75.0, 30, days_ago=3)
    # Advanced topics slightly lower
    for sub in ["Bitmask DP", "Interval DP", "Minimum Spanning Tree (Prim's / Kruskal's)",
                "Dijkstra's (Weighted Shortest Path)"]:
        set_sub(state, sub, 50.0, 15, days_ago=4)
    return "6. Advanced User (Platinum/Diamond)", state, set()


def profile_prereq_locked():
    """Gold in foundations but hasn't touched Trees/Graphs — many subtopics LOCKED."""
    state = new_user_state()
    # Strong in arrays, two pointers, stack, binary search
    for sub in ["Frequency Counting / Hash Map Lookup", "Prefix Sums", "Sorting + Comparison",
                "Complement Search (Two Sum Pattern)", "Opposite-Direction (Converging)",
                "Same-Direction (Fast/Slow on Arrays)", "Standard Binary Search",
                "Binary Search on Answer Space", "Boundary Finding (Bisect Left/Right)",
                "Stack-Based Simulation", "Monotonic Stack", "General Bit Manipulation",
                "General Math"]:
        set_sub(state, sub, 45.0, 15, days_ago=3)
    # Trees at 0 — so graphs, backtracking, DP etc all locked via prereqs
    return "7. Prereq-Locked (no Trees/Graphs)", state, set()


def profile_lopsided():
    """Diamond in DP, Bronze everywhere else."""
    state = new_user_state()
    for sub in ["Linear Recurrence DP", "Longest Increasing Subsequence", "Word Break / String DP",
                "Unbounded Knapsack", "0/1 Knapsack", "Two Sequence DP (LCS, Edit distance)",
                "Grid Path Problems", "Bitmask DP", "Interval DP"]:
        set_sub(state, sub, 85.0, 40, days_ago=2)
    # Need prereqs met for DP to be unlocked
    for sub in ["Combinations / Subsets", "DFS Traversal (Inorder, Preorder, Postorder)",
                "Sorting + Comparison", "Frequency Counting / Hash Map Lookup",
                "General Bit Manipulation"]:
        set_sub(state, sub, 15.0, 5, days_ago=10)
    return "8. Lopsided (Diamond DP, Bronze elsewhere)", state, set()


def profile_stale():
    """Gold across the board but half subtopics stale (30+ days)."""
    state = new_user_state()
    stale_toggle = True
    for topic in TAXONOMY["topics"]:
        for sub in topic["subtopics"]:
            days = 35 if stale_toggle else 3
            set_sub(state, sub["name"], 45.0, 15, days_ago=days)
            stale_toggle = not stale_toggle
    return "9. Stale Heavy (half subtopics 30+ days old)", state, set()


def profile_near_exhausted():
    """Diamond everywhere, most problems completed."""
    state = new_user_state()
    for topic in TAXONOMY["topics"]:
        for sub in topic["subtopics"]:
            set_sub(state, sub["name"], 90.0, 50, days_ago=1)
    # Mark 90% of problems as completed
    all_ids = [t["id"] for t in TAG_LOOKUP.values()]
    completed = set(all_ids[:int(len(all_ids) * 0.9)])
    return "10. Near-Exhausted (Diamond, 90% completed)", state, completed


# ── Run all profiles ──────────────────────────────────────────────

def run_profile(label, state, completed_ids, out_file):
    def log(s=""):
        print(s)
        out_file.write(s + "\n")

    overall = get_overall_level(state, TAXONOMY)
    log("=" * 70)
    log(label)
    log(f"Overall: {round(overall, 1)} ({get_subtopic_tier(overall)})")
    log("=" * 70)

    # Print mastery state
    log("\n--- Mastery State ---")
    from lib.mastery import get_topic_levels
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
            log(f"    {sub['name']}: {score} ({tier}, {count} attempts)")
    log("")

    queue = RecoQueue()
    queue.load_exclusions(completed_ids, set(), set())
    queue.fill(state)

    log("--- Recommendations ---")
    for i, slot in enumerate(queue.slots):
        profile = slot["profile"]
        topic = profile.get("topic", "?")
        subtopic = profile.get("subtopic", "?")
        elo = profile.get("elo_range")
        if elo:
            cap_str = f", cap={elo[1]}" if elo[1] is not None else ""
            elo_str = f"floor={elo[0]}{cap_str}"
        else:
            elo_str = "none"
        selectivity = profile.get("selectivity", "?")
        imp_range = profile.get("imp_range", [0, 1.0])
        n_cands = len(slot["candidates"])

        # Get user's mastery for this subtopic
        s_data = state.get("subtopics", {}).get(subtopic, {})
        score = round(s_data.get("score", 0.0), 1)
        tier = get_subtopic_tier(score)

        log(f"Slot {i+1}: {topic} > {subtopic}")
        log(f"  User mastery: {score} ({tier}) | elo: {elo_str} | selectivity: {selectivity} | imp_min: {imp_range[0]} | candidates: {n_cands}")

        if slot["candidates"]:
            for j, c in enumerate(slot["candidates"]):
                marker = ">>>" if j == 0 else "   "
                log(f"  {marker} [{c['id']}] {c['title']} | {c['match_type']} w={c['weight']} score={c.get('score', '?'):.3f} | elo={c['elo']} imp={c['importance']}")
        else:
            log("  (no candidates)")
        log("")

    log("\n")


if __name__ == "__main__":
    out_path = "data/output/reco_profile_tests.txt"
    os.makedirs("data/output", exist_ok=True)

    profiles = [
        profile_fresh,
        profile_real,
        profile_friend,
        profile_arrays_only,
        profile_balanced_mid,
        profile_advanced,
        profile_prereq_locked,
        profile_lopsided,
        profile_stale,
        profile_near_exhausted,
    ]

    with open(out_path, "w") as out_file:
        for build_fn in profiles:
            label, state, completed = build_fn()
            run_profile(label, state, completed, out_file)

    print(f"\nAll results saved to {out_path}")
