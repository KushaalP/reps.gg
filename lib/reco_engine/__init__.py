"""
reps.gg Recommendation Engine

LLM-driven problem recommendation with direct subtopic matching.

Flow:
1. Code assembles context (mastery state, taxonomy, prereqs, history, stale flags)
2. LLM outputs 10 problem profiles (subtopic + selectivity)
3. Each profile → direct subtopic search (primary then secondary by weight)
4. Code filters: completed, skip cooldown, discarded, prereq-gated, elo/importance bounds
5. Queue serves one problem per slot; skips rotate to back of queue
6. Re-call LLM when queue is empty or bulk import (10+) invalidates it
"""

import numpy as np
from openai import OpenAI

# ── Public API re-exports ────────────────────────────────────────

from lib.reco_engine.data import (
    TAGGED, PROBLEMS, TAXONOMY,
    TAG_LOOKUP, PROB_LOOKUP,
    ALL_SUBTOPICS, SUBTOPIC_TO_TOPIC,
    SUBTOPIC_ELO_STATS, SUBTOPIC_ELO_VALUES, SUBTOPIC_ELO_IMP_PAIRS,
    SUBTOPIC_IMP_VALUES,
    HARD_PREREQS, PRIMARY_INDEX, SECONDARY_INDEX,
    EMB_IDS, EMB_VECTORS,
    PREREQ_MIN_MASTERY, STALE_THRESHOLD_DAYS, ELO_MASTERY_THRESHOLD,
)

from lib.reco_engine.search import (
    prereqs_met, get_locked_subtopics,
    get_stale_subtopics, get_exhausted_subtopics,
    compute_elo_range, compute_importance_range,
    search_by_subtopic, search_candidates, filter_candidates,
    embed_query,
)

from lib.reco_engine.llm import call_llm
from lib.mastery import get_overall_level


# ── Queue management ─────────────────────────────────────────────

