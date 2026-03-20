# reps.gg System Design Flashcards

## Mastery Model

1. **Q: What are the 4 quality scores and their point values?**
A: solved_clean: 4.0, solved_with_hints: 3.25, solved_after_solution: 2.5, struggled: 0.0

2. **Q: What is the full mastery change formula?**
A: change = quality_score × difficulty_multiplier × importance_gate × mastery_rate × diminishing_returns

3. **Q: What is the difficulty multiplier formula?**
A: expected_elo = 800 + (mastery/100) × 1900. multiplier = clamp(1.0 + 0.5 × (problem_elo - expected_elo) / 500, 0.3, 2.5)

4. **Q: What is the base ELO at mastery 0? At mastery 100?**
A: 800 at mastery 0, 2700 at mastery 100 (800 + 1900)

5. **Q: What is the difficulty multiplier range?**
A: Min 0.3x, Max 2.5x

6. **Q: What is the normalization factor for the difficulty multiplier?**
A: 500

7. **Q: What happens when a user with mastery 0 solves a 1500-elo problem clean?**
A: expected_elo = 800, delta = (1500-800)/500 = 1.4, mult = 1.0 + 0.5×1.4 = 1.7. Change = 4.0 × 1.7 = 6.8 (before other factors)

8. **Q: What is the importance gate threshold and discount?**
A: Threshold: 0.2. Problems below get 25% of normal gain (discount = 0.25)

9. **Q: When do diminishing returns kick in and what's the max reduction?**
A: Kicks in at Gold (mastery 40). Max reduction: 0.7 (at mastery 100, gains are 30% of normal)

10. **Q: What is the diminishing returns formula?**
A: dampening = 1.0 - ((mastery - 40) / 60) × 0.7. Only applies when mastery > 40.

11. **Q: What dampening does a user with mastery 70 get?**
A: excess = (70-40)/60 = 0.5. dampening = 1.0 - 0.5 × 0.7 = 0.65 (65% of normal gain)

12. **Q: How are secondary subtopic gains calculated?**
A: change × weight × 0.5. Secondary discount is always 0.5.

13. **Q: What are the tier thresholds?**
A: Bronze: 0-19, Silver: 20-39, Gold: 40-59, Platinum: 60-79, Diamond: 80-100

14. **Q: How is mastery_rate calculated per subtopic?**
A: mastery_rate = 40 / (target_solves_to_gold × 2.5). AVG_GAIN_PER_SOLVE = 2.5.

15. **Q: What is the default mastery_rate for subtopics not in config?**
A: 1.0

16. **Q: Why additive scoring instead of ELO?**
A: ELO is relative ranking between users. We need absolute skill measurement per subtopic. ELO also doesn't handle quality dimension or importance weighting.

17. **Q: Why not average scores across solves?**
A: Running additive score lets historical progress compound. Each solve adds value proportional to its difficulty/quality. Averaging would penalize users for attempting hard problems.

18. **Q: What mastery score does the system clamp to?**
A: [0, 100] — both floor and ceiling enforced on every update

19. **Q: How does the system classify quality from boolean flags?**
A: Priority: struggled > looked_at_solution > used_hints > clean. First matching flag determines quality.

20. **Q: How is topic-level mastery calculated?**
A: Importance-weighted average of subtopic scores within that topic

21. **Q: How is overall mastery calculated?**
A: Importance-weighted average of topic scores

## Tagging Pipeline

22. **Q: How many problems are tagged in total?**
A: 3,860

23. **Q: How many topics and subtopics in the taxonomy?**
A: 18 topics, 40+ subtopics

24. **Q: What LLMs were used for the two-pass tagging?**
A: Pass 1: Claude Opus 4.6 (batch size 25). Pass 2: Claude Haiku 4.5 (validation by subtopic groups)

25. **Q: What fields does each tagged problem have?**
A: primary_topic, primary_subtopic (name + weight), secondary_subtopics (list with topic, name, weight), difficulty (elo), importance (0-1), interview_plausibility, company_plausibility (quant/faang/mid/startup)

26. **Q: What must primary + secondary weights sum to?**
A: 1.0 (with ±0.02 tolerance in validation)

