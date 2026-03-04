import json
import yaml

# ── Load data ────────────────────────────────────────────────────────

with open("data/tagged_problems.json") as f:
    tagged = json.load(f)

with open("data/problems.json") as f:
    problems = json.load(f)

with open("taxonomy.yaml") as f:
    taxonomy = yaml.safe_load(f)

with open("data/nc250.json") as f:
    nc250 = json.load(f)

prob_lookup = {p["id"]: p for p in problems}
nc250_ids = {p["id"] for p in nc250}

# Build valid topic/subtopic names from taxonomy
valid_topics = {}
valid_subtopics = set()
for topic in taxonomy["topics"]:
    valid_topics[topic["name"]] = {st["name"] for st in topic["subtopics"]}
    for st in topic["subtopics"]:
        valid_subtopics.add(st["name"])

# ── Checks ───────────────────────────────────────────────────────────

flags = []

def flag(problem_id, category, message):
    flags.append({"id": problem_id, "category": category, "message": message})

for t in tagged:
    pid = t["id"]
    p = prob_lookup.get(pid)

    # 1. Duplicate check (handled by dict, but check for completeness)
    # (duplicates would be caught by ID collision in the tagged dict)

    # 2. Invalid topic name
    topic = t.get("primary_topic", "")
    if topic not in valid_topics:
        flag(pid, "invalid_topic", f"Unknown topic: '{topic}'")

    # 3. Invalid subtopic names
    ps_name = t["primary_subtopic"]["name"]
    if ps_name not in valid_subtopics:
        flag(pid, "invalid_subtopic", f"Unknown primary subtopic: '{ps_name}'")

    # Check subtopic belongs to the stated topic
    if topic in valid_topics and ps_name not in valid_topics[topic]:
        # Check if it belongs to a different topic
        actual_topic = None
        for tn, subs in valid_topics.items():
            if ps_name in subs:
                actual_topic = tn
                break
        if actual_topic:
            flag(pid, "subtopic_mismatch", f"Subtopic '{ps_name}' belongs to '{actual_topic}', not '{topic}'")

    for s in t.get("secondary_subtopics", []):
        if s["name"] not in valid_subtopics:
            flag(pid, "invalid_subtopic", f"Unknown secondary subtopic: '{s['name']}'")

    # 4. Weight issues
    primary_w = t["primary_subtopic"]["weight"]
    secondaries = t.get("secondary_subtopics", [])
    total_w = primary_w + sum(s["weight"] for s in secondaries)

    if abs(total_w - 1.0) > 0.02:
        flag(pid, "weight_sum", f"Weights sum to {total_w:.2f}, not 1.00")

    for s in secondaries:
        if s["weight"] > primary_w:
            flag(pid, "weight_order", f"Secondary '{s['name']}' (w={s['weight']}) > primary '{ps_name}' (w={primary_w})")

    # 5. Cross-reference LeetCode difficulty vs tagged elo
    if p:
        lc_diff = p["difficulty"]  # Easy/Medium/Hard
        tagged_diff = t["difficulty"]

        if isinstance(tagged_diff, (int, float)):
            if lc_diff == "Easy" and tagged_diff > 1800:
                flag(pid, "difficulty_mismatch", f"LeetCode Easy but tagged elo {tagged_diff}")
            elif lc_diff == "Hard" and tagged_diff < 1200:
                flag(pid, "difficulty_mismatch", f"LeetCode Hard but tagged elo {tagged_diff}")
            elif lc_diff == "Medium" and tagged_diff > 2400:
                flag(pid, "difficulty_mismatch", f"LeetCode Medium but tagged elo {tagged_diff}")

    # 6. NC250 with low importance
    if pid in nc250_ids and t["importance"] < 0.5:
        flag(pid, "nc250_low_importance", f"NC250 problem but importance={t['importance']}")

    # 7. Interview plausibility vs company plausibility contradiction
    ip = t["interview_plausibility"]
    cp = t.get("company_plausibility", {})
    if cp:
        max_company = max(cp.values())
        if ip > 0.8 and max_company < 0.25:
            flag(pid, "plausibility_contradiction", f"High interview plausibility ({ip}) but all company scores < 0.25")
        if ip < 0.2 and max_company > 0.7:
            flag(pid, "plausibility_contradiction", f"Low interview plausibility ({ip}) but company score up to {max_company}")

    # 8. Importance sanity
    imp = t["importance"]
    if imp > 0.95:
        flag(pid, "importance_cap", f"Importance {imp} seems too high (max anchor is 0.9)")
    if imp > 0.85 and ip < 0.2:
        flag(pid, "importance_interview_mismatch", f"Very high importance ({imp}) but very low interview plausibility ({ip})")

# ── Report ───────────────────────────────────────────────────────────

print(f"Validated {len(tagged)} problems")
print(f"Total flags: {len(flags)}")
print()

# Group by category
from collections import Counter
cats = Counter(f["category"] for f in flags)
for cat, count in cats.most_common():
    print(f"  {cat}: {count}")

print()

# Print all flags grouped by category
for cat in sorted(cats.keys()):
    cat_flags = [f for f in flags if f["category"] == cat]
    print(f"\n{'='*60}")
    print(f"  {cat} ({len(cat_flags)} issues)")
    print(f"{'='*60}")
    for f in cat_flags:
        title = prob_lookup[f["id"]]["title"] if f["id"] in prob_lookup else "?"
        print(f"  ID {f['id']} ({title}): {f['message']}")
