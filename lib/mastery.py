"""
reps.gg Mastery Model

Running score per subtopic (0-100). Each attempt adds or subtracts.
No averaging, no decay, no recency weighting.

mastery_change = quality_score × perceived_diff_mult × difficulty_multiplier × importance_gate × mastery_rate
"""

import time
import yaml
import os

# ── Load config ────────────────────────────────────────────────────

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mastery_config.yaml")

with open(_CONFIG_PATH) as f:
    _CONFIG = yaml.safe_load(f)

QUALITY_SCORES = _CONFIG["quality_scores"]
PERCEIVED_DIFFICULTY_MULT = _CONFIG["perceived_difficulty"]
TIERS = [(t["min"], t["name"]) for t in _CONFIG["tiers"]]
SECONDARY_DISCOUNT = _CONFIG["secondary_discount"]
IMPORTANCE_THRESHOLD = _CONFIG["importance_threshold"]
IMPORTANCE_DISCOUNT = _CONFIG["importance_discount"]

_DR = _CONFIG["diminishing_returns"]
DR_THRESHOLD = _DR["threshold"]
DR_MAX_REDUCTION = _DR["max_reduction"]

_DIFF = _CONFIG["difficulty_multiplier"]
DIFF_BASE_ELO = _DIFF["base_elo"]
DIFF_ELO_RANGE = _DIFF["elo_range"]
DIFF_NORMALIZATION = _DIFF["normalization"]
DIFF_MIN = _DIFF["min"]
DIFF_MAX = _DIFF["max"]

# Derive mastery_rate per subtopic from target_solves_to_gold
# mastery_rate = 40 / (target_solves × avg_gain_per_solve)
# avg_gain_per_solve ≈ 2.5 (realistic mix: ~30% clean, 25% hints, 25% solution, 20% struggled)
AVG_GAIN_PER_SOLVE = 2.5
GOLD_THRESHOLD = 40.0
_SUBTOPIC_TARGETS = _CONFIG.get("subtopic_targets", {})
MASTERY_RATES = {}
for sub_name, target in _SUBTOPIC_TARGETS.items():
    MASTERY_RATES[sub_name] = GOLD_THRESHOLD / (max(6, target) * AVG_GAIN_PER_SOLVE)

DEFAULT_MASTERY_RATE = 1.0  # fallback for subtopics not in config


# ── Core functions ──────────────────────────────────────────────────

def classify_quality(used_hints: bool, looked_at_solution: bool, struggled: bool) -> str:
    if struggled:
        return "struggled"
    if looked_at_solution:
        return "solved_after_solution"
    if used_hints:
        return "solved_with_hints"
    return "solved_clean"


def get_mastery_rate(subtopic_name: str) -> float:
    return MASTERY_RATES.get(subtopic_name, DEFAULT_MASTERY_RATE)


def compute_difficulty_multiplier(problem_elo: float, current_mastery: float) -> float:
    expected_elo = DIFF_BASE_ELO + (current_mastery / 100) * DIFF_ELO_RANGE
    delta = (problem_elo - expected_elo) / DIFF_NORMALIZATION
    return max(DIFF_MIN, min(DIFF_MAX, 1.0 + 0.5 * delta))


def compute_importance_gate(importance: float) -> float:
    """Floor gate: problems below importance threshold get heavily discounted."""
    if importance < IMPORTANCE_THRESHOLD:
        return IMPORTANCE_DISCOUNT
    return 1.0


def compute_attempt_score(
    quality: str,
    perceived_difficulty: str,
    problem_elo: float,
    problem_importance: float,
    current_mastery: float,
    mastery_rate: float = 1.0,
) -> float:
    base = QUALITY_SCORES[quality]
    perceived_mult = PERCEIVED_DIFFICULTY_MULT[perceived_difficulty]

    diff_mult = compute_difficulty_multiplier(problem_elo, current_mastery)
    imp_gate = compute_importance_gate(problem_importance)

    # Diminishing returns: taper gains after threshold (Gold)
    if current_mastery > DR_THRESHOLD:
        excess = (current_mastery - DR_THRESHOLD) / (100 - DR_THRESHOLD)
        dampening = 1.0 - excess * DR_MAX_REDUCTION
    else:
        dampening = 1.0

    return base * perceived_mult * diff_mult * imp_gate * mastery_rate * dampening