27. **Q: What is importance in the tagging system?**
A: Technique transferability — how broadly useful the pattern is. NOT correlated with difficulty. A hard niche problem can have low importance.

28. **Q: How many validation checks does the tagging pipeline run?**
A: 8 checks: invalid names, subtopic-topic mismatch, weight integrity, weight ordering, difficulty bounds, NC250 importance floor, plausibility contradictions, importance-interview sanity

29. **Q: What is the NC250 importance floor?**
A: NC250 problems must have importance >= 0.5

30. **Q: What are the difficulty bounds for Easy/Medium/Hard?**
A: Easy capped at 1800 elo, Medium capped at 2400 elo, Hard minimum 1200 elo

31. **Q: What is the corrective pass error threshold?**
A: Only flags misclassifications or score errors > 0.25

32. **Q: How are calibration anchors used?**
A: 7 known problems with Zerotrac elo ratings (e.g. Two Sum: 1130, Maximum Frequency Stack: 2028, Critical Edges: 2572) anchor the difficulty scale

33. **Q: Why is importance decoupled from difficulty?**
A: A 3000-elo problem can be low importance (niche trick), and a 1100-elo problem can be high importance (foundational pattern like Two Sum). This drives the mastery formula — high-importance problems give more gain.

## Recommendation Engine

34. **Q: What is the recommendation flow end-to-end?**
A: Code builds context → LLM picks 10 subtopics + selectivity → code matches real problems via subtopic search → queue serves one per slot

35. **Q: What does the LLM output for each recommendation?**
A: {topic, subtopic, selectivity: 10-80}

36. **Q: What does selectivity 70-80 mean?**
A: Very selective — only the most foundational/high-yield problems. For subtopics where user is just starting out.

37. **Q: What does selectivity 10-25 mean?**
A: Wide open — nearly all problems pass including niche. For advanced users (Diamond) who've seen most common patterns.

38. **Q: How many recommendations does the LLM generate?**
A: Always 10

39. **Q: What context does the LLM see?**
A: Taxonomy with importance weights, prerequisite graph, per-subtopic mastery (scores + tiers + attempt counts + LOCKED/EXHAUSTED flags), last 5 attempts, top 5 stale subtopics, active topic filter

40. **Q: What is the rule-based fallback?**
A: Picks 10 weakest eligible subtopics sorted by gap-to-overall × importance, max 3 per topic for variety. Selectivity = clamp(70 - score, 10, 80).

41. **Q: When does the rule-based fallback trigger?**
A: When the LLM call throws an exception, or when the LLM returns empty profiles

42. **Q: Why LLM-as-recommender instead of pure algorithmic?**
A: LLM can reason about nuanced patterns: "user is strong at BFS but weak at multi-source BFS." Rule-based can't express this without complex heuristics.

43. **Q: Why calculations over embeddings for candidate search?**
A: Embeddings find semantically similar problems, but we need specific subtopic + difficulty + importance control. Direct filtering is more precise, explainable, and tunable per dimension.

## Candidate Search

44. **Q: How does search_by_subtopic work for Bronze users?**
A: 90th percentile importance gate (only high-quality problems), sort by elo ascending (easiest first), no mastery-based weighting

45. **Q: How does search_by_subtopic work for Silver+ users?**
A: LLM-selectivity-based importance gate, weighted scoring (1.0 × weight × decay for primary, 0.5 × weight × decay for secondary), sort by score descending

46. **Q: What is the ELO floor percentile mapping formula?**
A: floor_pct = 10 + ((mastery - 25) / 75) × 65. Maps mastery 25-100 to percentile 10-75 in the subtopic's elo distribution.

47. **Q: How is the ELO cap computed?**
A: filtered_median + (mastery/100) × (filtered_max - filtered_median). Uses importance-filtered elo distribution.

48. **Q: What are the expansion parameters?**
A: elo_expand_step: 50 (floor), 100 (cap). importance_expand_step: 0.05. max_expansions: 5.

49. **Q: Why does the elo cap expand faster than the floor?**
A: Allows upside growth more aggressively. Users benefit from attempting harder problems, not easier ones.

