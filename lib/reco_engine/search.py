"""
Candidate search, filtering, scoring, prereq checking, and staleness detection.
"""

import time
import statistics
import numpy as np
from openai import OpenAI

from lib.reco_engine.data import (
    TAG_LOOKUP, PROB_LOOKUP, TAXONOMY,
    HARD_PREREQS, ALL_SUBTOPICS, PREREQ_MIN_MASTERY,
    SUBTOPIC_ELO_VALUES, SUBTOPIC_ELO_IMP_PAIRS, SUBTOPIC_IMP_VALUES,
    EMB_IDS, EMB_VECTORS,
    PRIMARY_INDEX, SECONDARY_INDEX,
    STALE_THRESHOLD_DAYS, ELO_MASTERY_THRESHOLD,
)
from lib.mastery import get_subtopic_tier


# ── Staleness detection ──────────────────────────────────────────

def get_stale_subtopics(state, now=None):
    """Return subtopics that have been attempted before but are stale."""
    if now is None:
        now = time.time()
    stale = []
    for sub_name, sub_data in state.get("subtopics", {}).items():
        last = sub_data.get("last_attempted")
        if last is None:
            continue
        days_since = (now - last) / 86400
        if days_since >= STALE_THRESHOLD_DAYS and sub_data.get("score", 0) > 0:
            stale.append({
                "name": sub_name,
                "score": round(sub_data["score"], 1),
                "tier": get_subtopic_tier(sub_data["score"]),
                "days_since": round(days_since),
            })
    stale.sort(key=lambda x: -x["days_since"])
    return stale


# ── Prereq checking ─────────────────────────────────────────────

def prereqs_met(state, subtopic):
    if subtopic not in HARD_PREREQS:
        return True
    for prereq in HARD_PREREQS[subtopic]:
        if state.get("subtopics", {}).get(prereq, {}).get("score", 0.0) < PREREQ_MIN_MASTERY:
            return False
    return True


def get_locked_subtopics(state):
    """Return list of subtopics whose hard prereqs are not met."""
    locked = []
    for sub in ALL_SUBTOPICS:
        if not prereqs_met(state, sub):
            locked.append(sub)
    return locked


# ── Exhaustion detection ─────────────────────────────────────────

def get_exhausted_subtopics(completed_ids, skip_cooldown_ids, discarded_ids):
    """Return set of subtopics where all available problems are completed/excluded."""
    excluded = completed_ids | skip_cooldown_ids | discarded_ids
    exhausted = set()
    for sub_name in ALL_SUBTOPICS:
        all_pids = set(PRIMARY_INDEX.get(sub_name, []))
        for pid, _ in SECONDARY_INDEX.get(sub_name, []):
            all_pids.add(pid)
        if all_pids and all_pids.issubset(excluded):
            exhausted.add(sub_name)
    return exhausted


# ── Elo/importance range computation ─────────────────────────────

def compute_elo_range(state, subtopic, imp_min=0.0):
    """Compute elo range from user's mastery using the subtopic's actual elo distribution.

    Below ELO_MASTERY_THRESHOLD: returns None (no elo filtering, importance-only).
    Above threshold: returns [elo_floor, elo_cap].
    - Floor: percentile in the subtopic's elo distribution corresponding to mastery.
    - Cap: computed from filtered elo distribution (only problems >= imp_min).
      cap = filtered_median + (mastery_pct * (filtered_max - filtered_median))
      At low mastery: cap near median. At high mastery: cap near max.
    """
    mastery = state.get("subtopics", {}).get(subtopic, {}).get("score", 0.0)

    if mastery < ELO_MASTERY_THRESHOLD:
        return None  # No elo filtering for early learners

    elo_values = SUBTOPIC_ELO_VALUES.get(subtopic)
    if not elo_values:
        return None

    n = len(elo_values)
    # Floor: map mastery 25-100 to percentile 10-75
    floor_pct = 10 + ((mastery - ELO_MASTERY_THRESHOLD) / (100 - ELO_MASTERY_THRESHOLD)) * 65
    floor_idx = int((floor_pct / 100) * (n - 1))
    elo_floor = round(elo_values[floor_idx])

    # Cap: from importance-filtered elo distribution
    pairs = SUBTOPIC_ELO_IMP_PAIRS.get(subtopic, [])
    filtered_elos = sorted([elo for elo, imp in pairs if imp >= imp_min])
    if not filtered_elos:
        filtered_elos = sorted([elo for elo, _ in pairs])  # fallback to unfiltered
    if not filtered_elos:
        return [elo_floor, None]

    filtered_median = statistics.median(filtered_elos)
    filtered_max = filtered_elos[-1]
    mastery_pct = mastery / 100.0
    elo_cap = round(filtered_median + mastery_pct * (filtered_max - filtered_median))

    # Ensure cap >= floor
    if elo_cap < elo_floor:
        elo_cap = elo_floor

    return [elo_floor, elo_cap]


