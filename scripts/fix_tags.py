import json
import yaml

with open("data/tagged_problems.json") as f:
    tagged = json.load(f)

with open("taxonomy.yaml") as f:
    taxonomy = yaml.safe_load(f)

# Build subtopic -> topic lookup
subtopic_to_topic = {}
for topic in taxonomy["topics"]:
    for st in topic["subtopics"]:
        subtopic_to_topic[st["name"]] = topic["name"]

fixes = 0

for t in tagged:
    pid = t["id"]

    # 1. Fix weight order: swap primary/secondary if secondary > primary
    secondaries = t.get("secondary_subtopics", [])
    if secondaries:
        max_sec = max(secondaries, key=lambda s: s["weight"])
        if max_sec["weight"] > t["primary_subtopic"]["weight"]:
            old_primary = t["primary_subtopic"]
            old_topic = t["primary_topic"]

            # New primary = highest secondary
            t["primary_subtopic"] = {"name": max_sec["name"], "weight": max_sec["weight"]}
            t["primary_topic"] = max_sec.get("topic", subtopic_to_topic.get(max_sec["name"], old_topic))

            # Old primary becomes secondary
            new_sec = {"topic": old_topic, "name": old_primary["name"], "weight": old_primary["weight"]}

            # Remove the promoted secondary, add the demoted primary
            t["secondary_subtopics"] = [s for s in secondaries if s["name"] != max_sec["name"]]
            t["secondary_subtopics"].append(new_sec)

            print(f"  ID {pid}: swapped primary '{old_primary['name']}' -> '{t['primary_subtopic']['name']}'")
            fixes += 1

    # 2. Fix weight sum != 1.0
    total = t["primary_subtopic"]["weight"] + sum(s["weight"] for s in t.get("secondary_subtopics", []))
    if abs(total - 1.0) > 0.02:
        # Scale all weights proportionally
        scale = 1.0 / total
        t["primary_subtopic"]["weight"] = round(t["primary_subtopic"]["weight"] * scale, 2)
        for s in t.get("secondary_subtopics", []):
            s["weight"] = round(s["weight"] * scale, 2)
        # Fix rounding drift
        new_total = t["primary_subtopic"]["weight"] + sum(s["weight"] for s in t.get("secondary_subtopics", []))
        if abs(new_total - 1.0) > 0.001:
            t["primary_subtopic"]["weight"] = round(t["primary_subtopic"]["weight"] + (1.0 - new_total), 2)
        print(f"  ID {pid}: fixed weight sum {total:.2f} -> 1.00")
        fixes += 1

    # 3. Fix subtopic/topic mismatch
    ps_name = t["primary_subtopic"]["name"]
    if ps_name in subtopic_to_topic and t["primary_topic"] != subtopic_to_topic[ps_name]:
        old_topic = t["primary_topic"]
        t["primary_topic"] = subtopic_to_topic[ps_name]
        print(f"  ID {pid}: fixed topic '{old_topic}' -> '{t['primary_topic']}'")
        fixes += 1

# Save
with open("data/tagged_problems.json", "w") as f:
    json.dump(tagged, f, indent=2)

print(f"\nApplied {fixes} fixes to {len(tagged)} problems")
