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
- "primary_topic": "<exact topic name from taxonomy>" (e.g. "Arrays & Hashing", "Trees", "Core DP")
- "primary_subtopic": {{"name": "<exact subtopic name>", "weight": <float to 2 decimal places>}}
- "secondary_subtopics": [{{"topic": "<topic name>", "name": "<subtopic name>", "weight": <float to 2 decimal places>}}, ...] (can be empty)
- "difficulty": integer on the Zerotrac contest rating scale. Use precise values, NOT rounded to 50s or 100s. Examples: 1137, 1283, 1574, 1842, 2163, 2487. The full range is ~800 to ~3500.
- "importance": float 0-1 to 2 decimal places (e.g. 0.73, 0.42, 0.88 — be precise, avoid rounding to 0.5, 0.7, 0.8 etc.)
- "interview_plausibility": float 0-1 to 2 decimal places. This is INDEPENDENT of importance. It measures: would an interviewer realistically give this problem? A niche problem (low importance) CAN have high interview plausibility if it has a clean problem statement, is solvable in 30-45 min, and tests coding ability. A highly generalizable problem (high importance) CAN have low interview plausibility if it's too long, requires obscure knowledge, or has complex I/O. Use good judgment.
- "company_plausibility": {{"quant": <float 2dp>, "faang": <float 2dp>, "mid": <float 2dp>, "startup": <float 2dp>}}

PRECISION IS CRITICAL. Use 2 decimal places for all float scores. Do NOT cluster scores at round numbers. Difficulty should be precise integers (1347, not 1350).

All subtopic weights (primary + secondary) must sum to 1.00.

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

## Interview plausibility guidance
Interview plausibility is about whether this problem would REALISTICALLY show up in an interview. Consider:
- Clean, concise problem statement? Higher plausibility.
- Solvable in 30-45 minutes? Higher plausibility.
- Tests core coding/problem-solving ability? Higher plausibility.
- Requires obscure math/theory knowledge? Lower plausibility.
- Very long problem description or complex I/O? Lower plausibility.
- Too easy (trivial implementation)? Lower plausibility for FAANG, fine for startup.
- Contest-style with tricky edge cases? Lower plausibility.
A problem with 0.5 importance can easily have 0.85 interview plausibility. These are independent dimensions.

## Instructions
- Return ONLY a JSON array of objects, no other text
- Use EXACT topic and subtopic names from the taxonomy
- Every problem must have exactly one primary_topic and primary_subtopic
- Weights must sum to 1.00
- All float scores must be to 2 decimal places
- Difficulty must be a precise integer, not rounded to nearest 50
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
                max_tokens=16384,
                cache_control={"type": "ephemeral"},
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

            # Build elo lookup from source problems
            elo_lookup = {p["id"]: p["elo"] for p in batch if p.get("elo")}

            for r in results:
                pid = r["id"]
                if pid in elo_lookup:
                    r["difficulty_llm"] = r["difficulty"]
                    r["difficulty"] = elo_lookup[pid]
                tagged[pid] = r

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