def compute_importance_range(subtopic, selectivity):
    """Convert LLM selectivity (10-80) to [imp_min, 1.0] using subtopic's actual distribution."""
    imp_values = SUBTOPIC_IMP_VALUES.get(subtopic)
    if not imp_values:
        return [0.0, 1.0]
    selectivity = max(10, min(80, selectivity))
    idx = int((selectivity / 100) * (len(imp_values) - 1))
    imp_min = round(imp_values[idx], 2)
    return [imp_min, 1.0]


# ── Embedding search (legacy) ────────────────────────────────────

def embed_query(query_text):
    """Embed a single query string using the same model as our DB."""
    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=[query_text],
    )
    vec = np.array(response.data[0].embedding)
    return vec / np.linalg.norm(vec)


def search_candidates(query_vec, top_k=50):
    """Return top_k most similar problem IDs with scores."""
    scores = EMB_VECTORS @ query_vec
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(EMB_IDS[i], float(scores[i])) for i in top_indices]


def filter_candidates(
    candidates,
    elo_range,
    importance_range,
    state,
    completed_ids,
    skip_cooldown_ids,
    discarded_ids,
    max_results=5,
    elo_expand_step=50,
    importance_expand_step=0.05,
    max_expansions=5,
):
    """
    Filter candidates by elo, importance, prereqs, and exclusion lists.
    If too few pass, widen bounds incrementally.
    """
    elo_min = elo_range[0] if elo_range else None
    elo_cap = elo_range[1] if elo_range and len(elo_range) > 1 else None
    imp_min = importance_range[0]

    for expansion in range(max_expansions + 1):
        current_elo_min = (elo_min - (expansion * elo_expand_step)) if elo_min is not None else None
        current_elo_cap = (elo_cap + (expansion * 100)) if elo_cap is not None else None
        current_imp_min = max(0.0, imp_min - (expansion * importance_expand_step))

        results = []
        for pid, sim_score in candidates:
            if pid in completed_ids or pid in skip_cooldown_ids or pid in discarded_ids:
                continue

            tags = TAG_LOOKUP.get(pid)
            if not tags:
                continue

            primary_sub = tags["primary_subtopic"]["name"]
            if not prereqs_met(state, primary_sub):
                continue

            prob_elo = tags.get("difficulty", 0)
            if current_elo_min is not None and prob_elo < current_elo_min:
                continue
            if current_elo_cap is not None and prob_elo > current_elo_cap:
                continue

            prob_imp = tags.get("importance", 0)
            if prob_imp < current_imp_min:
                continue

            prob = PROB_LOOKUP.get(pid, {})
            results.append({
                "id": pid,
                "title": prob.get("title", ""),
                "slug": prob.get("slug", ""),
                "elo": prob_elo,
                "importance": prob_imp,
                "primary_subtopic": primary_sub,
                "similarity": round(sim_score, 4),
            })

            if len(results) >= max_results:
                break

        if results:
            return results

    return []


# ── Direct subtopic search ───────────────────────────────────────