class RecoQueue:
    """
    Manages the recommendation queue.

    Structure: list of slots, each slot has:
      - profile: the LLM-generated profile
      - candidates: list of up to 5 problems
      - current_index: which candidate is being served
      - completed: whether the user finished a problem from this slot
    """

    def __init__(self):
        self.slots = []
        self.raw_llm_output = ""
        self._completed_ids = set()
        self._skip_cooldown_ids = set()
        self._discarded_ids = set()

    def load_exclusions(self, completed_ids, skip_cooldown_ids, discarded_ids):
        self._completed_ids = set(completed_ids)
        self._skip_cooldown_ids = set(skip_cooldown_ids)
        self._discarded_ids = set(discarded_ids)

    def _rule_based_profiles(self, state, exhausted, topic_filter=None):
        """Fallback: pick 10 weakest eligible subtopics, sorted by gap to overall."""
        overall = get_overall_level(state, TAXONOMY)
        candidates = []
        for topic in TAXONOMY["topics"]:
            if topic_filter and topic["name"] != topic_filter:
                continue
            for sub in topic["subtopics"]:
                s_name = sub["name"]
                if s_name in exhausted:
                    continue
                if not prereqs_met(state, s_name):
                    continue
                score = state.get("subtopics", {}).get(s_name, {}).get("score", 0.0)
                gap = overall - score
                candidates.append({
                    "topic": topic["name"],
                    "subtopic": s_name,
                    "selectivity": max(10, min(80, int(70 - score))),
                    "gap": gap,
                    "importance": sub.get("importance", 0.5),
                })
        # Sort by gap (descending), then importance (descending)
        candidates.sort(key=lambda c: (c["gap"], c["importance"]), reverse=True)
        # Take top 10, deduplicate topics for variety
        selected = []
        seen_topics = {}
        for c in candidates:
            t = c["topic"]
            if seen_topics.get(t, 0) >= 3:
                continue
            selected.append({"topic": c["topic"], "subtopic": c["subtopic"], "selectivity": c["selectivity"]})
            seen_topics[t] = seen_topics.get(t, 0) + 1
            if len(selected) >= 10:
                break
        return selected

    def fill(self, state, topic_filter=None, use_embeddings=False):
        """Call LLM and fill the queue with 10 slots. Falls back to rule-based if LLM fails."""
        exhausted = get_exhausted_subtopics(
            self._completed_ids, self._skip_cooldown_ids, self._discarded_ids
        )
        try:
            profiles, self.raw_llm_output = call_llm(state, topic_filter, exhausted)
        except Exception as e:
            print(f"LLM recommendation failed, using rule-based fallback: {e}")
            profiles = self._rule_based_profiles(state, exhausted, topic_filter)
            self.raw_llm_output = "FALLBACK"
        self.slots = []

        if not profiles:
            # Last resort fallback
            profiles = self._rule_based_profiles(state, exhausted, topic_filter)

        if not profiles:
            return

        if use_embeddings:
            # Embedding-based search (legacy)
            queries = [p.get("query", f"Topic: {p.get('topic','')}. Primary subtopic: {p.get('subtopic','')}.") for p in profiles]
            client = OpenAI()
            response = client.embeddings.create(
                model="text-embedding-3-large",
                input=queries,
            )
            query_vecs = np.array([r.embedding for r in response.data])
            query_vecs = query_vecs / np.linalg.norm(query_vecs, axis=1, keepdims=True)

            for i, profile in enumerate(profiles):
                subtopic = profile.get("subtopic", "")
                selectivity = profile.get("selectivity", 50)
                candidates_raw = search_candidates(query_vecs[i], top_k=50)
                imp_range = compute_importance_range(subtopic, selectivity) if subtopic else [0.0, 1.0]
                candidates = filter_candidates(
                    candidates_raw,
                    elo_range=compute_elo_range(state, subtopic, imp_min=imp_range[0]) if subtopic else [800, 2500],
                    importance_range=imp_range,
                    state=state,
                    completed_ids=self._completed_ids,
                    skip_cooldown_ids=self._skip_cooldown_ids,
                    discarded_ids=self._discarded_ids,
                    max_results=5,
                )
                self.slots.append({
                    "profile": profile,
                    "candidates": candidates,
                    "current_index": 0,
                    "completed": False,
                })
        else:
            # Direct subtopic search
            for profile in profiles:
                subtopic = profile.get("subtopic")

                candidates = []
                if subtopic:
                    selectivity = profile.get("selectivity", 50)
                    imp_range = compute_importance_range(subtopic, selectivity)
                    elo_range = compute_elo_range(state, subtopic, imp_min=imp_range[0])
                    mastery = state.get("subtopics", {}).get(subtopic, {}).get("score", 0.0)
                    if mastery < ELO_MASTERY_THRESHOLD:
                        # Bronze override: 90th percentile gate
                        imp_values = SUBTOPIC_IMP_VALUES.get(subtopic, [])
                        if imp_values:
                            idx_90 = int(0.9 * (len(imp_values) - 1))
                            profile["imp_range"] = [imp_values[idx_90], 1.0]
                        else:
                            profile["imp_range"] = [0.7, 1.0]
                    else:
                        profile["imp_range"] = imp_range
                    profile["elo_range"] = elo_range  # store for debugging
                    candidates = search_by_subtopic(
                        subtopic,
                        elo_range=elo_range,
                        importance_range=imp_range,
                        state=state,
                        completed_ids=self._completed_ids,
                        skip_cooldown_ids=self._skip_cooldown_ids,
                        discarded_ids=self._discarded_ids,
                        max_results=5,
                    )
                self.slots.append({
                    "profile": profile,
                    "candidates": candidates,
                    "current_index": 0,
                    "completed": False,
                })

    def get_next(self):
        """Get the next problem to serve. Returns (slot_index, problem) or None."""
        for i, slot in enumerate(self.slots):
            if slot["completed"]:
                continue
            if slot["current_index"] < len(slot["candidates"]):
                return i, slot["candidates"][slot["current_index"]]
        return None

    def mark_completed(self, slot_index):
        """User completed a problem from this slot."""
        self.slots[slot_index]["completed"] = True
        problem = self.slots[slot_index]["candidates"][self.slots[slot_index]["current_index"]]
        self._completed_ids.add(problem["id"])

    def mark_skipped(self, slot_index):
        """User skipped the current problem — advance to next candidate, move slot to back."""
        slot = self.slots[slot_index]
        problem = slot["candidates"][slot["current_index"]]
        self._skip_cooldown_ids.add(problem["id"])
        slot["current_index"] += 1

        # Move this slot to the back of the queue
        self.slots.pop(slot_index)
        self.slots.append(slot)

    def mark_discarded(self, slot_index):
        """User discarded the current problem — never show again, advance candidate."""
        slot = self.slots[slot_index]
        problem = slot["candidates"][slot["current_index"]]
        self._discarded_ids.add(problem["id"])
        slot["current_index"] += 1

        # Move to back
        self.slots.pop(slot_index)
        self.slots.append(slot)

    def is_empty(self):
        """True if all slots are completed or exhausted."""
        for slot in self.slots:
            if not slot["completed"] and slot["current_index"] < len(slot["candidates"]):
                return False
        return True

    def summary(self):
        """Human-readable queue state."""
        lines = []
        for i, slot in enumerate(self.slots):
            profile = slot["profile"]
            status = "DONE" if slot["completed"] else f"{slot['current_index']}/{len(slot['candidates'])}"
            topic = profile.get("topic", "?")
            subtopic = profile.get("subtopic", "?")
            lines.append(f"Slot {i+1} [{status}]: {topic} > {subtopic}")
            if slot["candidates"]:
                current = slot["candidates"][min(slot["current_index"], len(slot["candidates"]) - 1)]
                lines.append(f"  Current: {current['title']} (elo={current['elo']}, imp={current['importance']})")
            else:
                lines.append(f"  No candidates found")
            lines.append("")
        return "\n".join(lines)
