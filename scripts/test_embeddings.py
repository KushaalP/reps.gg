import json
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

# ── Load data ───────────────────────────────────────────────────────
print("Loading...")
with open("data/embeddings.json") as f:
    emb_data = json.load(f)
with open("data/tagged_problems.json") as f:
    tagged = json.load(f)
with open("data/problems.json") as f:
    problems = json.load(f)

tag_lookup = {t["id"]: t for t in tagged}
prob_lookup = {p["id"]: p for p in problems}

ids = [e["id"] for e in emb_data]
vectors = np.array([e["embedding"] for e in emb_data])
vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

# ── Queries ─────────────────────────────────────────────────────────
queries = [
    # Simple single subtopic, no secondary
    "Topic: Arrays & Hashing. Primary subtopic: Prefix Sums. Secondary subtopics: none.",
    "Topic: Stack. Primary subtopic: Monotonic Stack. Secondary subtopics: none.",
    "Topic: Greedy. Primary subtopic: General Greedy (Greedy is main insight). Secondary subtopics: none.",

    # Single subtopic with one secondary
    "Topic: Core DP. Primary subtopic: Grid Path Problems. Secondary subtopics: DFS Path Finding.",
    "Topic: Graphs. Primary subtopic: BFS Shortest Path (Unweighted). Secondary subtopics: DFS Connected Components.",
    "Topic: Linked List. Primary subtopic: Reversal (Full and Partial). Secondary subtopics: Merge Linked Lists.",

    # Two secondaries
    "Topic: Trees. Primary subtopic: BST Operations (Insert, Delete, Validate). Secondary subtopics: DFS Traversal (Inorder, Preorder, Postorder), Frequency Counting / Hash Map Lookup.",
    "Topic: Backtracking. Primary subtopic: Permutations. Secondary subtopics: Constraint Satisfaction (N-Queens), Frequency Counting / Hash Map Lookup.",
    "Topic: Heap / Priority Queue. Primary subtopic: Merge K Sorted Structures. Secondary subtopics: Top-K Elements, Sorting + Comparison.",

    # Cross-domain combos
    "Topic: Core DP. Primary subtopic: Linear Recurrence DP. Secondary subtopics: General Greedy (Greedy is main insight).",
    "Topic: Binary Search. Primary subtopic: Boundary Finding (Bisect Left/Right). Secondary subtopics: Variable-Size Window (Expand/Contract).",
    "Topic: Arrays & Hashing. Primary subtopic: Frequency Counting / Hash Map Lookup. Secondary subtopics: Opposite-Direction (Converging).",

    # Niche subtopics
    "Topic: Math & Geometry. Primary subtopic: Primes / Sieve of Eratosthenes. Secondary subtopics: none.",
    "Topic: Intervals. Primary subtopic: Sweep Line / Meeting Rooms. Secondary subtopics: Sorting + Comparison.",

    # Heavy multi-secondary
    "Topic: Advanced Graphs. Primary subtopic: Dijkstra's (Weighted Shortest Path). Secondary subtopics: Heap Simulation, Frequency Counting / Hash Map Lookup, Binary Search on Answer Space.",
    "Topic: Backtracking. Primary subtopic: Path Finding with Backtracking. Secondary subtopics: DFS Traversal (Inorder, Preorder, Postorder), Matrix Traversal (Diagonal, Valid Sudoku, etc), Constraint Satisfaction (N-Queens).",

    # Common interview patterns
    "Topic: Sliding Window. Primary subtopic: Fixed-Size Window. Secondary subtopics: Frequency Counting / Hash Map Lookup.",
    "Topic: Two Pointers. Primary subtopic: Opposite-Direction (Converging). Secondary subtopics: Sorting + Comparison.",

    # Niche combos
    "Topic: Advanced DP. Primary subtopic: Bitmask DP. Secondary subtopics: Combinatorics.",
    "Topic: Bit Manipulation. Primary subtopic: General Bit Manipulation. Secondary subtopics: Frequency Counting / Hash Map Lookup.",
]

# ── Embed and search ────────────────────────────────────────────────
response = client.embeddings.create(model="text-embedding-3-large", input=queries)
q_vecs = np.array([r.embedding for r in response.data])
q_vecs = q_vecs / np.linalg.norm(q_vecs, axis=1, keepdims=True)

import sys

# Also write to file
output_path = "data/test_embeddings_output.txt"
out_file = open(output_path, "w")

def log(s=""):
    print(s)
    out_file.write(s + "\n")

for i, query in enumerate(queries):
    scores = vectors @ q_vecs[i]
    top_indices = np.argsort(scores)[::-1][:5]

    log(f"\n{'='*70}")
    log(f"Q{i+1}: {query}")
    log(f"{'='*70}")
    for idx in top_indices:
        pid = ids[idx]
        t = tag_lookup[pid]
        p = prob_lookup[pid]
        secs = ", ".join(s["name"] for s in t.get("secondary_subtopics", []))

        # Get the blob that was embedded for this problem
        blob_secs = ", ".join(s["name"] for s in t.get("secondary_subtopics", [])) or "none"

        def importance_label(val):
            if val < 0.1: return "negligible"
            if val < 0.2: return "very low"
            if val < 0.3: return "low"
            if val < 0.4: return "below average"
            if val < 0.5: return "moderate"
            if val < 0.6: return "above average"
            if val < 0.7: return "fairly high"
            if val < 0.8: return "high"
            if val < 0.9: return "very high"
            return "essential"

        def difficulty_label(val):
            if val < 1000: return "trivial"
            if val < 1200: return "very easy"
            if val < 1350: return "easy"
            if val < 1500: return "medium-easy"
            if val < 1650: return "medium"
            if val < 1800: return "medium-hard"
            if val < 2000: return "hard"
            if val < 2200: return "very hard"
            if val < 2500: return "extremely hard"
            return "elite"

        imp_l = importance_label(t["importance"])
        diff_l = difficulty_label(t["difficulty"])

        log(f"  {scores[idx]:.3f} | {p['title']}")
        log(f"         topic: {t['primary_topic']} > {t['primary_subtopic']['name']} | sec: {secs or 'none'}")
        log(f"         diff: {diff_l} ({t['difficulty']}) | imp: {imp_l} ({t['importance']})")

out_file.close()
print(f"\nSaved to {output_path}")
