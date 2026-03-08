"""
Pull solved problems from LeetCode profile, cross-reference with tagged problems,
and compute mastery assuming avg gain per solve for each problem.
"""

import requests
import json
import yaml
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from lib.mastery import (
    new_user_state, update_mastery, get_subtopic_tier,
    get_topic_levels, get_overall_level, compute_attempt_score,
    get_mastery_rate,
)

load_dotenv()

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"
CSRF = os.getenv("LEETCODE_CSRF_TOKEN")
SESSION = os.getenv("LEETCODE_SESSION")
COOKIES = {"csrftoken": CSRF, "LEETCODE_SESSION": SESSION}
HEADERS = {"x-csrftoken": CSRF, "referer": "https://leetcode.com"}


def fetch_solved_problems(username="KushaalP"):
    """Fetch all accepted submissions for a user."""
    query = """
    query userProblemsSolved($username: String!) {
        matchedUser(username: $username) {
            submitStatsGlobal {
                acSubmissionNum {
                    difficulty
                    count
                }
            }
        }
        recentAcSubmissionList(username: $username, limit: 1000) {
            id
            title
            titleSlug
        }
    }
    """
    resp = requests.post(LEETCODE_GRAPHQL, json={
        "query": query,
        "variables": {"username": username}
    }, cookies=COOKIES, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()["data"]

    stats = data["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"]
    print(f"Profile stats: {stats}")

    recent = data["recentAcSubmissionList"]
    print(f"Recent AC submissions returned: {len(recent)}")
    return recent


def fetch_all_solved_slugs(username="KushaalP"):
    """Use the problemsetQuestionList with status filter to get all solved."""
    all_slugs = set()
    skip = 0
    limit = 100

    while True:
        query = """
        query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
            problemsetQuestionList: questionList(
                categorySlug: $categorySlug
                limit: $limit
                skip: $skip
                filters: $filters
            ) {
                total: totalNum
                questions: data {
                    questionFrontendId
                    titleSlug
                    title
                }
            }
        }
        """
        resp = requests.post(LEETCODE_GRAPHQL, json={
            "query": query,
            "variables": {
                "categorySlug": "",
                "limit": limit,
                "skip": skip,
                "filters": {"status": "AC"}
            }
        }, cookies=COOKIES, headers=HEADERS)
        resp.raise_for_status()
        result = resp.json()["data"]["problemsetQuestionList"]
        questions = result["questions"]

        if not questions:
            break

        for q in questions:
            all_slugs.add(q["titleSlug"])

        total = result["total"]
        skip += limit
        print(f"  Fetched {skip}/{total} solved problems...")

        if skip >= total:
            break

    print(f"Total solved: {len(all_slugs)}")
    return all_slugs


# ── Load tagged problems ──────────────────────────────────────────
with open("data/core/tagged_problems.json") as f:
    tagged = json.load(f)

with open("data/core/problems.json") as f:
    problems = json.load(f)

with open("taxonomy.yaml") as f:
    taxonomy = yaml.safe_load(f)

tag_lookup = {t["id"]: t for t in tagged}
prob_lookup = {p["id"]: p for p in problems}
slug_to_id = {p["slug"]: p["id"] for p in problems}

# Build subtopic importance lookup
subtopic_importance = {}
for topic in taxonomy["topics"]:
    for sub in topic["subtopics"]:
        subtopic_importance[sub["name"]] = sub["importance"]

# ── Fetch solved problems ─────────────────────────────────────────
print("Fetching your solved problems from LeetCode...")
solved_slugs = fetch_all_solved_slugs()

# Match against our database
matched_ids = []
unmatched = []
for slug in solved_slugs:
    if slug in slug_to_id:
        pid = slug_to_id[slug]
        if pid in tag_lookup:
            matched_ids.append(pid)
        else:
            unmatched.append(slug)
    else:
        unmatched.append(slug)

print(f"\nMatched to tagged database: {len(matched_ids)}")
print(f"Unmatched (not in our DB): {len(unmatched)}")

# ── Simulate mastery with avg gain ────────────────────────────────
state = new_user_state()

# Apply each solved problem assuming avg quality (hints-level solve, medium perceived)
# This means: solved_with_hints, medium perceived difficulty
for pid in matched_ids:
    tags = tag_lookup[pid]
    update_mastery(
        state, pid, tags,
        used_hints=True,
        looked_at_solution=False,
        struggled=False,
    )

# ── Print results ─────────────────────────────────────────────────
print(f"\n{'='*80}")
print(f"  YOUR MASTERY PROFILE ({len(matched_ids)} problems)")
print(f"{'='*80}")

# Subtopic scores
print(f"\n  --- Subtopic Scores (top 25) ---")
items = sorted(state["subtopics"].items(), key=lambda x: -x[1]["score"])
for sub_name, sub_data in items[:25]:
    imp = subtopic_importance.get(sub_name, 0)
    tier = get_subtopic_tier(sub_data["score"])
    print(f"    {sub_name:<45} {sub_data['score']:>6.1f} [{tier}]  "
          f"(imp:{imp:.2f}, {sub_data['attempts_count']} problems)")

# Count tiers
tier_counts = {"Bronze": 0, "Silver": 0, "Gold": 0, "Platinum": 0, "Diamond": 0}
for sub_name, sub_data in state["subtopics"].items():
    tier = get_subtopic_tier(sub_data["score"])
    tier_counts[tier] += 1

print(f"\n  --- Tier Distribution ---")
for tier, count in tier_counts.items():
    bar = "█" * count
    print(f"    {tier:<10} {count:>3}  {bar}")

# Topic levels
print(f"\n  --- Topic Levels ---")
topic_levels = get_topic_levels(state, taxonomy)
for topic in taxonomy["topics"]:
    name = topic["name"]
    info = topic_levels[name]
    tier = get_subtopic_tier(info["score"])
    print(f"    {name:<40} {info['score']:>6.1f} [{tier}]")

overall = get_overall_level(state, taxonomy)
print(f"\n    {'OVERALL':<40} {overall:>6.1f} [{get_subtopic_tier(overall)}]")

# Bottom subtopics (weaknesses)
print(f"\n  --- Weakest Subtopics (attempted but low) ---")
attempted = [(n, d) for n, d in items if d["attempts_count"] > 0]
for sub_name, sub_data in reversed(attempted[-10:]):
    imp = subtopic_importance.get(sub_name, 0)
    tier = get_subtopic_tier(sub_data["score"])
    print(f"    {sub_name:<45} {sub_data['score']:>6.1f} [{tier}]  "
          f"(imp:{imp:.2f}, {sub_data['attempts_count']} problems)")

# Untouched high-importance subtopics
print(f"\n  --- Untouched High-Importance Subtopics ---")
untouched = [s for s in subtopic_importance
             if subtopic_importance[s] >= 0.7 and s not in state["subtopics"]]
for s in sorted(untouched, key=lambda x: -subtopic_importance[x]):
    print(f"    {s:<45} (imp:{subtopic_importance[s]:.2f})")
if not untouched:
    print(f"    (none — all high-importance subtopics attempted)")
