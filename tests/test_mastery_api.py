"""
Tests for the reps.gg mastery model and API.

1. Happy path: solve a problem clean → mastery increases
2. Edge case: solve at mastery cap (100) → score stays clamped
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.mastery import (
    new_user_state,
    update_mastery,
    compute_attempt_score,
    get_subtopic_tier,
    get_overall_level,
    _ensure_subtopic,
)
from lib.reco_engine.data import TAG_LOOKUP, TAXONOMY


def test_clean_solve_increases_mastery():
    """Happy path: solving a problem clean should increase the primary subtopic score."""
    state = new_user_state()

    # Pick a real problem from the tag lookup
    pid = next(iter(TAG_LOOKUP))
    tags = TAG_LOOKUP[pid]
    primary = tags["primary_subtopic"]["name"]

    old_score = state.get("subtopics", {}).get(primary, {}).get("score", 0.0)

    state = update_mastery(
        state, pid, tags,
        used_hints=False, looked_at_solution=False, struggled=False,
    )

    new_score = state["subtopics"][primary]["score"]
    assert new_score > old_score, (
        f"Clean solve should increase mastery: {old_score} -> {new_score}"
    )
    print(f"PASS: Clean solve increased {primary}: {old_score} -> {new_score}")


def test_mastery_clamped_at_100():
    """Edge case: mastery should never exceed 100 even with repeated clean solves."""
    state = new_user_state()

    pid = next(iter(TAG_LOOKUP))
    tags = TAG_LOOKUP[pid]
    primary = tags["primary_subtopic"]["name"]

    # Force the score to 99
    _ensure_subtopic(state, primary)
    state["subtopics"][primary]["score"] = 99.0

    state = update_mastery(
        state, pid, tags,
        used_hints=False, looked_at_solution=False, struggled=False,
    )

    new_score = state["subtopics"][primary]["score"]
    assert new_score <= 100.0, (
        f"Mastery should be clamped at 100, got {new_score}"
    )
    print(f"PASS: Mastery clamped at {new_score} (<=100)")


def test_struggled_gives_zero():
    """Edge case: struggling with a problem should give 0 mastery change."""
    state = new_user_state()

    pid = next(iter(TAG_LOOKUP))
    tags = TAG_LOOKUP[pid]
    primary = tags["primary_subtopic"]["name"]

    _ensure_subtopic(state, primary)
    state["subtopics"][primary]["score"] = 40.0

    old_score = 40.0

    state = update_mastery(
        state, pid, tags,
        used_hints=False, looked_at_solution=False, struggled=True,
    )

    new_score = state["subtopics"][primary]["score"]
    assert new_score == old_score, (
        f"Struggled should give 0 change: {old_score} -> {new_score}"
    )
    print(f"PASS: Struggled gave 0 change, score stayed at {new_score}")


if __name__ == "__main__":
    test_clean_solve_increases_mastery()
    test_mastery_clamped_at_100()
    test_struggled_gives_zero()
    print("\nAll tests passed!")
