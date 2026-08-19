# Enrichment — how a name becomes a dossier

Discovery gives you a URL and a snippet. Enrichment spends **1 credit per entity** to answer what they do, how big their audience is, and what they are saying right now.

Triggered by `find --deep N`, `enrich`, or implicitly by `expand` when no dossier is stored.

## Endpoints used

| identity | endpoint | credits | gives |
|---|---|---|---|
| `person/linkedin/*` | `/v1/linkedin/profile?url=` | 1 | name, location, followers, about, website/socials when present, recent posts, similar profiles |
| `company/linkedin/*` | `/v1/linkedin/company?url=` | 1 | industry, size, employees, founded, HQ, specialties, funding, investors, staff with titles, posts, similar pages |
| `*/youtube/*` | `/v1/youtube/channel?handle=` | 1, or 0 cached | subscribers, video count, total views, description, country, external links |
| `*/tiktok/*` | `/v1/tiktok/profile?handle=` | 1, or 0 cached | followers, likes, video count, bio, verified, bio link |
| `*/instagram/*` | `/v1/instagram/profile?handle=` | 1 | followers, biography, verified, external URL |
| `*/x/*` | `/v1/twitter/profile?handle=` | 1 | followers, post count, bio, location, verified |
| `*/web/*`, `*/reddit/*` | — | 0 | not enrichable; stays discovery-only |

YouTube and TikTok accept `cache_max_age` (`--cache`, default `7d`). A cache hit costs **0 credits** and sets `cached: true`. Repeated research on the same roster is close to free.

## The two constraints that shape this module

**LinkedIn masks job history.** Public profiles return asterisk strings like `"******* ** * ******"` for `experience[].member.description` and often the org name. `util.is_masked()` catches any string that is >25% asterisks, `clean()` drops it, and the row is tagged `masked-profile`. **Nothing masked ever reaches the report.**

**The Google snippet is better than the profile for job titles.** Google indexes a LinkedIn person as `Name - Headline - LinkedIn`, so the snippet still carries the title LinkedIn no longer serves via the profile. The dossier keeps both: `snippet` is stored alongside the fetched profile and both feed ICP matching. For `person/linkedin/*`, a snippet-derived headline wins over an about-derived one.

That merge is the whole reason this tool combines sources rather than picking one.

## Dossier fields

| field | meaning |
|---|---|
| `headline` | one line: what they do |
| `headline_source` | `search-snippet`, `linkedin-experience`, `linkedin-about`, `linkedin-company`, `youtube-about`, `tiktok-bio`, `x-bio` — always shown in the card so the reader can discount it |
| `snippet` | the raw discovery text, retained for scoring |
| `bio` | about / description / signature |
| `audience` + `audience_kind` | followers, subscribers, or employees — one comparable number |
| `audience_detail` | the platform-specific breakdown |
| `recent` | recent post titles with links — what they are talking about now |
| `topics` | keywords extracted from bio + headline + snippet + posts |
| `links` | cross-platform links found on the profile (a free identity graph) |
| `contacts` | harvested public emails, labelled links, whether they book meetings — never guessed |
| `similar` | LinkedIn `similarProfiles` / `similarPages` — feeds `expand` |
| `people` | LinkedIn company `employees[]`, **with real job titles** |
| `signals` | derived tags (`who-finder signals`) |
| `company` | industry, size, founded, funding rounds, last round, investors |
| `enriched` | false if we never fetched or the fetch failed |
| `error` | why, if so |

## Failure is data

`enrich()` never raises. A failed fetch returns a dossier with `enriched: false`, an `error`, and a snippet-derived headline. Those rows still appear in the brief, are capped at band `MAYBE`, and are counted in `WHAT I FOUND` as discovery-only. Dropping them silently would be worse than showing them honestly.

## Free lateral expansion

`similar` and `people` come back inside the profile payload you already paid for. `expand <id>` turns them into new roster candidates for **0 credits**:

- `company/linkedin/acme` → its staff, with titles, as `person/linkedin/*` rows
- `person/linkedin/jane` → LinkedIn's own "similar profiles" suggestions

For company research this is usually the cheapest path to real named humans, because employee titles are public even when individual profiles are masked.
