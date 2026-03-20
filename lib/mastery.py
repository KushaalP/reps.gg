"""
reps.gg Mastery Model

Running score per subtopic (0-100). Each attempt adds or subtracts.
No averaging, no decay, no recency weighting.

mastery_change = quality_score × difficulty_multiplier × importance_gate × mastery_rate
"""

import time
import math
import yaml
import os

# ── Load config ────────────────────────────────────────────────────

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mastery_config.yaml")

with open(_CONFIG_PATH) as f:
    _CONFIG = yaml.safe_load(f)

QUALITY_SCORES = {int(k): v for k, v in _CONFIG["quality_scores"].items()}
TIERS = [(t["min"], t["name"]) for t in _CONFIG["tiers"]]
SECONDARY_DISCOUNT = _CONFIG["secondary_discount"]
IMPORTANCE_THRESHOLD = _CONFIG["importance_threshold"]
IMPORTANCE_DISCOUNT = _CONFIG["importance_discount"]

_DECAY = _CONFIG["decay"]
DECAY_GRACE_DAYS = _DECAY["grace_days"]
DECAY_BASE_RATE = _DECAY["base_rate"]
DECAY_MAX_TIER_DROP = _DECAY["max_tier_drop"]
DECAY_RECOVERY_BOOST = _DECAY["recovery_boost"]

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

def _decay_floor(stored_score: float) -> float:
    """Compute the minimum score a subtopic can decay to (2 tiers below current)."""
    # Find current tier index
    tier_idx = 0
    for i, (threshold, _) in enumerate(TIERS):
        if stored_score >= threshold:
            tier_idx = i
    # Floor is 2 tiers below
    floor_idx = max(0, tier_idx - DECAY_MAX_TIER_DROP)
    return TIERS[floor_idx][0]


def compute_decay_factor(days_inactive: float, mastery_rate: float = 1.0) -> float:
    """Logarithmic decay factor scaled by subtopic mastery rate.
    Narrow patterns (high mastery_rate) decay faster.
    Returns 0.0-1.0 (1.0 = no decay)."""
    if days_inactive <= DECAY_GRACE_DAYS:
        return 1.0
    effective_rate = DECAY_BASE_RATE * math.sqrt(mastery_rate)
    return max(0.0, 1.0 - effective_rate * math.log(days_inactive / DECAY_GRACE_DAYS))


def get_effective_score(stored_score: float, last_attempted: float,
                        subtopic_name: str = None, now: float = None) -> float:
    """Apply lazy decay to a stored score. Does not modify state."""
    if last_attempted is None or stored_score <= 0:
        return stored_score
    if now is None:
        now = time.time()
    days_inactive = (now - last_attempted) / 86400
    rate = get_mastery_rate(subtopic_name) if subtopic_name else DEFAULT_MASTERY_RATE
    factor = compute_decay_factor(days_inactive, rate)
    if factor >= 1.0:
        return stored_score
    floor = _decay_floor(stored_score)
    return floor + (stored_score - floor) * factor


def is_decayed(last_attempted: float, now: float = None) -> bool:
    """Check if a subtopic has decayed (past grace period)."""
    if last_attempted is None:
        return False
    if now is None:
        now = time.time()
    return (now - last_attempted) / 86400 > DECAY_GRACE_DAYS


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
    quality: int,
    problem_elo: float,
    problem_importance: float,
    current_mastery: float,
    mastery_rate: float = 1.0,
) -> float:
    base = QUALITY_SCORES[max(1, min(10, quality))]

    diff_mult = compute_difficulty_multiplier(problem_elo, current_mastery)
    imp_gate = compute_importance_gate(problem_importance)

    # Diminishing returns: taper gains after threshold (Gold)
    if current_mastery > DR_THRESHOLD:
        excess = (current_mastery - DR_THRESHOLD) / (100 - DR_THRESHOLD)
        dampening = 1.0 - excess * DR_MAX_REDUCTION
    else:
        dampening = 1.0

    return base * diff_mult * imp_gate * mastery_rate * dampening


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
    quality: int,
    now: float = None,
) -> dict:
    if now is None:
        now = time.time()
    primary = problem_tags["primary_subtopic"]["name"]
    problem_elo = problem_tags["difficulty"]
    problem_importance = problem_tags["importance"]

    _ensure_subtopic(state, primary)
    current_mastery = state["subtopics"][primary]["score"]
    last_attempted = state["subtopics"][primary]["last_attempted"]

    # Use effective (decayed) score for difficulty multiplier calculation
    effective = get_effective_score(current_mastery, last_attempted, primary, now)

    rate = get_mastery_rate(primary)

    # Compute primary mastery change (using effective score for difficulty context)
    change = compute_attempt_score(
        quality, problem_elo, problem_importance, effective, rate
    )

    # Recovery boost if subtopic has decayed
    if is_decayed(last_attempted, now):
        change *= DECAY_RECOVERY_BOOST

    # Update primary subtopic (add to stored score, not effective)
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
            quality, problem_elo, problem_importance, sec_mastery, sec_rate
        ) * sec_weight * SECONDARY_DISCOUNT
        state["subtopics"][sec_name]["score"] = max(0, min(100, sec_mastery + sec_change))
        state["subtopics"][sec_name]["attempts_count"] += 1
        state["subtopics"][sec_name]["last_attempted"] = now

    # Record attempt
    state["attempts"].append({
        "problem_id": problem_id,
        "quality": quality,
        "primary_subtopic": primary,
        "mastery_change": change,
        "new_mastery": state["subtopics"][primary]["score"],
        "timestamp": now,
    })

    return state


# ── Aggregation ─────────────────────────────────────────────────────

def get_topic_levels(state: dict, taxonomy: dict, now: float = None) -> dict:
    if now is None:
        now = time.time()
    topics = {}
    for topic in taxonomy["topics"]:
        topic_name = topic["name"]
        weighted_sum = 0.0
        weight_total = 0.0
        for sub in topic["subtopics"]:
            sub_name = sub["name"]
            imp = sub["importance"]
            sub_data = state["subtopics"].get(sub_name, {})
            stored = sub_data.get("score", 0.0)
            last = sub_data.get("last_attempted")
            score = get_effective_score(stored, last, sub_name, now)
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
