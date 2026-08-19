# Scoring

Three numbers travel with every row and they answer different questions. Confusing them is the most common analytical error this tool invites.

- [The three numbers](#the-three-numbers)
- [Engagement mode](#engagement-mode)
- [Presence mode](#presence-mode)
- [Compilation damping](#compilation-damping)
- [Priority](#priority)
- [What you may and may not compare](#what-you-may-and-may-not-compare)
- [previous_score](#previous_score)

## The three numbers

| field | question it answers | comparable across platforms? |
|---|---|---|
| `score` | how loudly did this identity show up for this topic | **no** |
| `fit_score` | how well do they match the ICP, 0–100 | yes |
| `priority` | who should we contact first | yes |

`score` is raw and mode-dependent. `fit_score` and `priority` are normalised on purpose so the ranked list can mix a LinkedIn operator and a YouTube channel without lying.

## Engagement mode

Used by the `creators` scenario, where the platform reports real interaction.

```
score = views + 10*likes + 20*comments + 5*shares
```

Summed across every matching hit for one identity. The weights encode effort: a comment costs more than a like, which costs more than a passive view, so a small channel with a genuinely engaged audience can outrank a large one with none.

## Presence mode

Used by `people`, `companies`, `hiring`, `press`, and `compare` — every scenario whose rows come from a Google index.

```
score = 10 * hit_count
```

**Google-indexed rows carry no engagement data whatsoever.** There are no views to report, and any number that looked like engagement on a LinkedIn row would be fabricated. Presence scoring says only "this identity appeared for several of our angles", which is a weak but honest signal: repeat appearance across independent queries beats a single hit.

Say this out loud when presenting LinkedIn results. Users assume a ranked list is engagement-ranked unless told otherwise.

## Compilation damping

Titles shaped like `best of`, `top N`, `lofi`, `N hours`, `playlist`, `mix` get flagged `compilation` and their score divided by 5.

These videos accumulate enormous view counts while telling you nothing about whether the channel owner works on your topic. Without damping, a single "10 HOURS of AI music" upload outranks every practitioner in the results.

The flag stays on the row, so a damped score is auditable rather than mysterious.

## Priority

The ranking key for `WHO TO CONTACT`:

```
priority = 0.60 * fit_score
         + 0.25 * reach_points(audience)
         + novelty bonus
```

`reach_points` is log-scaled, because the difference between 1k and 10k followers matters far more than between 500k and 510k:

| audience | points |
|---|---|
| 1,000 | 30 |
| 10,000 | 50 |
| 100,000 | 70 |
| 1,000,000 | 90 |

The novelty bonus lifts names the user has not seen before, so a fresh strong match outranks an equally strong name already sitting in the roster. That is deliberate: the point of the tool is new names.

Fit dominates at 60% because reach without fit is a bad lead. A million-follower creator who fails the ICP gate should not top the list, and does not.

## What you may and may not compare

**May:** `priority` between any two rows in the same run. `fit_score` between any two rows. Engagement `score` between two rows on the *same* platform.

**May not:** `score` between platforms. `score` between a presence row and an engagement row — this is the [score mixing](failure-modes.md#score-mixing) failure. Audience counts across platforms without naming the unit, since `audience_kind` distinguishes followers, subscribers, and employees.

Note that `audience` for a company is a headcount, not a following. A 5,000-employee company and a 5,000-follower creator share a number and nothing else; `audience_kind` is what disambiguates them and belongs in any sentence quoting the figure.

## previous_score

The value from the last snapshot of that identity. A jump means more matching content appeared for your queries — not that the person grew. Only in `creators`, where the score is engagement, does a rise plausibly mean growing reach.
