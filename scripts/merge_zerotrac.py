import requests
import json

# Fetch Zerotrac ratings
print("Fetching Zerotrac ratings...")
resp = requests.get("https://zerotrac.github.io/leetcode_problem_rating/data.json")
resp.raise_for_status()
zerotrac = resp.json()

# Build lookup by problem ID
ratings = {}
for entry in zerotrac:
    ratings[entry["ID"]] = round(entry["Rating"], 2)

print(f"Zerotrac ratings: {len(ratings)} problems")

# Load our problems
with open("data/problems.json") as f:
    problems = json.load(f)

print(f"Our problems: {len(problems)}")

# Merge
matched = 0
for p in problems:
    elo = ratings.get(p["id"])
    p["elo"] = elo
    if elo:
        matched += 1

# Save
with open("data/problems.json", "w") as f:
    json.dump(problems, f, indent=2)

print(f"Matched: {matched}/{len(problems)}")
print(f"Unmatched: {len(problems) - matched}")
print(f"Saved to data/problems.json")
