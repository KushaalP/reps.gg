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

# General Notes

- for targeted practice, we may need to ignore prereq graph, but also warn users that they may ecounter new patterns
- starting problem handpicked by me for each pattern if unseen
- maybe we only do elo drop for spaced reptition (when reco randomly chooses, and u fail, then u drop significantly)
- another mastery thing can be placement rounds for users with existing leetcode history, theyre given a problem at their level/below, and first few can bump them down (would probably only be for gold and above)
- handle reco engine's specing into things like bitmask dp, dont handle in mastery weighting, thats fine how it is
- come back to tests when reco engine is fully polished
- will probably change instead of solve w hints blah blah, ill do sclae of ese 1-5, adjust mastery calc accordingly, need to tune with that
- need to absorb certain subtopics into others
- add a filter if user is lc premium or not to reccommend premium problems
- need a way to look through solutions and see which solution the user chose, like if they chose to use union find for example, update mastery accordingly (maybe not in mvp)
- we should maybe pass in a recently struggled this many times or smth later on
