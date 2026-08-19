# Identity

Every row is keyed `kind/platform/handle`. Stable identity is what makes de-duplication, status tracking, and "new versus known" possible at all.

- [The shape](#the-shape)
- [Per-platform parsing](#per-platform-parsing)
- [Kind follows the scenario](#kind-follows-the-scenario)
- [Why the same human is two rows](#why-the-same-human-is-two-rows)
- [Accepted input forms](#accepted-input-forms)
- [When parsing fails](#when-parsing-fails)

## The shape

```
person/linkedin/jane-doe
company/linkedin/acme-video
person/youtube/adlab
company/web/runwayml.com
```

`kind` is `person` or `company`. `platform` is the source system. `handle` is that platform's stable identifier — a slug, an `@handle`, or a hostname.

## Per-platform parsing

| URL pattern | identity |
|---|---|
| `linkedin.com/in/{slug}` | `person/linkedin/{slug}` |
| `linkedin.com/company/{slug}` | `company/linkedin/{slug}` |
| `linkedin.com/jobs/...` with title `Role \| Company \| LinkedIn` | `company/linkedin/{company-slug}` |
| `youtube.com/@{handle}` or `/channel/{id}` | `{kind}/youtube/{handle}` |
| `tiktok.com/@{handle}` | `person/tiktok/{handle}` |
| `x.com/{handle}` or `twitter.com/{handle}` | `person/x/{handle}` |
| anything else | `person/web/{name-slug}` or `company/web/{hostname}` |

The job-posting rule is the one worth understanding: **the identity of a job posting is the company that posted it**, extracted from the page title. Ten open roles at one studio collapse to one row rather than flooding the report with the same employer.

## Kind follows the scenario

A YouTube channel is `person/youtube/x` in a `creators` run and `company/youtube/x` in a `companies` run. The same channel can legitimately be either — a studio channel is a company, a practitioner's channel is a person — and the scenario is the best available evidence for which one the user meant.

## Why the same human is two rows

Jane Doe on LinkedIn and Jane Doe on YouTube are `person/linkedin/jane-doe` and `person/youtube/janedoe`. The engine does not merge them.

Cross-platform identity resolution requires either a confident name match (unreliable — common names collide constantly) or a profile link (usually absent). A wrong merge is worse than no merge: it fuses two people's audiences and roles into a single fabricated profile, and nothing downstream can detect it.

So the table shows both, and joining them is a CRM job with a human in the loop. Do not merge them in your prose either.

## Accepted input forms

`show`, `mark`, `enrich`, and `expand` accept:

- the full `kind/platform/handle`
- `platform/handle`, where kind defaults to `person`

```bash
$BIN show person/youtube/adlab
$BIN show youtube/adlab            # same row
```

## When parsing fails

A hit whose URL matches no pattern and whose title yields no usable slug is dropped from the entity list but kept as a hit. This is why a run can report sources as `ok` and still return zero entities — rows came back, but none of them resolved to something addressable.

If that happens repeatedly on one source, the cause is usually a changed result shape upstream. Check `results.source_status` for `unparsed` and see [insights.md](insights.md).

The parser lives in `scripts/lib/identity.py`. Do not regex URLs in chat — a second parser that disagrees with the roster's keys silently breaks de-duplication.