def get_subtopic_tier(score: float) -> str:
    tier = "Bronze"
    for threshold, name in TIERS:
        if score >= threshold:
            tier = name
    return tier


# ── User state management ──────────────────────────────────────────

def new_user_state() -> dict:
    return {
        "subtopics": {},
        "attempts": [],
    }


def _ensure_subtopic(state: dict, subtopic_name: str):
    if subtopic_name not in state["subtopics"]:
        state["subtopics"][subtopic_name] = {
            "score": 0.0,
            "attempts_count": 0,
            "last_attempted": None,
        }


def update_mastery(
    state: dict,
    problem_id: int,
    problem_tags: dict,
    used_hints: bool,
    looked_at_solution: bool,
    struggled: bool,
    perceived_difficulty: str,
    now: float = None,
) -> dict:
    if now is None:
        now = time.time()

    quality = classify_quality(used_hints, looked_at_solution, struggled)
    primary = problem_tags["primary_subtopic"]["name"]
    problem_elo = problem_tags["difficulty"]
    problem_importance = problem_tags["importance"]

    _ensure_subtopic(state, primary)
    current_mastery = state["subtopics"][primary]["score"]

    rate = get_mastery_rate(primary)

    # Compute primary mastery change
    change = compute_attempt_score(
        quality, perceived_difficulty, problem_elo, problem_importance, current_mastery, rate
    )

    # Update primary subtopic
    state["subtopics"][primary]["score"] = max(0, min(100, current_mastery + change))
    state["subtopics"][primary]["attempts_count"] += 1
    state["subtopics"][primary]["last_attempted"] = now

    # Update secondary subtopics (discounted)
    for sec in problem_tags.get("secondary_subtopics", []):
        sec_name = sec["name"]
        sec_weight = sec["weight"]
        _ensure_subtopic(state, sec_name)
        sec_mastery = state["subtopics"][sec_name]["score"]
        sec_rate = get_mastery_rate(sec_name)
        # Secondary change uses secondary's own mastery_rate
        sec_change = compute_attempt_score(
            quality, perceived_difficulty, problem_elo, problem_importance, sec_mastery, sec_rate
        ) * sec_weight * SECONDARY_DISCOUNT
        state["subtopics"][sec_name]["score"] = max(0, min(100, sec_mastery + sec_change))
        state["subtopics"][sec_name]["attempts_count"] += 1
        state["subtopics"][sec_name]["last_attempted"] = now

    # Record attempt
    state["attempts"].append({
        "problem_id": problem_id,
        "quality": quality,
        "perceived_difficulty": perceived_difficulty,
        "primary_subtopic": primary,
        "mastery_change": change,
        "new_mastery": state["subtopics"][primary]["score"],
        "timestamp": now,
    })

    return state


# ── Aggregation ─────────────────────────────────────────────────────

def get_topic_levels(state: dict, taxonomy: dict) -> dict:
    topics = {}
    for topic in taxonomy["topics"]:
        topic_name = topic["name"]
        weighted_sum = 0.0
        weight_total = 0.0
        for sub in topic["subtopics"]:
            sub_name = sub["name"]
            imp = sub["importance"]
            score = state["subtopics"].get(sub_name, {}).get("score", 0.0)
            weighted_sum += score * imp
            weight_total += imp
        avg = weighted_sum / weight_total if weight_total > 0 else 0.0
        topics[topic_name] = {
            "score": round(avg, 2),
            "tier": get_subtopic_tier(avg),
        }
    return topics


def get_overall_level(state: dict, taxonomy: dict) -> float:
    topic_levels = get_topic_levels(state, taxonomy)
    weighted_sum = 0.0
    weight_total = 0.0
    for topic in taxonomy["topics"]:
        topic_name = topic["name"]
        imp = topic["importance"]
        score = topic_levels[topic_name]["score"]
        weighted_sum += score * imp
        weight_total += imp
    return round(weighted_sum / weight_total, 2) if weight_total > 0 else 0.0
