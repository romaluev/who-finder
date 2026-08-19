# Creators

People whose **published content** matches the topic, ranked by how much engagement it earns. This is the only scenario with real engagement data.

**Kind:** `person` · **Sources:** `youtube`, `tiktok` · **Score:** engagement

- [Angles](#angles)
- [When to use it](#when-to-use-it)
- [How ranking works here](#how-ranking-works-here)
- [Compilation damping](#compilation-damping)
- [Instagram is opt-in](#instagram-is-opt-in)
- [Pitfalls](#pitfalls)

## Angles

| # | source | query | why |
|---|---|---|---|
| 1 | youtube | `{topic}` | the main sweep |
| 2 | youtube | `{topic} tutorial` | practitioners teaching it, which correlates with expertise |
| 3 | tiktok | `{topic}` | shorter-form, different population |

Hits roll up per `person/{platform}/{handle}`, so a channel with four matching videos becomes one row with the summed score and a hit count.

## When to use it

They said creator, influencer, UGC, YouTuber, TikToker, "who posts about", "who makes content on", "who should we send product to".

If they want operators who barely publish, that is [people](people.md). The test: does the user care about audience, or about the person's job? Audience means creators.

## How ranking works here

```
score = views + 10*likes + 20*comments + 5*shares
```

Weighted by effort — a comment signals more than a like, which signals more than a passive view. A 20k-subscriber channel with an engaged audience can and should outrank a 500k channel whose viewers scroll past.

This is the one scenario where a rising `previous_score` plausibly means growing reach rather than just more matching uploads.

## Compilation damping

Titles shaped like `best of`, `top N`, `lofi`, `N hours`, `playlist`, `mix` get flagged `compilation` and divided by 5.

Without this, a single "10 HOURS of AI-generated music" upload buries every actual practitioner, because aggregation videos accumulate views without indicating that the uploader works on anything. The flag stays on the row so the damping is visible rather than mysterious.

If a legitimately relevant channel got damped, you will see the `compilation` tag on it and can say so.

## Instagram is opt-in

```bash
$BIN find "..." --scenario creators --sources youtube,tiktok,instagram
```

Never a default. The endpoint searches Google-indexed reels rather than Instagram itself, so coverage is patchier than the other two and the extra credits often buy little. Add it when the user names Instagram or when the topic is visual-first and the first run came back thin.

## Pitfalls

- **Do not** add LinkedIn here. Those rows have no engagement, so they land at the bottom of an engagement ranking and make the list look broken.
- **Do not** compare a TikTok score to a YouTube score in prose. Platform norms differ by an order of magnitude; the table is per-row for that reason. `priority` is the cross-platform number.
- **Do not** leave freshness at `month` for an evergreen ask — use `year` or `all` when they want established voices rather than current activity.
- **Do** state audience size with its unit. `audience_kind` distinguishes subscribers from followers.
