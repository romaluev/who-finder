# Insights — why the engine writes the summary

Hand a model twenty rows and ask for takeaways and it will produce a confident paragraph whether or not the rows support one. `insights.py` exists so every sentence in `WHAT I FOUND` is derived from a count the engine can point at.

The agent pastes these lines. It does not rewrite them, and it does not add findings of its own.

## Coverage — the distinction that matters most

Each planned query ends in one of three states:

| state | rendered | means |
|---|---|---|
| `ok` | `youtube:yt ok(12)` | ran, returned rows |
| `no-results` | `x:x no-results` | ran fine, genuinely empty |
| `error` | `web:w ERROR` | never completed |

**"We found no X" and "we did not successfully look for X" are different claims.** A source that errored appears in `GAPS` under *sources that errored (absence here is not evidence)*. Reporting that as "nothing out there" is the single most damaging thing this tool could do, because the user acts on absence.

## Findings

Emitted only when the underlying data exists:

- entity count, split new versus already in roster, by platform
- audience median and max, plus **how many profiles actually reported a number** — never a median that hides a tiny sample
- count of masked LinkedIn profiles, with the reminder that those role lines come from the search snippet
- ICP band distribution
- signal rollup (hiring, funded, recent-round, verified…)
- recurring themes from clustering
- count of discovery-only rows whose fit is provisional

Grammar is generated with `plural()`; `1 entity`, not `1 entities`. Small thing, but a report that says "1 profiles" reads like nobody checked it.

## Clusters

Themes come from shared profile vocabulary, with three guards:

- fewer than **4 enriched dossiers** → no clusters at all, because shared words among three profiles are coincidence
- a term in more than 80% of profiles is dropped — if everyone says "video" on a video search, that is the query echoing back, not a finding
- terms shorter than 4 characters are dropped, and a stopword list strips verbs like *make*, *build*, *teach* that describe grammar rather than a market

Each entity is assigned to one theme only, so cluster sizes sum honestly instead of double-counting.

## Gaps

- sources that errored
- sources that ran and returned nothing
- enriched profiles exposing no follower count
- the first few raw errors, verbatim

If `GAPS` is empty, the run was genuinely clean. That is worth trusting precisely because the section is not decorative.
