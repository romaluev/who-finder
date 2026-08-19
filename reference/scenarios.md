# Scenarios

The engine classifies the brief, then runs that scenario's angles. You do not pick Google operators, and you do not merge scenarios into one crawl.

- [Detection order](#detection-order)
- [Topic extraction](#topic-extraction)
- [What each scenario is for](#what-each-scenario-is-for)
- [Angle weighting](#angle-weighting)
- [Overriding detection](#overriding-detection)
- [Choosing depth and freshness](#choosing-depth-and-freshness)

## Detection order

First match wins, after the compare regex:

```
compare → hiring → press → creators → companies → people
```

The order encodes specificity. `who is hiring for AI video` contains a person-word (`who`) and a company context, but `hiring` is checked earlier because it is the more specific reading. `people` is last because it is the fallback: most briefs about humans do not announce themselves.

**Person-words beat company-words.** `people at AI video companies` is `people`, not `companies` — the brief names humans as the target and companies as the location. This is the single most common misclassification when a human overrides the detector by hand.

## Topic extraction

The brief is not the query. The engine strips:

- filler: `find`, `me`, `us`, `please`, `looking for`, `can you`
- scenario words: `founders`, `companies`, `creators`, `hiring`, `journalists`

so `find me founders of AI video tools` yields the topic `ai video tools`.

**Quoted phrases survive verbatim.** `people posting "text to video"` gives the topic `text to video` exactly, which is how you force a multi-word phrase the stripper would otherwise break up. Reach for quotes when the topic is a term of art.

A brief with no topic after stripping ("find me some good people") produces zero steps and exits 2. Ask one short question rather than inventing a subject.

## What each scenario is for

| scenario | you are looking for | not for | score mode |
|---|---|---|---|
| [people](people.md) | named humans — founders, operators, ICs | subscriber lists, job reqs | presence |
| [companies](companies.md) | orgs with a public page | individual creators | presence |
| [creators](creators.md) | people whose **posts** match the topic | execs who never publish | engagement |
| [hiring](hiring.md) | companies with a public req | candidates | presence |
| [press](press.md) | bylines, hosts, interviewers | brand social accounts | presence |
| [compare](compare.md) | two briefs, same sources | three-way bake-offs | presence, two sides |

The `people` / `creators` distinction is the one worth internalising. `people` finds humans who *work on* the topic, whether or not they post. `creators` finds humans whose *content* is about the topic, ranked by how much engagement it earns. A quiet CTO scores zero in `creators` and ranks well in `people`.

## Angle weighting

Each scenario ships three to five queries. The primary source carries weight 1.0 and adjacent angles carry less, so a noisy open-web query cannot outrank a direct LinkedIn `/in` match.

Weights are why you should not flatten a scenario into one query with `--sources`: the ranking depends on several angles disagreeing.

See the exact angles with:

```bash
$BIN find "your brief" --dry-run
```

That prints the queries and the cost ceiling without spending anything, and is the fastest way to check the planner understood the brief.

## Overriding detection

```bash
$BIN find "..." --scenario people|companies|creators|hiring|press|compare
$BIN find "..." --sources youtube,web
```

Use `--scenario` when detection is visibly wrong or the user named the type outright. Do not pass it reflexively — it pre-empts a detector that is usually right, and it is how `people at X companies` becomes a company search.

Use `--sources` to add or restrict platforms within a scenario. Instagram is never a default; it is opt-in via `--sources instagram` only.

## Choosing depth and freshness

`--deep 10` is the default posture: ten enriched rows is enough to qualify a batch, and enrichment is what turns handles into an answer.

`--freshness month` is the default. Move to `year` when the space is small and a month returns too little — common for `people` and `companies` in a niche. `all` drops date filters entirely and is right for evergreen questions ("who are the established voices"), wrong for "who is active right now".

Freshness applies to discovery, not to profiles: an enriched dossier always reflects the profile as it is today.
