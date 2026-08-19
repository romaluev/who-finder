# Failure modes

Named so you can catch the shape in your own draft before the user does. Each entry gives the symptom, why it happens, and the correction.

- [Output failures](#output-failures) — the run was fine, the answer was not
- [Evidence failures](#evidence-failures) — claiming more than the data supports
- [Planning failures](#planning-failures) — the wrong search
- [Cost failures](#cost-failures)
- [Setup failures](#setup-failures)
- [Quick diagnosis](#quick-diagnosis)

## Output failures

### impersonation
**Symptom:** a list of plausible names, no `who_finder.py` call in the transcript.
**Why:** the request reads like general knowledge, and you have plenty of it.
**Why it is bad:** no roster de-dup (the user may already have contacted half of them), no attributed fit, no source, no way to verify. It looks identical to a real answer.
**Fix:** run `find`. Every name in your output must be in `results.entities`.

### redesign
**Symptom:** you converted `table` into your own markdown, or re-sorted the cards.
**Why:** the engine's format looks improvable.
**Why it is bad:** the rewrite loses `fit_reasons` (the arithmetic that justifies each rank) and usually loses `GAPS` entirely. The user then trusts a ranking with no visible basis.
**Fix:** paste `table` verbatim, add at most three sentences after it.

### gap deletion
**Symptom:** the `GAPS` block is missing from what you pasted.
**Why:** it makes the answer look weaker.
**Why it is bad:** `GAPS` is where "we could not look" lives. Removing it converts a partial result into an apparently complete one.
**Fix:** `GAPS` is not optional. If it is embarrassing, that is information the user needs.

### silent re-rank
**Symptom:** your prose ordering differs from the card ordering.
**Why:** one name looks more interesting to you.
**Fix:** `priority` is 60% ICP fit, 25% reach, plus a novelty bonus. If that weighting is wrong for this user, fix `icp.json` — do not fix it in prose.

### mask leak
**Symptom:** `*******` appears in your output.
**Why:** LinkedIn returns asterisk-masked strings for non-public experience fields.
**Fix:** the engine detects this and substitutes the search snippet, tagging the row `masked-profile`. If a mask still reaches your draft, delete the line. Never present it as a redaction.

## Evidence failures

### phantom absence
**Symptom:** "nobody is doing this", "the space looks quiet", off a run whose sources were `unparsed` or `error`.
**Why:** zero rows looks like zero people.
**Why it is bad:** the user acts on absence — they conclude a market is empty and stop looking.
**Fix:** only `no-results` supports an absence claim. `unparsed` means the parser broke; `error` means we never looked. See [insights.md](insights.md).

### invented role
**Symptom:** a job title that is not in the data, inferred from the company or the URL slug.
**Why:** a row with a blank role looks incomplete.
**Fix:** "role not public" is a real answer. A fabricated title is indistinguishable from a real one to the reader, which is what makes it costly.

### invented email
**Symptom:** `jane@acme.com` in a report when the profile never published that address.
**Why:** a shortlist without an inbox looks unfinished, and first.last@domain is easy to type.
**Why it is bad:** it looks like a finding, it bounces, and the reader cannot tell which addresses were real.
**Fix:** print only what `contacts` harvested. A missing inbox is a missing inbox. Guessed work emails are contact-goat, and only after the user agrees to spend.

### band inflation
**Symptom:** an unenriched row described as a strong lead.
**Why:** the search snippet reads well.
**Fix:** unenriched rows are capped at `MAYBE` because we never fetched the profile. Run `enrich <id>` to earn the upgrade.

### confident unknown
**Symptom:** treating `?` and `off` as the same thing.
**Fix:** `off` means we looked and they are disqualified. `?` means the profile fetch failed. Opposite meanings for the user's next move.

### score mixing
**Symptom:** "this LinkedIn profile outperforms that YouTube channel."
**Why:** both rows have a `score` column.
**Fix:** LinkedIn rows come from a Google index and have no engagement data at all; their score is presence (`10 × hit_count`). YouTube scores are real views and likes. `priority` compares across platforms; raw `score` does not. See [scoring.md](scoring.md).

### known as new
**Symptom:** the headline features names already marked `outreached`.
**Fix:** lead with `results.n_new`. Import the user's existing skip/customer list before the first `find` so "new" is true.

## Planning failures

### keyword trap
**Symptom:** the whole sentence used as one query, or a brief with no topic run anyway.
**Fix:** `find` extracts the topic and builds angles. If the brief has no subject at all ("find me some good people"), ask one short question first.

### platform soup
**Symptom:** four sources on a vague brief.
**Why:** the sources exist.
**Fix:** each scenario has a default set that is already the right answer. `--sources` is an override for a specific reason, not a buffet. Instagram is opt-in only.

### people-at-companies
**Symptom:** "find people at AI video companies" run as a company search.
**Fix:** person-words beat company-words. That brief is `people`. The engine gets this right; the error appears when you pass `--scenario companies` yourself.

### compare-as-blog
**Symptom:** an invented verdict with section headers on an `A vs B` run.
**Fix:** paste the table with its `side` column. If they want a narrative, three bullets: only on A, only on B, on both.

### scenario override reflex
**Symptom:** passing `--scenario` on every call.
**Why it is bad:** it pre-empts a detector that is usually right, and it is how the previous two failures happen.
**Fix:** pass it only when detection is visibly wrong or the user named the type.

## Cost failures

### silent overspend
**Symptom:** `--deep 40` on a vague brief with no warning.
**Fix:** preview with `--dry-run` (free, no key needed) and state the ceiling. Use `--max-credits` when the user is cost-sensitive.

### re-find to refresh
**Symptom:** running the same `find` twice to "get more".
**Why it is bad:** identical queries return the same rows for full price.
**Fix:** `report` re-renders from the roster for zero credits. `expand` finds adjacent names from a dossier you already bought, also free. To genuinely widen, change `--freshness` or `--sources`.

### enrich-everything
**Symptom:** `--deep 40` when the user wanted names.
**Fix:** depth is for qualification, not coverage. Ten enriched rows beat forty shallow ones for outreach, and cost less than forty enrichments.

## Setup failures

### missing key
**Symptom:** `doctor` returns `ready-thin`, exit 0.
**Fix:** proceed with a caveat — public search only, no profile pages. Offer `setup YOUR_KEY` for the full path. Inventing names is worse than a thinner shortlist. Do not substitute WebSearch.

### cookie LinkedIn
**Symptom:** a suggestion to log in and scrape, or to use Sales Navigator.
**Fix:** refuse. LinkedIn here is Google-indexed public URLs plus vendor profile endpoints. That is a deliberate boundary, not a limitation to route around.

### broken icp.json
**Symptom:** exit 10.
**Fix:** `error.message` names the line. The run stops rather than falling back, because scoring against the wrong rules and reporting it as a result is worse than refusing.

### wrong folder
**Symptom:** the engine is not where you looked.
**Fix:** `scripts/who_finder.py` is a sibling of `SKILL.md`. Use the directory your harness read `SKILL.md` from; do not write a path-discovery loop.

## Quick diagnosis

| you see | it means | go to |
|---|---|---|
| exit 4 | no key or a rejected key | [missing key](#missing-key) |
| exit 8 | plan over budget | [cost failures](#cost-failures) |
| exit 10 | malformed ICP | [broken icp.json](#broken-icpjson) |
| `UNPARSED` in coverage | parser bug, not an absence | [phantom absence](#phantom-absence) |
| `n_new: 0` | the seen-list is working | say so and stop |
| every band is `?` | enrichment failed wholesale | check `results.errors`; likely auth or vendor |
| every row is `off` | the ICP gate rejects the topic | `icp show`; the `must_any` terms probably do not match this brief |
| zero entities but sources `ok` | rows returned, identities unparseable | [identity.md](identity.md) |
