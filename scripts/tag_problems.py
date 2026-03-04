import json
import time
import os
import yaml
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────
PASS1_MODEL = "claude-opus-4-6"
PASS2_MODEL = "gpt-5.2-mini"  # swap to whatever you want
BATCH_SIZE = 25
OUTPUT_PATH = "data/tagged_problems.json"

# ── Load data ───────────────────────────────────────────────────────
def load_taxonomy():
    with open("taxonomy.yaml") as f:
        return yaml.safe_load(f)

def load_nc250():
    with open("data/nc250.json") as f:
        return json.load(f)

def load_problems():
    with open("data/problems.json") as f:
        return json.load(f)

# ── Build system prompt ─────────────────────────────────────────────
def build_system_prompt(taxonomy, nc250):
    # Extract all valid subtopic names
    subtopic_names = []
    for topic in taxonomy["topics"]:
        for st in topic["subtopics"]:
            subtopic_names.append(f"  - {st['name']} (under {topic['name']})")

    nc250_titles = [p["title"] for p in nc250]

    return f"""You are an expert LeetCode problem tagger. Your job is to analyze problems and produce structured metadata.

## Taxonomy
You MUST use these exact subtopic names when tagging. Each problem gets a primary subtopic and optional secondary subtopics.

{yaml.dump(taxonomy, default_flow_style=False)}

## Valid subtopic names:
{chr(10).join(subtopic_names)}

## Output format
For each problem, return a JSON object with these fields:
- "id": the problem's LeetCode ID (integer)
- "primary_subtopic": {{"name": "<exact subtopic name>", "weight": <float>}}
- "secondary_subtopics": [{{"name": "<exact subtopic name>", "weight": <float>}}, ...] (can be empty)
- "difficulty": integer on the Zerotrac contest rating scale (~800 = trivial, ~1200 = easy, ~1600 = medium, ~2000 = hard, ~2400+ = elite)
- "importance": float 0-1, how generalizable/transferable the problem is
- "interview_plausibility": float 0-1, likelihood of appearing in a real interview
- "company_plausibility": {{"quant": <float>, "faang": <float>, "mid": <float>, "startup": <float>}}

All subtopic weights (primary + secondary) must sum to 1.0.

## Difficulty calibration anchors
These problems have known contest ratings. Use them to calibrate your difficulty estimates:
- Concatenation of Array: 1130
- Count Good Nodes in Binary Tree: 1360
- Time Based Key-Value Store: 1575
- Car Fleet: 1678
- Maximum Frequency Stack: 2028
- Minimum Interval to Include Each Query: 2286
- Find Critical and Pseudo-Critical Edges in Minimum Spanning Tree: 2572

## Importance calibration
Importance measures how transferable the problem's core technique is — NOT how hard it is.

Framework:
- If the problem cleanly teaches a core subtopic pattern, importance is HIGH (0.75-0.95) even with minor twists
- If the problem uses known patterns but in a very specific/niche setup, importance is MID (0.4-0.65)
- If the problem is a one-off trick, pure simulation, or math trivia with no transferable technique, importance is LOW (0.1-0.3)
- Being on the NeetCode 150/250 list signals HIGH importance — these problems were curated because they teach generalizable patterns
- Difficulty does NOT correlate with importance — a 3000-elo problem can be low importance if it's a niche trick
- Math as a secondary technique doesn't lower importance — judge by the most transferable technique the problem teaches
- Math as the ENTIRE solution with no algorithmic pattern = low importance

Importance anchors:
- Two Sum: 0.9 (core hash map pattern, transfers everywhere)
- Number of Islands: 0.9 (core BFS/DFS grid pattern)
- Coin Change: 0.9 (core DP foundation)
- Merge Intervals: 0.9 (core sorting + intervals)
- ~0.75: Problems that cleanly map to a core subtopic with a twist (e.g. House Robber variants with extra state)
- Filling Bookcase Shelves: 0.65 (partition DP, solid but narrower family)
- ~0.5: Real technique + niche overlay (e.g. tree distances + Pythagorean check)
- Word Squares II: 0.45 (known patterns but very specific constraint setup)
- ~0.3: Some useful sub-technique but mostly niche (e.g. digit frequency counting in a math problem)
- Airplane Seat Probability: 0.15 (pure math trick, nothing transfers)
- Check if Rectangle Corner Is Reachable: 0.15 (elo 3774, extremely hard but niche math/geometry trick)
- Basic Calculator IV: 0.15 (elo 2863, hard but specific string parsing grind)
- Cat and Mouse II: 0.15 (elo 2849, hard but niche game theory)
- Harshad Number: 0.1 (no pattern at all)

## NeetCode 250 problems (high importance signal):
{chr(10).join(nc250_titles)}

## Instructions
- Return ONLY a JSON array of objects, no other text
- Use EXACT subtopic names from the taxonomy
- Every problem must have exactly one primary_subtopic
- Weights must sum to 1.0
"""