def search_by_subtopic(
    subtopic,
    elo_range,
    importance_range,
    state,
    completed_ids,
    skip_cooldown_ids,
    discarded_ids,
    max_results=5,
    elo_expand_step=50,
    importance_expand_step=0.05,
    max_expansions=5,
):
    """
    Search for problems by subtopic name with elo/importance filters.
    Primary matches first, then secondary (sorted by weight) if needed.
    Widens bounds incrementally if too few results.
    """

    mastery = state.get("subtopics", {}).get(subtopic, {}).get("score", 0.0)
    is_bronze = mastery < ELO_MASTERY_THRESHOLD

    elo_cap = elo_range[1] if elo_range and len(elo_range) > 1 else None

    def _filter(pid, elo_min, cur_elo_cap, imp_min):
        if pid in completed_ids or pid in skip_cooldown_ids or pid in discarded_ids:
            return None
        tags = TAG_LOOKUP.get(pid)
        if not tags:
            return None
        primary_sub = tags["primary_subtopic"]["name"]
        if not prereqs_met(state, primary_sub):
            return None
        prob_elo = tags.get("difficulty", 0)
        if elo_min is not None and prob_elo < elo_min:
            return None
        if cur_elo_cap is not None and prob_elo > cur_elo_cap:
            return None
        prob_imp = tags.get("importance", 0)
        if prob_imp < imp_min:
            return None
        prob = PROB_LOOKUP.get(pid, {})
        return {
            "id": pid,
            "title": prob.get("title", ""),
            "slug": prob.get("slug", ""),
            "elo": prob_elo,
            "importance": prob_imp,
            "primary_subtopic": primary_sub,
            "match_type": None,  # filled by caller
            "weight": None,
        }

    elo_min = elo_range[0] if elo_range else None
    min_secondary_weight = 0.15

    # Bronze: 90th percentile importance gate, sort by elo ascending
    # Silver+: LLM selectivity-based importance gate, sort by score
    if is_bronze:
        imp_values = SUBTOPIC_IMP_VALUES.get(subtopic, [])
        if imp_values:
            idx_90 = int(0.9 * (len(imp_values) - 1))
            imp_min = imp_values[idx_90]
        else:
            imp_min = 0.7  # fallback
    else:
        imp_min = importance_range[0]

    all_candidates = []
    seen_ids = set()

    elo_cap_expand_step = 100  # cap expands upward faster than floor expands downward

    for expansion in range(max_expansions + 1):
        cur_elo_min = (elo_min - (expansion * elo_expand_step)) if elo_min is not None else None
        cur_elo_cap = (elo_cap + (expansion * elo_cap_expand_step)) if elo_cap is not None else None
        cur_imp_min = max(0.0, imp_min - (expansion * importance_expand_step))
        decay = 1.0 - (expansion * 0.1)

        for pid in PRIMARY_INDEX.get(subtopic, []):
            if pid in seen_ids:
                continue
            r = _filter(pid, cur_elo_min, cur_elo_cap, cur_imp_min)
            if r:
                w = TAG_LOOKUP[pid]["primary_subtopic"]["weight"]
                r["match_type"] = "primary"
                r["weight"] = w
                r["score"] = r["elo"] if is_bronze else 1.0 * w * decay
                all_candidates.append(r)
                seen_ids.add(pid)

        for pid, weight in SECONDARY_INDEX.get(subtopic, []):
            if pid in seen_ids or weight < min_secondary_weight:
                continue
            r = _filter(pid, cur_elo_min, cur_elo_cap, cur_imp_min)
            if r:
                r["match_type"] = "secondary"
                r["weight"] = weight
                r["score"] = r["elo"] if is_bronze else 0.5 * weight * decay
                all_candidates.append(r)
                seen_ids.add(pid)

        # Bronze: check if we have enough after this expansion
        if is_bronze and len(all_candidates) >= max_results:
            break

    if is_bronze:
        # Primaries first, then elo ascending within each group
        all_candidates.sort(key=lambda x: (x["match_type"] != "primary", x["score"]))
    else:
        # Sort by score descending (best match first)
        all_candidates.sort(key=lambda x: -x["score"])
    return all_candidates[:max_results]
