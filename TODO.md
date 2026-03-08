# reps.gg TODO

# below is LLM BS
## Reco Engine
- [ ] Score ties in Silver+ — multiple primary w=1.0 candidates all score 1.000 with no tiebreaker
- [ ] Weight in Silver+ scoring — consider only using weight for secondary matches, not primaries

## Mastery Model
- [ ] 1-10 quality scale — replace categorical (clean/hints/solution/struggled) with 1-10 self-report, normalize to 0-4 quality score
- [ ] Solution/approach detection — detect which subtopic the user actually used (e.g. Union-Find vs BFS), update mastery accordingly (post-MVP)

## Learning Loop Simulation
- [ ] Add more learner profiles (grinder, casual, etc.)
- [ ] Add shaky problem tracking / re-serve logic
- [ ] Validate prereqs against real mastery state (not log parsing)

## General
- [ ] Commit current changes (perceived_difficulty removal, elo caps, learning loop, rashmith profile)

# My TODO
- normalize 1-10
- handle decay/progress loss/spaced repetition with recent struggle so its more adaptive (recent fails, etc.)
- work on targeted learning mode (seperate prompt, ignore prereqs)
- Interview Mode

# General Notes

- add a filter if user is lc premium or not to reccommend premium problems
- need a way to look through solutions and see which solution the user chose, like if they chose to use union find for example, update mastery accordingly (maybe not in mvp)
- company specific can just look at company patterns and tag if it fits will enough, or can just pull from existing company tags, and enrich with similar/consensus if not enough (maybe no enrich though cuz that may be decpetive, or maybe disclaimer once exhausted)
- 

