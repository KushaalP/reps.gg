import json
import yaml
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"
OUTPUT_PATH = "data/core/corrective_flags.json"

# ── Load data ───────────────────────────────────────────────────────
with open("data/core/tagged_problems.json") as f:
    tagged = json.load(f)

with open("data/core/problems.json") as f:
    problems = json.load(f)

with open("taxonomy.yaml") as f:
    taxonomy = yaml.safe_load(f)

prob_lookup = {p["id"]: p for p in problems}

# ── Group by primary subtopic ──────────────────────────────────────
groups = {}
for t in tagged:
    key = t["primary_subtopic"]["name"]
    if key not in groups:
        groups[key] = []
    groups[key].append(t)

print(f"Total subtopic groups: {len(groups)}")
for name, probs in sorted(groups.items(), key=lambda x: -len(x[1]))[:5]:
    print(f"  {name}: {len(probs)} problems")

# ── Build prompts ──────────────────────────────────────────────────
SYSTEM_PROMPT = """You are reviewing LeetCode problem tags for consistency within a subtopic group.

You will receive a list of problems all tagged under the same primary subtopic, sorted by difficulty.

IMPORTANT RULES:
- Be conservative. Only flag things you are highly confident are WRONG, not just slightly off.
- There WILL be wide variance within a subtopic — different problems can legitimately have very different difficulty, importance, and interview scores. Do NOT flag something just because it's above or below the group average.
- Avoid suggesting minor adjustments. If a score is roughly in the right ballpark, leave it alone.
- LeetCode's Easy/Medium/Hard labels are often wrong, especially for contest problems. Do NOT flag difficulty mismatches based on LeetCode labels.

Only flag:
1. Misclassification — a problem that clearly does NOT belong in this subtopic. It should obviously be in a completely different subtopic. This is the most important check. Some have overlap and is subjective, if there's ambiguity, give benefit of doubt.
2. Egregious score errors — importance or interview_plausibility that is off by more than 0.25 and you are confident based on knowing the problem. For example, a classic well-known interview problem with interview_plausibility < 0.3, or a pure math trick with importance > 0.8.

Do NOT flag:
- Minor score differences (e.g. suggesting 0.55 instead of 0.45)
- Difficulty values (these come from Zerotrac contest ratings and are ground truth)
- Problems just because they're unusual for the group — variance is expected

For each flag, use EXACTLY these field names: "misclassification", "importance", or "interview_plausibility".
Return a JSON object per flag:
{"id": <int>, "field": "<field_name>", "current": <value>, "suggested": <value>, "reason": "<brief explanation>"}

Return a JSON array of flags. If everything looks fine (MOST groups should), return an empty array: []
Return ONLY the JSON array, no other text."""


def build_group_prompt(subtopic_name, group):
    group_sorted = sorted(group, key=lambda x: x["difficulty"])
    lines = []
    for t in group_sorted:
        title = prob_lookup[t["id"]]["title"] if t["id"] in prob_lookup else "?"
        lc_diff = prob_lookup[t["id"]]["difficulty"] if t["id"] in prob_lookup else "?"
        cp = t.get("company_plausibility", {})
        lines.append(
            f"ID {t['id']} | {title} | LC:{lc_diff} | "
            f"Diff:{t['difficulty']} | Imp:{t['importance']} | "
            f"Intv:{t['interview_plausibility']} | "
            f"Co: Q={cp.get('quant',0)} F={cp.get('faang',0)} M={cp.get('mid',0)} S={cp.get('startup',0)}"
        )

    return f"""Review the following {len(group)} problems tagged under "{subtopic_name}":

{chr(10).join(lines)}"""


# ── Run corrective pass ───────────────────────────────────────────
client = anthropic.Anthropic()
all_flags = []
total_input = 0
total_output = 0

CHUNK_SIZE = 100  # max problems per API call

for i, (subtopic, group) in enumerate(sorted(groups.items())):
    # Split large groups into chunks
    chunks = [group[j:j+CHUNK_SIZE] for j in range(0, len(group), CHUNK_SIZE)]
    chunk_label = f" ({len(chunks)} chunks)" if len(chunks) > 1 else ""
    print(f"\n[{i+1}/{len(groups)}] {subtopic} ({len(group)} problems){chunk_label}...")

    for ci, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  chunk {ci+1}/{len(chunks)}...")

        user_prompt = build_group_prompt(subtopic, chunk)

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            text = response.content[0].text

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            flags = json.loads(text)

            if flags:
                for f in flags:
                    f["subtopic"] = subtopic
                all_flags.extend(flags)
                print(f"  {len(flags)} flags")
            else:
                print(f"  clean")

            usage = response.usage
            total_input += usage.input_tokens
            total_output += usage.output_tokens

        except json.JSONDecodeError as e:
            print(f"  ERROR parsing JSON: {e}")
            print(f"  Raw: {text[:300]}")
        except Exception as e:
            print(f"  ERROR: {e}")

# ── Save flags ────────────────────────────────────────────────────
with open(OUTPUT_PATH, "w") as f:
    json.dump(all_flags, f, indent=2)

print(f"\n{'='*60}")
print(f"Corrective pass complete.")
print(f"Total flags: {len(all_flags)}")
print(f"Tokens — input: {total_input}, output: {total_output}")
print(f"Saved to {OUTPUT_PATH}")
