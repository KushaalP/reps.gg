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
- fine tune minimum depth
- handle decay/progress loss/spaced repetition with recent struggle so its more adaptive (recent fails, etc.)
- work on targeted learning mode (seperate prompt, ignore prereqs)
- Interview Mode

# General Notes

- add a filter if user is lc premium or not to reccommend premium problems
- need a way to look through solutions and see which solution the user chose, like if they chose to use union find for example, update mastery accordingly (maybe not in mvp)
- company specific can just look at company patterns and tag if it fits will enough, or can just pull from existing company tags, and enrich with similar/consensus if not enough (maybe no enrich though cuz that may be decpetive, or maybe disclaimer once exhausted)
- maybe for ux/ui thing, don't show progress per subpattern unless explciitly expanded, it should just be showing gain for the full topic, this way it's not overwhelming
- this is a big one and unsure if turly needed/maybe post mvp, but instead of tagging llms, handpick, or ig llm pick a much more selected set of interview relevant patterns, potentially compile a bunch of mega lists, sort somehow (probably by elo or whatever), can have tiers, u need a certain amount to graduate a tier, can easily drop down a tier
makes a lot of the math more simple, and has less noisy recos
- another potentially big one, to build patterns, you actually may genuinely need targeted learning at first to be enforced, otherwise foundations are shaky. this is fixable within the current product, but need to figure this one out.
    - this could be phase gating, overall mastery maybe gates certain topics
    - or increase minimum depth/fine tune it
    - recent failure stuff somewhat handles this (recent failure focuses on topics esp when weak, need to handle for failures at different tiers thoguh)
    - maybe a frontier gate, don't have more than 5 new active subskills, unless certain threshold of mastery is reached overall
    - potentially just increase preereq min mastery
    - overall it is important to maintain the depth vs breadth balance that smth like the nc150 does, recos need to reflect that
    - may need to reexamine the 10 slots approach, that maybe is too wide and not adaptive enough, potentially less slots and we can backlog until certain thresholds r met though to limit api calls
    - spaced reptition through decay, option to move mastery down, maybe while deciding can offer example problems and range so they have good idea in a modal
    - we can reenable even clean solves after a month since solve i think, smaller thresholds for fails
    - can have start from begenning option, this option overrides and resets all in that category to unsolved

