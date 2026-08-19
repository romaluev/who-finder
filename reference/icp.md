# ICP fit — local rules, attributed points

Fit answers "is this worth your time" with arithmetic you can read, not a model opinion. Every point lands in `fit_reasons`, so `why is this a 78?` is always answerable.

## Where the config comes from

Resolution order:

1. `--icp /path/to.json`
2. `$WHO_FINDER_ICP`
3. `.who-finder/icp.json` (or `$WHO_FINDER_HOME/icp.json`)
4. built-in generic rules, with the topic gate derived from the search brief

`who-finder icp init` writes an editable template. `who-finder icp show --agent` prints what is active — it reports `(none — using built-in generic rules)` when running on defaults, so nobody mistakes the fallback for a configured ICP.

## Config

```json
{
  "name": "my-icp",
  "must_any": ["ai video", "generative video"],
  "boost": { "founder": 15, "head of": 12, "agency": 10 },
  "penalty": { "student": -20, "intern": -15 },
  "audience": { "min": 1000, "sweet_min": 10000, "sweet_max": 2000000, "weight": 20 },
  "geo": { "prefer": ["united states", "united kingdom"], "weight": 8 },
  "signals": { "hiring": 10, "funded": 12, "recent-round": 10 }
}
```

Every key is optional. Keys are matched as lowercase substrings against the haystack: headline + snippet + bio + name + topics + recent post titles + company industry + specialties.

- `must_any` is a **gate**, not a booster. Present and unmatched caps the row at `weak`.
- `boost` is capped at +30 total, `penalty` floored at −30, so no single list can dominate.
- `audience` compares whatever that platform reports — followers, subscribers, or employees.

## Scoring

Base 40, then:

| component | effect |
|---|---|
| topic gate matched | +18 |
| topic gate present, profile has text, no match | −12 and band capped at `weak` |
| boost terms | sum, max +30 |
| penalty terms | sum, min −30 |
| audience inside `sweet_min..sweet_max` | +weight |
| audience outside the band | +weight/3 |
| audience below `min` | −weight/2 |
| geo match | +weight |
| each matching signal | its configured points |

Clamped to 0–100.

## Bands

| band | meaning |
|---|---|
| `strong` | ≥70 **and** the profile was actually fetched |
| `possible` | ≥52 |
| `weak` | ≥34, or the topic gate failed |
| `off` | below that |
| `unknown` | no profile text at all — we never learned enough to judge |

Two rules exist to stop the tool overclaiming:

**Unenriched rows cannot be `strong`.** A search snippet can read beautifully, but we did not open the profile. Those rows are capped at `possible` with the gap `profile not fetched — capped at possible; run enrich to confirm`.

**Missing data is `unknown`, never `off`.** Ranking an unfetched profile as a hard no is how a tool like this quietly buries the best lead in the list. `unknown` sorts down via a priority penalty, but it is never presented as a rejection.

## Priority

The sort key blends three things, because the best fit with no reach and the biggest account with no fit are both bad first calls:

```
priority = 0.60 × fit + 0.25 × reach + 8 if new − 6 if unknown
```

`reach` is log-scaled — 1k → 30, 10k → 50, 100k → 70, 1M → 90 — because the gap between 5k and 50k followers matters far more than the gap between 2M and 5M. Linear reach would let one huge account own every ranking.

Entities with no follower count (Google-indexed rows) fall back to a damped engagement proxy so they are not automatically last.

## When the results feel wrong

Editing `icp.json` is the fix. Tell the user that. Re-ranking in prose is not — it throws away the attribution that makes the number trustworthy.
