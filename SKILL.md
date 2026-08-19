---
name: who-finder
description: Deep public research on people or companies by scenario (operators, firms, creators, hiring, press, A vs B). Plans the queries, fetches profiles, scores ICP fit with reasons, ranks by priority, and keeps a seen-list so outreach only gets new names. Use when asked to find people, find companies, find creators, research a market, who is hiring, journalists covering a topic, compare two scenes, LinkedIn public profiles, YouTube talent, build a shortlist, qualify leads, or export a handoff CSV. Not for sending messages, not for logged-in LinkedIn scraping, not for CRM.
license: Apache-2.0
metadata:
  version: "3.0.0"
---

# who-finder

You are inside this skill. The **engine** is `scripts/who_finder.py`. It detects the scenario, plans queries, calls ScrapeCreators, fetches profiles, scores ICP fit, ranks, de-dupes, and writes the roster. You do not WebSearch for names. You do not write HTTP. You do not invent a report format. You do not judge fit in prose — the engine attributes every point to a named reason.

Creator-finding is one scenario. The product is **who** — people and companies.

## Resolve SKILL_DIR

`SKILL_DIR` = directory of **this** SKILL.md. `scripts/who_finder.py` is a sibling of SKILL.md.

```bash
SKILL_DIR="<absolute path of the SKILL.md directory you Read>"
BIN="python3 $SKILL_DIR/scripts/who_finder.py"
test -f "$SKILL_DIR/scripts/who_finder.py"
```

If that test fails, stop. Wrong folder.

## Contract (every request)

1. `doctor --agent` first if this session has not already proven the key.
2. Primary verb is **`find`**. A sentence brief goes to `find`. `search` is one raw keyword (debug only).
3. **Default to `--deep 10`.** Bare `find` returns names; `--deep` returns who they are, how big their audience is, what they posted, and why they fit. Skip `--deep` only when they explicitly want a cheap/fast name sweep.
4. Do not pass `--scenario` unless they named one. The engine detects people / companies / creators / hiring / press / compare.
5. Always `--agent`. Parse JSON. The field **`table` is the user-facing answer** — paste it verbatim. Add at most three bullets of your own. Do not redesign it, do not re-rank it, do not re-summarise the cards.
6. Lead with `results.n_new`. Known rows are memory, not the headline.
7. After they contact / skip / already know someone: `mark`. When they want a sheet: `export`.

```bash
$BIN doctor --agent
$BIN which "who should we pitch in AI video" --agent
$BIN find "founders of AI video tools" --deep 10 --agent
$BIN find "AI video ads" --scenario creators --deep 10 --agent
$BIN report --status new --agent          # re-render the brief, 0 credits
$BIN enrich person/linkedin/someslug --agent
$BIN expand company/linkedin/someco --agent
$BIN show person/youtube/somehandle --agent
$BIN mark person/youtube/somehandle --status outreached --agent
$BIN export --status new --band strong --out who-handoff.csv --agent
```

Doctor exit 4 = missing `SCRAPECREATORS_API_KEY` (theirs). Stop. Do not invent names.
Doctor `--probe` spends one credit on YouTube — only if they asked "is it working".

## Cost, so you can choose depth honestly

| call | credits |
|---|---|
| each query angle in a plan | 1 |
| each enriched entity (`--deep N`) | 1, or 0 on a YouTube/TikTok cache hit |
| `report`, `expand` from a stored dossier, `show`, `export`, `mark` | 0 |

`find "brief" --deep 10` on a five-angle scenario costs about 15 credits. Say the number if they ask; do not guess it silently.

## Scenarios (engine-owned)

| brief sounds like | scenario | default sources | score |
|---|---|---|---|
| people / founders / operators | `people` | LinkedIn `/in` + YouTube + X | presence |
| companies / vendors / studios | `companies` | LinkedIn company + web | presence |
| creators / influencers / who posts | `creators` | YouTube + TikTok | engagement |
| hiring / jobs / open roles | `hiring` | LinkedIn jobs + ATS sites | presence |
| journalists / press / bylines | `press` | web + YouTube interviews | presence |
| `A vs B` / compare | `compare` | both LinkedIn + YouTube | presence, two sides |

