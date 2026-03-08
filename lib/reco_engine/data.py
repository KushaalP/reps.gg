"""
Static data loading, precomputed indexes, and constants.
Loaded once at import time.
"""

import json
import yaml
import os
import statistics
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Load raw data ────────────────────────────────────────────────

with open(os.path.join(_PROJECT_ROOT, "data/core/tagged_problems.json")) as f:
    TAGGED = json.load(f)

with open(os.path.join(_PROJECT_ROOT, "data/core/problems.json")) as f:
    PROBLEMS = json.load(f)

with open(os.path.join(_PROJECT_ROOT, "taxonomy.yaml")) as f:
    TAXONOMY = yaml.safe_load(f)

with open(os.path.join(_PROJECT_ROOT, "prerequisites.yaml")) as f:
    _prereqs = yaml.safe_load(f).get("prerequisites", {})

with open(os.path.join(_PROJECT_ROOT, "data/core/embeddings.json")) as f:
    _emb_data = json.load(f)

# ── Primary lookups ──────────────────────────────────────────────

TAG_LOOKUP = {t["id"]: t for t in TAGGED}
PROB_LOOKUP = {p["id"]: p for p in PROBLEMS}

# ── Embedding matrix ─────────────────────────────────────────────

EMB_IDS = [e["id"] for e in _emb_data]
EMB_VECTORS = np.array([e["embedding"] for e in _emb_data])
EMB_VECTORS = EMB_VECTORS / np.linalg.norm(EMB_VECTORS, axis=1, keepdims=True)

# ── Prereq lookup ────────────────────────────────────────────────

HARD_PREREQS = {}
for _sub_name, _prereq_data in _prereqs.items():
    _hard = _prereq_data.get("hard", [])
    if _hard:
        HARD_PREREQS[_sub_name] = _hard

# ── Subtopic lists ───────────────────────────────────────────────

ALL_SUBTOPICS = []
SUBTOPIC_TO_TOPIC = {}
for _topic in TAXONOMY["topics"]:
    for _sub in _topic["subtopics"]:
        ALL_SUBTOPICS.append(_sub["name"])
        SUBTOPIC_TO_TOPIC[_sub["name"]] = _topic["name"]

# ── Per-subtopic elo distributions ───────────────────────────────

_sub_elos = {}
_sub_elo_imp_pairs = {}
for _t in TAGGED:
    _sub = _t["primary_subtopic"]["name"]
    _elo = _t.get("difficulty", 0)
    _imp = _t.get("importance", 0)
    if _elo:
        _sub_elos.setdefault(_sub, []).append(_elo)
        _sub_elo_imp_pairs.setdefault(_sub, []).append((_elo, _imp))

SUBTOPIC_ELO_STATS = {}
SUBTOPIC_ELO_VALUES = {}
SUBTOPIC_ELO_IMP_PAIRS = {}
for _sub, _elos in _sub_elos.items():
    _elos.sort()
    SUBTOPIC_ELO_VALUES[_sub] = _elos
    SUBTOPIC_ELO_STATS[_sub] = {
        "min": round(_elos[0]),
        "median": round(statistics.median(_elos)),
        "max": round(_elos[-1]),
        "count": len(_elos),
    }
for _sub, _pairs in _sub_elo_imp_pairs.items():
    SUBTOPIC_ELO_IMP_PAIRS[_sub] = _pairs

# ── Per-subtopic importance distributions ────────────────────────

_sub_importances = {}
for _t in TAGGED:
    _imp = _t.get("importance", 0)
    if not _imp:
        continue
    _pname = _t["primary_subtopic"]["name"]
    _sub_importances.setdefault(_pname, []).append(_imp)
    for _s in _t.get("secondary_subtopics", []):
        _sub_importances.setdefault(_s["name"], []).append(_imp)
SUBTOPIC_IMP_VALUES = {}
for _sub, _imps in _sub_importances.items():
    SUBTOPIC_IMP_VALUES[_sub] = sorted(_imps)

# ── Primary/secondary subtopic indexes ───────────────────────────

PRIMARY_INDEX = {}
for _t in TAGGED:
    PRIMARY_INDEX.setdefault(_t["primary_subtopic"]["name"], []).append(_t["id"])

SECONDARY_INDEX = {}
for _t in TAGGED:
    for _s in _t.get("secondary_subtopics", []):
        SECONDARY_INDEX.setdefault(_s["name"], []).append((_t["id"], _s["weight"]))
for _sub in SECONDARY_INDEX:
    SECONDARY_INDEX[_sub].sort(key=lambda x: -x[1])

# ── Constants ────────────────────────────────────────────────────

PREREQ_MIN_MASTERY = 10.0
STALE_THRESHOLD_DAYS = 14
ELO_MASTERY_THRESHOLD = 25
