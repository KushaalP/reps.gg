"""
LLM prompt construction and API call for recommendation generation.
"""

import json
from openai import OpenAI

from lib.reco_engine.data import TAXONOMY, PROB_LOOKUP, HARD_PREREQS
from lib.reco_engine.search import prereqs_met, get_stale_subtopics
from lib.mastery import get_subtopic_tier, get_topic_levels, get_overall_level


# ── System prompt ────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the recommendation engine for reps.gg, an adaptive DSA learning platform.

Your job: given a user's mastery state, generate 10 problem profiles that will optimally advance their learning.

Each profile targets a single subtopic. Use EXACT topic and subtopic names from the taxonomy provided.

You specify a "selectivity" value (10-80) for each profile. This controls how selective the importance gate is — it maps to a percentile of the subtopic's actual problem pool, these are simply guidelines, and you should adapt accordingly for the mastery at hand:
- selectivity 70-80: very selective, only the most foundational and high-yield problems pass. Use for subtopics where the user is just starting out.
- selectivity 50-65: moderately selective, a mix of core and moderate problems. Use for subtopics where the user has some experience (Silver/Gold).
- selectivity 30-45: broad, includes moderately niche problems. Use for subtopics where the user is solid (Platinum) and needs variety.
- selectivity 10-25: wide open, nearly all problems pass including niche patterns. Use for subtopics where the user is advanced (Diamond) and has seen most common patterns.

Guidelines for what to recommend:
- Never recommend subtopics marked [LOCKED] — their prerequisites are not met.
- Never recommend subtopics marked [EXHAUSTED] — no problems remain for that subtopic.
- Prioritize subtopics that are lagging relative to the user's overall level. When multiple subtopics are lagging, prefer higher-importance ones (from the taxonomy). But don't ignore low-importance subtopics entirely — if the gap is large enough, they still deserve attention.
- Introduce variety — don't recommend the same subtopic multiple times unless they desperately need it.
- If stale subtopics are flagged, include 1-2 review profiles at the user's current level for those subtopics.
- Consider the prerequisite graph: if a user is weak in a prereq, strengthening it benefits downstream subtopics.
- Balance breadth and depth — don't hyper-focus on one topic unless that's what the user needs (depth can still be crucial to build foundations)

Output valid JSON with the key "recommendations" containing an array of 10 objects. Format:
{"recommendations": [
  {
    "topic": "Arrays & Hashing",
    "subtopic": "Frequency Counting / Hash Map Lookup",
    "selectivity": 70
  }
]}
"""


# ── Context builders ─────────────────────────────────────────────

def build_mastery_summary(state, exhausted_subtopics=None):
    """Compact mastery summary for the LLM prompt."""
    if exhausted_subtopics is None:
        exhausted_subtopics = set()
    lines = []
    topic_levels = get_topic_levels(state, TAXONOMY)
    overall = get_overall_level(state, TAXONOMY)

    lines.append(f"Overall: {overall} ({get_subtopic_tier(overall)})")
    lines.append("")

    for topic in TAXONOMY["topics"]:
        t_name = topic["name"]
        t_data = topic_levels[t_name]
        lines.append(f"{t_name}: {t_data['score']} ({t_data['tier']})")
        for sub in topic["subtopics"]:
            s_name = sub["name"]
            s_data = state.get("subtopics", {}).get(s_name, {})
            score = round(s_data.get("score", 0.0), 1)
            count = s_data.get("attempts_count", 0)
            tier = get_subtopic_tier(score)
            flags = ""
            if not prereqs_met(state, s_name):
                flags = " [LOCKED]"
            elif s_name in exhausted_subtopics:
                flags = " [EXHAUSTED]"
            lines.append(f"  {s_name}: {score} ({tier}, {count} attempts){flags}")
        lines.append("")

    return "\n".join(lines)


def build_recent_history(state, n=5):
    """Last n attempts as context."""
    attempts = state.get("attempts", [])
    recent = attempts[-n:] if len(attempts) >= n else attempts
    if not recent:
        return "No attempts yet."

    lines = []
    for a in reversed(recent):
        pid = a["problem_id"]
        prob = PROB_LOOKUP.get(pid, {})
        title = prob.get("title", f"#{pid}")
        lines.append(
            f"- {title} | {a['primary_subtopic']} | {a['quality']} | "
            f"change: {a['mastery_change']:+.2f}"
        )
    return "\n".join(lines)


def build_taxonomy_summary():
    """Compact taxonomy for the prompt (topic > subtopic: importance)."""
    lines = []
    for topic in TAXONOMY["topics"]:
        lines.append(f"{topic['name']} (importance: {topic['importance']}):")
        for sub in topic["subtopics"]:
            lines.append(f"  {sub['name']}: importance {sub['importance']}")
    return "\n".join(lines)


def build_prereq_summary():
    """Compact prereq graph for the prompt."""
    lines = []
    for sub_name, prereqs in HARD_PREREQS.items():
        lines.append(f"{sub_name} requires: {', '.join(prereqs)}")
    return "\n".join(lines)


def build_user_prompt(state, topic_filter=None, stale_subtopics=None, exhausted_subtopics=None):
    parts = []

    parts.append("=== TAXONOMY ===")
    parts.append(build_taxonomy_summary())

    parts.append("\n=== PREREQUISITE GRAPH (hard requirements) ===")
    parts.append(build_prereq_summary())

    parts.append("\n=== USER MASTERY STATE ===")
    parts.append(build_mastery_summary(state, exhausted_subtopics or set()))

    parts.append("\n=== RECENT HISTORY (last 5 attempts) ===")
    parts.append(build_recent_history(state))

    if stale_subtopics:
        parts.append("\n=== STALE SUBTOPICS (due for review) ===")
        for s in stale_subtopics[:5]:
            parts.append(f"- {s['name']}: {s['score']} ({s['tier']}), {s['days_since']} days since last attempt")

    if topic_filter:
        parts.append(f"\n=== ACTIVE TOPIC FILTER ===")
        parts.append(f"User has filtered to: {topic_filter}. ALL 10 recommendations must be within this topic.")

    parts.append("\nGenerate 10 problem profiles.")

    return "\n".join(parts)


# ── LLM call ─────────────────────────────────────────────────────

def call_llm(state, topic_filter=None, exhausted_subtopics=None):
    """Call the LLM to generate 10 problem profiles."""
    stale = get_stale_subtopics(state)
    user_prompt = build_user_prompt(state, topic_filter, stale, exhausted_subtopics)

    client = OpenAI()
    response = client.responses.create(
        model="gpt-5-mini",
        input=[
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        reasoning={"effort": "low"},
        text={"format": {"type": "json_object"}},
    )

    raw = response.output_text
    parsed = json.loads(raw)

    # Handle both {"recommendations": [...]} and [...] formats
    if isinstance(parsed, list):
        profiles = parsed
    elif isinstance(parsed, dict):
        for key in ["recommendations", "profiles", "problems", "problem_profiles"]:
            if key in parsed:
                profiles = parsed[key]
                break
        else:
            for v in parsed.values():
                if isinstance(v, list):
                    profiles = v
                    break
            else:
                print(f"DEBUG: Unexpected LLM response structure: {list(parsed.keys())}")
                profiles = []
    else:
        profiles = []

    if not profiles:
        print(f"DEBUG: Raw LLM response: {raw[:500]}")

    return profiles, raw
