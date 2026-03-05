import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────
MODEL = "text-embedding-3-large"
BATCH_SIZE = 100  # OpenAI supports up to 2048 inputs per call
OUTPUT_PATH = "data/core/embeddings.json"

# ── Load data ───────────────────────────────────────────────────────
with open("data/core/problems.json") as f:
    problems = json.load(f)

with open("data/core/tagged_problems.json") as f:
    tagged = json.load(f)

prob_lookup = {p["id"]: p for p in problems}
tag_lookup = {t["id"]: t for t in tagged}

# ── Build text blobs ────────────────────────────────────────────────
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

def build_blob(tags):
    secs = ', '.join(s['name'] for s in tags.get('secondary_subtopics', [])) or 'none'
    return f"Topic: {tags['primary_topic']}. Primary subtopic: {tags['primary_subtopic']['name']}. Secondary subtopics: {secs}."


# ── Generate embeddings ─────────────────────────────────────────────
client = OpenAI()

# Build all blobs
blobs = []
ids = []
for t in tagged:
    blob = build_blob(t)
    blobs.append(blob)
    ids.append(t["id"])

print(f"Problems to embed: {len(blobs)}")

# Batch API calls
all_embeddings = {}
for i in range(0, len(blobs), BATCH_SIZE):
    batch_blobs = blobs[i:i+BATCH_SIZE]
    batch_ids = ids[i:i+BATCH_SIZE]

    print(f"Batch {i//BATCH_SIZE + 1}/{(len(blobs)-1)//BATCH_SIZE + 1} ({len(batch_blobs)} problems)...")

    response = client.embeddings.create(
        model=MODEL,
        input=batch_blobs,
    )

    for j, embedding in enumerate(response.data):
        all_embeddings[batch_ids[j]] = embedding.embedding

    print(f"  Done. Tokens used: {response.usage.total_tokens}")

# Save
output = [{"id": pid, "embedding": emb} for pid, emb in sorted(all_embeddings.items())]
with open(OUTPUT_PATH, "w") as f:
    json.dump(output, f)

print(f"\nSaved {len(output)} embeddings to {OUTPUT_PATH}")
file_size = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
print(f"File size: {file_size:.1f} MB")