50. **Q: What is the decay factor per expansion?**
A: decay = 1.0 - (expansion × 0.1). Problems found in later (wider) expansions are penalized in ranking.

51. **Q: What is the minimum secondary weight to be considered?**
A: 0.15. Below that, cross-topic matches are ignored.

52. **Q: What scoring formula is used for primary matches (Silver+)?**
A: 1.0 × weight × decay

53. **Q: What scoring formula is used for secondary matches (Silver+)?**
A: 0.5 × weight × decay

54. **Q: How many candidates per slot?**
A: Up to 5

55. **Q: What happens when no candidates are found after all expansions?**
A: Slot persists with empty candidate list. Queue skips it during get_next().

## Queue Management

56. **Q: How does mark_skipped work?**
A: Add problem to skip_cooldown, increment current_index, move slot to back of queue

57. **Q: How does mark_discarded work?**
A: Add problem to discarded (permanent exclusion), increment current_index, move slot to back of queue

58. **Q: What's the difference between skip_cooldown and discarded?**
A: Skip is temporary — problem can be re-served in future sessions. Discard is permanent — never shown again.

59. **Q: When is the queue considered empty?**
A: When all slots are either completed or have current_index >= candidate count

60. **Q: Why rotate skipped/discarded slots to the back?**
A: Ensures all slots get a chance. Prevents a single problematic slot from blocking the entire queue.

## Monte Carlo Simulation

61. **Q: How many journeys and problems per Monte Carlo run?**
A: 500 journeys × 300 problems per archetype

62. **Q: What are the 8 Monte Carlo archetypes?**
A: slow_learner, fast_learner, avg_learner, targeted_learner, rogue, comfort_zone, contest_bro, easy_grinder (plus one_trick)

63. **Q: What checkpoints does Monte Carlo measure?**
A: [50, 100, 150, 200, 250, 300] problems

64. **Q: What does Monte Carlo measure at each checkpoint?**
A: Overall mastery, avg subtopic mastery, subtopics touched, tier distribution

65. **Q: What are the calibration targets?**
A: NC150 completion ≈ Silver/low Gold (30-40). NC250 completion ≈ comfortable Gold (45-55).

66. **Q: How does the slow_learner archetype perform on hard problems?**
A: struggled 25%, solution 35%, hints 25%, clean 15%

67. **Q: How does the fast_learner archetype perform at-level?**
A: struggled 2%, solution 5%, hints 13%, clean 80%

68. **Q: What defines the contest_bro archetype?**
A: Only attempts hard problems (elo > 2000), fails frequently (struggled 45% on hard problems)

69. **Q: What defines the comfort_zone archetype?**
A: Only does Arrays/Hashing, never touches graphs/DP/trees. High quality on what they do attempt.

70. **Q: What defines the rogue archetype?**
A: Random topics, ignores recommendations. 35% fixates on random previous subtopic, 65% picks any random subtopic.

71. **Q: How does the targeted_learner pick topics?**
A: Picks weakest topic that hasn't hit Silver (25+), stays on it until Silver, then moves to next weakest

72. **Q: What is the gap threshold between "above/at/below" in simulation?**
A: 200 ELO. Above = gap > 200, at = -200 to 200, below = gap < -200

73. **Q: What does Monte Carlo tune?**
A: Mastery rates, reco engine mode thresholds, prerequisite system (PREREQ_MIN_MASTERY), subtopic filtering strategies

## Resume Enrichment

74. **Q: What is the max mastery bump from resume alone?**
A: 35 (Silver tier cap)

75. **Q: When does resume enrichment skip a subtopic?**
A: When current score >= 20 (practice data is more reliable than resume inference)

76. **Q: What size bumps does the system prefer?**
A: Small bumps, 5-15 points. Never large jumps.

77. **Q: Give an example of evidence that warrants a bump.**
A: "Built a graph-based recommendation engine" → BFS/DFS subtopics +10-15

78. **Q: Give an example that does NOT warrant a bump.**
A: "Familiar with data structures" — too vague, no concrete evidence