# ── Build batch prompt ──────────────────────────────────────────────
def build_batch_prompt(problems_batch):
    entries = []
    for p in problems_batch:
        content = p.get("content_clean") or "(no description available — paid problem)"
        solution = p.get("solution_clean") or "(no official solution)"
        # Truncate long content/solutions to save tokens
        if len(content) > 2000:
            content = content[:2000] + "..."
        if len(solution) > 1500:
            solution = solution[:1500] + "..."

        entry = f"""---
ID: {p['id']}
Title: {p['title']}
Difficulty: {p['difficulty']}
LeetCode Topics: {', '.join(p['topics'])}
Zerotrac ELO: {p.get('elo') or 'N/A'}

Description:
{content}

Official Solution:
{solution}
"""
        entries.append(entry)

    return f"Tag the following {len(problems_batch)} problems:\n\n" + "\n".join(entries)


# ── Pass 1: Batch tagging ──────────────────────────────────────────
def run_pass1():
    taxonomy = load_taxonomy()
    nc250 = load_nc250()
    problems = load_problems()

    system_prompt = build_system_prompt(taxonomy, nc250)
    client = anthropic.Anthropic()

    # Load existing progress
    tagged = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
            tagged = {p["id"]: p for p in existing}
        print(f"Resuming — {len(tagged)} already tagged")

    # Filter to untagged
    to_tag = [p for p in problems if p["id"] not in tagged]
    print(f"Problems to tag: {len(to_tag)}")
    print(f"System prompt: ~{len(system_prompt.split())} words")

    batches = [to_tag[i:i+BATCH_SIZE] for i in range(0, len(to_tag), BATCH_SIZE)]
    print(f"Batches: {len(batches)}")

    for batch_idx, batch in enumerate(batches):
        print(f"\nBatch {batch_idx+1}/{len(batches)} ({len(batch)} problems)...")

        user_prompt = build_batch_prompt(batch)

        try:
            response = client.messages.create(
                model=PASS1_MODEL,
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            text = response.content[0].text

            # Parse JSON from response (handle markdown code blocks)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            results = json.loads(text)

            for r in results:
                tagged[r["id"]] = r

            # Save checkpoint
            all_tagged = sorted(tagged.values(), key=lambda x: x["id"])
            with open(OUTPUT_PATH, "w") as f:
                json.dump(all_tagged, f, indent=2)

            print(f"  Tagged {len(results)} problems (total: {len(tagged)})")

            # Log token usage
            usage = response.usage
            print(f"  Tokens — input: {usage.input_tokens}, output: {usage.output_tokens}")
            if hasattr(usage, 'cache_read_input_tokens'):
                print(f"  Cache — read: {usage.cache_read_input_tokens}, creation: {usage.cache_creation_input_tokens}")

        except json.JSONDecodeError as e:
            print(f"  ERROR parsing JSON: {e}")
            print(f"  Raw response: {text[:500]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(1)

    print(f"\nPass 1 complete. Tagged {len(tagged)} problems.")


if __name__ == "__main__":
    run_pass1()