Do not mix YouTube engagement scores with LinkedIn presence scores. Do not add Instagram unless they named it.

## Reading the deep brief

- `WHAT I FOUND` — engine-written, count-backed. Do not embellish it.
- `WHO TO CONTACT` — ranked cards. `does` is their role, `why` is the fit arithmetic, `now` is a real recent post, `tags` are signals.
- Bands: `STRONG` (verified profile + topic + title/audience match), `MAYBE`, `weak`, `off`, `?` (unknown — we could not fetch the profile).
- `GAPS` — sources that errored versus sources that ran and returned nothing. **These are different claims.** Never report a source that errored as "nothing out there".
- A row we could not enrich is capped at `MAYBE`, never `STRONG`. If they push for a verdict on one, run `enrich <id>` rather than upgrading it yourself.

## ICP fit

Fit is a local JSON file the user owns, not your judgement.

```bash
$BIN icp show --agent     # current rules (built-in generic if no file)
$BIN icp init             # write an editable template to .who-finder/icp.json
$BIN signals --agent      # signal names you can score
```

With no file, the engine derives a topic gate from the brief and uses generic seniority rules. If they say "these results are not our kind of customer", the fix is editing `icp.json` — offer that, do not silently re-rank.

## Do not

- Do not log into LinkedIn or pass cookies. LinkedIn here is Google-indexed public URLs plus vendor profile endpoints.
- Do not send email/DMs. Export is the end of the line.
- Do not print a role you did not receive. LinkedIn masks job history on public profiles; the engine falls back to the search snippet and tags the row `masked-profile`.
- Do not fan out every source because they exist.
- Do not skip `find` and improvise queries in chat. If the planner is wrong, pass `--sources` or `--scenario`.
- Do not treat "people at X companies" as a company search. Person-words win.
- Do not re-enrich rows already in the roster to "refresh" them unless asked. That spends credits for nothing.

## Named failure modes

- **keyword trap** — used the whole sentence as one Google query instead of `find`.
- **shallow answer** — returned bare handles when `--deep` was the point of the ask.
- **platform soup** — four sources on a vague brief.
- **score mixing** — ranked a LinkedIn profile against a YouTube creator.
- **known as new** — showed already-outreached names as the headline.
- **LinkedIn-without-engagement** — treated Google-indexed LI rows as if they had views.
- **mask leak** — printed `*******` from a masked LinkedIn experience block.
- **confident unknown** — presented an unenriched row as a qualified lead.
- **silent error** — reported a failed source as an empty result.

## Load when the engine is not enough

- Scenario detect + angles: [reference/scenarios.md](reference/scenarios.md)
- People: [reference/people.md](reference/people.md)
- Companies: [reference/companies.md](reference/companies.md)
- Creators: [reference/creators.md](reference/creators.md)
- Hiring: [reference/hiring.md](reference/hiring.md)
- Press: [reference/press.md](reference/press.md)
- Compare: [reference/compare.md](reference/compare.md)
- Enrichment + dossier fields: [reference/enrichment.md](reference/enrichment.md)
- ICP config + fit math: [reference/icp.md](reference/icp.md)
- Insights + coverage rules: [reference/insights.md](reference/insights.md)
- Endpoints + credits: [reference/sources.md](reference/sources.md)
- Identity parse: [reference/identity.md](reference/identity.md)
- Score meaning: [reference/scoring.md](reference/scoring.md)
- Roster / new vs known: [reference/roster.md](reference/roster.md)
- CSV columns: [reference/handoff.md](reference/handoff.md)
- Failure catalogue: [reference/failure-modes.md](reference/failure-modes.md)