79. **Q: What LLM is used for resume enrichment?**
A: gpt-5-mini with JSON object output format

80. **Q: What happens if the input is not a resume?**
A: LLM returns {error: "not_a_resume", message: "..."}, frontend shows red error, user stays on step

81. **Q: Why cap at Silver and not higher?**
A: Resume shows familiarity, not mastery. Mastery comes from actual practice. Cap prevents inflated starting scores.

## API & Architecture

82. **Q: What is the tech stack?**
A: Next.js 16 frontend, FastAPI backend, gpt-5-mini for LLM calls, in-memory state

83. **Q: How is state stored currently?**
A: In-memory Python dicts (single user). _state, _completed_ids, _skip_cooldown_ids, _discarded_ids, _queue, _goal

84. **Q: How does the frontend talk to the backend?**
A: Next.js rewrites /api/* to FastAPI on port 8000 (resume enrichment calls backend directly due to Turbopack proxy issue)

85. **Q: How does the LeetCode import treat all matched solves?**
A: As "hints" quality (used_hints=True) — conservative estimate since we don't know how they actually solved

86. **Q: What are the 7 API endpoints?**
A: POST /api/connect, POST /api/connect-demo, GET /api/profile, POST /api/recommend, POST /api/solve, POST /api/skip, POST /api/enrich-resume, POST /api/goal

87. **Q: What does the solve endpoint return?**
A: Rich feedback: primary (subtopic, oldScore, newScore, delta, oldTier, newTier, tierChanged), secondary changes array, overall (oldScore, newScore, delta)

88. **Q: What are the goal target scores?**
A: FAANG: 50, Quant: 65, Mid-tech: 40, Startup: 30, General: 35

## Scaling & System Design

89. **Q: How would you scale to multi-user?**
A: PostgreSQL for state, Redis for queue caching, stateless API servers behind load balancer. Schema: users, mastery_scores (user_id, subtopic, score, last_attempted), solve_history

90. **Q: How would you handle concurrent solves on the same subtopic?**
A: Optimistic locking — read score + version, compute change, write with version check. Retry on conflict.

91. **Q: How would you reduce LLM latency for recommendations?**
A: Cache recommendations, pre-generate on solve events, batch similar mastery profiles, or fine-tune a smaller model on LLM outputs

92. **Q: How would you implement decay?**
A: Lazy evaluation on read. effective_score = stored_score × decay_factor(days_since_last_attempt). Only write back on next solve. Grace period of ~7 days.

93. **Q: How would you handle the Chrome extension?**
A: Content script on leetcode.com/problems/* detects submission → POST to API → show mastery change in popup → dashboard auto-refreshes via websocket

94. **Q: How do you prevent gaming?**
A: Difficulty multiplier caps easy-grinding gains, importance gate discounts niche problems, diminishing returns taper post-Gold, quality is self-reported but cross-validated by difficulty context

95. **Q: How would you secure LeetCode tokens in production?**
A: OAuth flow instead of raw cookies, token encryption at rest, never persist session tokens in DB, only hold in memory during sync

96. **Q: How would you handle PII in resumes?**
A: Data processing agreement with OpenAI, option to opt out, strip PII before sending to LLM, never persist resume text — only store resulting mastery bumps

97. **Q: What is the prerequisite system?**
A: Hard prereqs map subtopics to required prerequisite subtopics. User must have >= PREREQ_MIN_MASTERY in prereqs before a subtopic unlocks. Checked in search and shown as [LOCKED] to LLM.

98. **Q: What is the spaced repetition design?**
A: Shaky solves (hints/solution) get 30-day cooldown before re-serving. Shaky twice = permanently discarded. Stale subtopics (no activity for STALE_THRESHOLD_DAYS) flagged for review.

99. **Q: Why 200 synthetic problems for the demo?**
A: Hackathon rules required synthetic data only, no scraping. Extracted top 200 by importance from full corpus to maintain realistic topic distribution.

100. **Q: What are the 3 tests and what do they verify?**
A: (1) Clean solve increases mastery — happy path. (2) Mastery clamped at 100 — edge case overflow. (3) Struggled gives zero change — edge case for 0.0 quality score.
