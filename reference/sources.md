# Sources

Every external call this tool makes, what it costs, and what it returns.

- [Auth and billing](#auth-and-billing)
- [YouTube](#youtube)
- [TikTok](#tiktok)
- [Instagram](#instagram-opt-in)
- [Google-backed sources](#google-backed-sources)
- [Freshness](#freshness)
- [Drift detection](#drift-detection)
- [What is never called](#what-is-never-called)

## Auth and billing

Base `https://api.scrapecreators.com`, header `x-api-key`, read from `SCRAPECREATORS_API_KEY`.

One credit per HTTP call. `doctor` reads `/v1/credit-balance` for free and reports the balance so you can tell the user what is left.

The key is never written to disk, never logged, and never appears in any envelope. `doctor` reports only whether it is present and whether the vendor accepted it.

**Never fan out every source.** Each scenario's default set is already the right answer; `--sources` is a targeted override. See [scenarios.md](scenarios.md).

## YouTube

```
GET /v1/youtube/search?query=…&includeExtras=true&uploadDate=this_month|this_year
```

Returns videos with channel handles and, when extras land, view/like/comment counts. Channel and playlist rows are skipped — only videos resolve to a creator identity.

Default source for `creators`; supporting source for `people`, `companies`, `press`, and `compare`.

Profile enrichment uses the channel endpoint and is cacheable, so re-enriching a channel within the cache window is free.

## TikTok

```
GET /v1/tiktok/search/keyword
```

Handle is the author's `unique_id`. Returns play, digg, comment, and share counts, which map onto the engagement formula in [scoring.md](scoring.md).

Duplicates collapse onto `person/tiktok/{handle}`, so a creator with six matching videos is one row with a hit count of six.

## Instagram (opt-in)

```
GET /v2/instagram/reels/search
```

Searches Google-indexed reels rather than Instagram directly, so coverage is thinner than YouTube or TikTok. Spaces in the query can return 500; the engine retries with the query collapsed.

Never a default. Add it only when the user names Instagram, or when a visual-first topic came back thin.

## Google-backed sources

`linkedin_people`, `linkedin_companies`, `linkedin_jobs`, `x`, `web`, and `reddit` all route through:

```
GET /v1/google/search?query=…&date_posted=last-month|last-year
```

The planner has already embedded the `site:` operators in the query. **Do not wrap them again** — a doubly-scoped query returns nothing and looks like an empty market.

**These hits carry zero engagement data.** There are no views on a Google result. Rows from these sources are presence-scored, and any engagement figure attached to one would be invented. This is the single most important property of the LinkedIn path and the source of the [score mixing](failure-modes.md#score-mixing) failure.

LinkedIn here means **Google-indexed public URLs**. Not Sales Navigator, not a member cookie, not a logged-in session.

## Freshness

`--freshness month|year|all` maps per source: `uploadDate` on YouTube, `date_posted` on Google, dropped entirely for `all`.

| value | use for |
|---|---|
| `month` (default) | who is active right now |
| `year` | niche spaces where a month is too thin — common for `people`, `companies`, `press` |
| `all` | evergreen questions: established voices, the full landscape |

Freshness constrains discovery only. An enriched dossier always reflects the profile as it is today, regardless of when the matching post was published.

## Drift detection

Every response is probed before parsing. The engine counts records in the container it expects, and if that container is missing it scans shallowly for the largest list of objects elsewhere in the payload.

That produces four states per query angle, reported in `results.source_status`:

| state | meaning |
|---|---|
| `ok` | rows returned and parsed |
| `no-results` | expected container present and empty — a real absence |
| `unparsed` | the source answered with records we could not read, or the container vanished |
| `error` | the call never completed |

`unparsed` exists because the failure it catches is otherwise invisible. When a vendor renames a response key, a naive parser returns zero rows and the report reads as "nobody matches" — a false negative the user acts on. The probe distinguishes "we looked and found nothing" from "we could not read the answer", and `GAPS` names which sources drifted and where the records moved.

Details of how this surfaces in the report: [insights.md](insights.md).

## What is never called

No logged-in endpoints. No LinkedIn session, no Sales Navigator, no cookie jar. No email-discovery or contact-enrichment vendors. No write endpoints anywhere — this tool has no way to send, post, connect, or modify anything.
