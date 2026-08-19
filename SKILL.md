---
name: who-finder
description: Deep public research on people or companies by scenario (operators, firms, creators, hiring, press, A vs B). Plans the queries, fetches public profiles, scores ICP fit with attributed reasons, ranks by priority, and keeps a seen-list so outreach only gets new names. Use when asked to find people, find companies, find creators, research a market, build a shortlist, qualify leads, see who is hiring, find journalists covering a topic, compare two scenes, search LinkedIn public profiles, find YouTube or TikTok talent, or export a prospect handoff CSV. Also use for "who should we pitch", "who is doing X", "give me names", "find me operators at", "who covers this beat". Not for sending email or DMs, not for logged-in LinkedIn or Sales Navigator scraping, not for CRM writes, and not for researching a topic with no people in it — that is last30days.
license: Apache-2.0
metadata:
  version: "3.4.0"
---

# SKILL CONTRACT — READ BEFORE ANY TOOL CALL

You are inside the `who-finder` skill. This is a specific research engine with a defined output contract, not a prompt that means "go find some people."

**The engine is `scripts/who_finder.py`.** It detects the scenario, plans the query angles, calls ScrapeCreators, fetches public profiles, scores ICP fit with attributed arithmetic, ranks by priority, de-dupes against a local roster, and renders the report. Every one of those steps lives in Python **specifically so you cannot improvise it**.

What you do: parse intent into one `find` call, run it, paste the `table`, add at most three sentences of your own.

What you never do: search for names yourself, write HTTP, invent a ranking, judge fit in prose, or design a report format.

**The single most common failure of a skill like this** is the model reading the file, skimming the headers, and then answering the user with a few web searches and a confident list of names it half-remembers. That output is worthless here — it has no roster de-duplication, no attributed fit, no credit accounting, and no way to tell a real absence from a broken parser. If you are about to write a list of names you did not get from `results.entities`, stop.

---

# OUTPUT CONTRACT — THE THIRTEEN LAWS

These dominate every other instruction in this file. If you are about to violate one, stop and regenerate.

**LAW 1 — RUN THE ENGINE. ALWAYS.** Every answer this skill produces comes from at least one `who_finder.py` invocation. Not from your training data, not from WebSearch, not from a URL the user pasted. If your response contains a person or company you cannot point to in `results.entities`, you did not run the skill — you impersonated it.

**LAW 2 — `table` IS THE ANSWER. PASTE IT VERBATIM.** The engine renders the report because a model handed twenty rows will rewrite them into a confident narrative the rows do not support. Do not re-rank it, do not re-summarise the cards, do not convert it to your own markdown table, do not drop the `GAPS` section because it looks negative. Paste `table`, then add **at most three sentences**. The `GAPS` section is the most important part of the output and is the part models most often delete.

**LAW 3 — NEVER INVENT A NAME, HANDLE, ROLE, OR NUMBER.** Every name, `@handle`, job title, follower count, and URL in your response must appear in the JSON you got back. If a row has no role, it has no role — say "role not public", never guess from the company name. Fabricating one plausible title poisons a list the user is about to act on, and they cannot tell which one you made up.

**LAW 4 — ABSENCE IS A CLAIM AND MOST ZEROS DO NOT SUPPORT IT.** `results.source_status` gives each query angle one of four states, and they mean different things:

| state | what happened | may you say "nothing out there"? |
|---|---|---|
| `ok` | returned rows | n/a |
| `no-results` | container present and empty | **yes** — this is a real absence |
| `unparsed` | answered in a shape we could not read | **no** — parser bug |
| `error` | never completed | **no** — we did not look |

Writing "there is nobody doing this" off an `unparsed` or `error` state is the most damaging thing this skill can do, because the user acts on the absence. When you see `SCHEMA DRIFT` in `GAPS`, say plainly that the tool could not read those sources and the result is partial.

**LAW 5 — LEAD WITH `results.n_new`.** Known rows are memory, not news. Open with how many new names came back. If `n_new` is 0, say that first — "nothing new since last run" is a complete and useful answer, and burying it under a re-listing of known names wastes the user's read.

**LAW 6 — NEVER UPGRADE A BAND.** Bands come from `fit_band`. A row that was not enriched is capped at `MAYBE` no matter how good the snippet reads, because we never saw the profile. If the user pushes for a verdict on one name, run `enrich <id>` and let the engine re-score — do not promote it in prose.

**LAW 7 — SPEND DELIBERATELY AND SAY THE NUMBER.** Every query angle is one credit; every enriched profile is one more. Before any run you expect to exceed ~20 credits, or any run where the user has signalled cost sensitivity, preview it with `--dry-run` and state the ceiling. After every run, `meta.credits_spent` is a fact you may be asked for. Never run the same `find` twice to "get more" — use `report` (0 credits) or `expand` (0 credits).

**LAW 8 — DO NOT MIX SCORES ACROSS PLATFORMS.** LinkedIn rows come from a Google index and have **no engagement data**. YouTube and TikTok rows have real view and like counts. `priority` is comparable across them because it is ICP-driven; raw `score` is not. Never write "this LinkedIn profile is more engaged than that YouTube channel."

**LAW 9 — NEVER PRINT A MASK.** LinkedIn hides job history on public profiles and returns asterisk strings like `*******`. The engine detects this, falls back to the search snippet, and tags the row `masked-profile`. If you ever see a run of asterisks in your drafted output, delete it — do not present it as a redacted title.

**LAW 10 — EXPORT IS THE END OF THE LINE.** This skill finds and qualifies. It does not send email, does not DM, does not write to a CRM, and does not log into LinkedIn. When the user asks to reach out, produce the CSV or run `contacts` and stop.

**LAW 11 — THE ENGINE WRITES THE DOCUMENT.** When the user wants a report, pass `--format md,pdf --out PATH` and hand back the paths. Do not assemble a document out of the JSON yourself: your version will drop the attributed arithmetic, the corroboration counts, and the coverage caveats, and it will look authoritative while doing it. A hand-written summary of a research report is the same failure as LAW 1, one step later.

**LAW 12 — "MORE" IS NOT ANOTHER `find`.** Discovery already returned more names than `--deep` paid to enrich. `more --offset N` continues down that stored ranking and `report --offset N` re-cuts it for free. Re-running `find` re-buys every search to surface mostly the same people. If the user asks for more names and you run `find` again, you have spent their credits on a duplicate.

**LAW 13 — COMPOSE, DON'T IMPERSONATE, DON'T INVENT AN EMAIL.** Public emails, Calendly links, and personal sites come from the engine — they appeared on a profile. A work email you pattern-guess (`jane@acme.com`) is a bounce waiting to happen. If `contact-goat-pp-cli` is on PATH and the user asked for a work email or a warm intro, run *that* binary, and only after they agree to spend. If it is not installed, say so. Never invent an address to look helpful.

---

# STEP 0 — PRECONDITION GATE

Run this before anything else. It costs nothing and prevents the two setup failures.

```bash
SKILL_DIR="<absolute path of the directory holding the SKILL.md you just read>"
BIN="python3 $SKILL_DIR/scripts/who_finder.py"
test -f "$SKILL_DIR/scripts/who_finder.py" || echo "WRONG_DIR"
$BIN doctor --agent
```

`scripts/who_finder.py` is always a direct sibling of SKILL.md. Do not write a path-discovery loop; use the directory your harness told you it read SKILL.md from.

Branch on `results.state`:

| state | exit | do |
|---|---|---|
| `ready` | 0 | proceed |
| `skipped-unconfigured` | 4 | **stop.** Tell the user to `export SCRAPECREATORS_API_KEY=...` (their own key, from scrapecreators.com). Do not substitute WebSearch. Do not produce names. |
| `auth-failed` | 5 | **stop.** Their key is rejected — expired or wrong. |
| `error` | 5 | report the message; do not retry more than once |

Skip `doctor` only if a previous call in *this* session already returned `ready`.

`doctor --probe` spends one credit on a real YouTube search. Run it only when the user asks "is it actually working" — it is the only command that proves the live path end to end.

---

# STEP 1 — PARSE INTENT INTO ONE `find`

Do not ask clarifying questions you can answer from the brief. The engine detects the scenario; your job is to pass the brief through cleanly.

| the user says | scenario | you pass |
|---|---|---|
| "founders of / operators at / people who" | `people` | nothing — auto-detects |
| "companies / vendors / studios / agencies building" | `companies` | nothing |
| "creators / influencers / who posts about / YouTubers" | `creators` | nothing |
| "who is hiring / open roles / job posts for" | `hiring` | nothing |
| "journalists / press / who covers / bylines" | `press` | nothing |
| "X vs Y" | `compare` | nothing |
| detection is visibly wrong | — | `--scenario <name>` |

**Pass `--scenario` only when the engine got it wrong or the user named the type explicitly.** Guessing pre-empts the detector and is how a "people at AI video companies" brief becomes a company search. Person-words beat company-words: that brief is `people`.

**Default to `--deep 10`.** Bare `find` returns handles. `--deep` returns who they are, how big their audience is, what they posted recently, and why they fit — which is the entire point of the ask. Drop `--deep` only when the user explicitly wants a cheap or fast name sweep.

**Always pass `--agent`** and parse the JSON envelope.

```bash
$BIN find "founders of AI video tools" --deep 10 --agent
```

## Supply the framings only you can supply

The engine reframes the topic structurally on its own: exactly as asked, as a quoted phrase, and with the leading qualifier dropped. Those rewrites work on any subject because they do not need to know what the words mean.

**What the engine cannot derive is the vocabulary of the field**, and that is the reframing that finds the people a literal search misses. Somebody building `text-to-video` tools may describe themselves as working on `generative video`, `synthetic media`, or `AI film production`, and none of those strings contain the words the user typed. You know that. The engine does not, and a built-in synonym list would be wrong for every domain but one.

**So pass `--frame` for any topic with real jargon behind it.** Two or three, each a phrase a practitioner would actually put in their own headline:

```bash
$BIN find "people building text-to-video tools" --deep 10 --agent \
  --frame "generative video" \
  --frame "AI film production"
```

Rules for a good frame. **A frame is a different vocabulary, not a different filter** — `--frame "founders of generative video"` is wasted, because role targeting is already an angle; `--frame "generative video"` is the useful half. **Never frame with a term you are not confident is real** in the field, since a frame that matches nothing costs a credit and returns noise. **Do not paraphrase the brief back into itself** — `--frame "people making AI videos"` on a brief about AI video adds nothing the literal frame did not already cover.

Each extra frame is exactly one more search, so three frames on a five-angle scenario costs seven credits rather than five. `--frames N` caps the total; `--frames 1` disables reframing.

## The keyword trap

A brief is not a search query. `find` extracts the topic and builds angles from it. What breaks the engine is a brief with no topic in it — "find me some good people", "who should we talk to". If the brief has no subject, ask **one** short question to get the subject, then run. Do not run the engine on an empty topic and do not pad it with your own assumptions.

---

# STEP 2 — SPEND CHECK

| call | credits |
|---|---|
| each query angle in a plan | 1 |
| each enriched entity under `--deep N` | 1, or 0 on a cache hit |
| `report`, `expand`, `show`, `list`, `export`, `mark`, `icp`, `agent-context` | 0 |
| `doctor` | 0 (1 with `--probe`) |

A five-angle scenario with `--deep 10` costs up to 15 credits. That is the normal price of a real answer — do not silently downgrade the run to save credits, and do not silently spend 60 either.

Preview before an expensive or ambiguous run:

```bash
$BIN find "AI video tooling" --deep 25 --dry-run --agent   # 0 credits, prints exact queries + ceiling
$BIN find "AI video tooling" --deep 25 --max-credits 20 --agent   # exits 8 rather than overspending
```

`--dry-run` needs no API key and touches no network, so it is also the right way to show someone what the tool *would* do.

---

# STEP 3 — RUN, THEN READ THE ENVELOPE

Every command returns the same shape:

```json
{
  "meta":    { "version": "...", "scenario": "...", "credits_spent": 12, "icp": "..." },
  "plan":    { "steps": [ { "source": "...", "query": "...", "label": "..." } ] },
  "table":   "the rendered report — this is what you paste",
  "results": { "n_new": 7, "n_known": 3, "source_status": [...], "insights": {...}, "entities": [...] }
}
```

Read in this order: `meta.credits_spent` → `results.n_new` → `results.source_status` → `table`.

When context is tight, project the fields you need instead of ingesting whole dossiers:

```bash
$BIN find "..." --deep 10 --agent --select results.n_new,results.entities.id,results.entities.priority,results.entities.fit_band
```

`meta` and `error` always survive `--select`, so a projection can never hide the credit count or a failure.

## Reading the brief

- **`WHAT I FOUND`** — engine-written and count-backed. Do not embellish it; every clause traces to a number.
- **`WHO TO CONTACT`** — ranked cards. `does` = their role, `why` = the fit arithmetic, `now` = a real recent post, `tags` = signals, `url` = the profile.
- **Bands** — `STRONG` (profile fetched, topic matched, title or audience qualified), `MAYBE`, `weak`, `off` (actively disqualified), `?` (unknown — profile fetch failed).
- **`GAPS`** — errored sources, drifted sources, genuinely empty sources. Three different claims. Paste it.

`off` and `?` are not the same and the difference matters to the user: `off` means we looked and they are wrong for you; `?` means we could not look.

---

# STEP 4 — SELF-CHECK BEFORE YOU EMIT

Scan your drafted response and fix any hit:

- [ ] Every name appears in `results.entities`. No exceptions.
- [ ] I pasted `table` rather than rewriting it, and the `GAPS` block is still in it.
- [ ] I did not claim absence for any source in `unparsed` or `error` state.
- [ ] I led with `n_new`, not with the total.
- [ ] No band is higher in my prose than in `fit_band`.
- [ ] No `*******` anywhere.
- [ ] No email I invented. Every address appears in `results` or in `contacts`.
- [ ] My additions are three sentences or fewer.
- [ ] If they asked what it cost, I used `meta.credits_spent` and not an estimate.
- [ ] If they asked for a file, I gave them the path the engine printed — I did not write the report myself.

---

# STEP 5 — WHEN THEY WANT A DOCUMENT

"Send me a report", "write this up", "top 10 with full detail", "something I can forward" — these all mean a file, and **the engine writes it**. Add `--format` to the same run:

```bash
$BIN find "BRIEF" --deep 10 --format md,pdf --out ~/Desktop/shortlist --agent
```

That produces `shortlist.md` and `shortlist.pdf` from one build: a cover, a summary of the landscape, a ranked table, a full page on each person, and a method section listing every query that ran. `--format` accepts `md`, `html`, `pdf`, `json`, comma-separated. **`html` is the best-looking of the four** and prints to a better PDF than the built-in writer, so offer it when the document is going to a client. The built-in `pdf` needs no browser and no install, which is why it exists.

**Do not compose the document yourself.** Reformatting the JSON into your own markdown loses the attributed arithmetic, the corroboration counts, and the coverage caveats — every part that makes the file worth more than a list of names. Report the paths back and quote at most a line or two.

## "Show me more"

The roster holds every name discovery returned, while `--deep N` only paid to enrich the top N. So "give me another ten" is **not** a reason to run `find` again:

```bash
$BIN more --offset 10 --limit 10 --format md --out more --agent
```

`more` walks further down the existing ranking and enriches only what has not been enriched, at one credit each and zero for discovery. To re-cut a slice you have already paid for, `report --limit 10 --offset 10` costs nothing at all. **Re-running `find` to get more names is the single most expensive mistake available in this tool** — it re-buys every search and returns mostly the same people, now marked `known`.

---

# COMMANDS

```bash
$BIN doctor --agent                       # 0  health + credit balance
$BIN agent-context --agent                # 0  machine-readable map of this whole CLI
$BIN which "who should we pitch" --agent  # 0  capability phrase -> command
$BIN find "BRIEF" --deep 10 --agent       # the primary verb
$BIN find "BRIEF" --dry-run --agent       # 0  exact queries + cost ceiling
$BIN find "BRIEF" --frame "other words"   # +1 per frame; add the field's vocabulary
$BIN find "BRIEF" --format md,pdf --out PATH --agent   # write the document
$BIN report --status new --agent          # 0  re-render the brief from the roster
$BIN report --limit 10 --offset 10 --format md --out PATH --agent   # 0  page a paid slice
$BIN more --offset 10 --limit 10 --agent  # 1/profile, 0 discovery — the next ten down
$BIN enrich person/linkedin/slug --agent  # 1  fetch + score one stored row
$BIN expand company/linkedin/co --agent   # 0  employees / similar profiles from a stored dossier
$BIN show person/youtube/handle --agent   # 0  one entity, full dossier
$BIN list --status new --agent            # 0
$BIN mark person/youtube/h --status outreached --agent
$BIN export --status new --band strong --out handoff.csv --agent
$BIN contacts --agent                     # 0  emails and links they published
$BIN icp show --agent                     # 0  the fit rules in force
$BIN signals --agent                      # 0  signal names you can score
$BIN feedback "what surprised you" --agent
```

Identities are always `kind/platform/handle` — `person/linkedin/jane-doe`, `company/linkedin/acme`, `person/youtube/adlab`.

**Global flags** work before or after the verb: `--agent`, `--select PATHS`, `--deliver stdout|file:<path>|webhook:<url>`, `--profile NAME`, `--db PATH`.

## Exit codes

| code | meaning | your move |
|---|---|---|
| 0 | success | proceed |
| 2 | usage error | read `error.fix`, correct the flag, retry once |
| 3 | not found | the id is not in the roster; `list` first |
| 4 | auth required | stop, ask for the key |
| 5 | upstream API error | retry once, then report |
| 8 | budget refused | raise `--max-credits` or lower `--deep`, with the user's consent |
| 9 | delivery failed | the `--deliver` sink is bad; fall back to stdout |
| 10 | config error | their `icp.json` is malformed; `error.message` names the line |

Non-zero always carries `error.code`, `error.message`, and `error.fix`. Read `fix` before improvising.

---

# WORKED EXAMPLES

### 1. Ordinary ask

> **User:** find me people building AI video ad tools

```bash
$BIN find "people building AI video ad tools" --deep 10 --agent
```

Envelope says `n_new: 7`, `n_known: 2`, `credits_spent: 13`, one source `no-results`.

> **You:** Seven new names, two already in your roster. 13 credits.
>
> [paste `table` verbatim]
>
> The two strongest are both hiring right now, which is usually the best time to reach out. X returned nothing this window, so this is LinkedIn and YouTube only.

Three sentences. No re-ranking. The `GAPS` line about X survived because it is inside `table`.

### 2. Drifted source — the absence trap

Envelope says `n_new: 0` and `source_status` has two entries in `unparsed`.

> **WRONG:** "I could not find anyone building AI video ad tools — the space looks quiet."
>
> **RIGHT:** "No usable results, but not because the market is empty — two sources answered in a format this build could not parse, so the run is broken rather than negative. [paste `table`] The GAPS line names the sources; worth re-running after the parser is fixed."

### 3. Cost-sensitive ask

> **User:** can you find AI video agencies but don't burn a ton of credits

```bash
$BIN find "AI video agencies" --deep 8 --dry-run --agent
```

> **You:** That plan is 4 query angles plus up to 8 profile fetches, so 12 credits maximum. Want me to run it, or trim it to discovery only for 4?

### 4. Nothing new

> **You:** Nothing new since your last run on this — all 6 names came back already in the roster, 5 credits. [paste `table`] If you want to widen it, `--freshness year` or a different angle would help more than re-running this one.

### 5. Wrong-fit results

> **User:** these aren't our kind of customer

Do **not** silently re-rank. Fit is a file the user owns.

> **You:** Fit is scored from `icp.json`, not my judgement — right now it is using [generic rules derived from your topic / your `higgsfield-accounts` file]. Run `icp init` to get an editable template, or tell me what disqualifies these and I will write the `penalty` terms.

### 6. "Top 10 with a writeup I can forward"

One run writes both files. Add your own framings for the field's vocabulary.

```bash
$BIN find "people building text-to-video tools" --deep 10 \
  --frame "generative video" --frame "AI film production" \
  --format md,pdf --out ~/Desktop/text-to-video --agent
```

> **You:** Ten profiles written up, 17 credits. `~/Desktop/text-to-video.pdf` and `.md` — each person has their role, audience, why they scored where they did, and the query that found them. Four of them turned up under more than one phrasing of the search, which is usually the strongest signal in the set.

### 7. "Give me ten more"

> **WRONG:** re-running `find` with a bigger `--deep`. That re-buys every search.

```bash
$BIN more --offset 10 --limit 10 --format md,pdf --out ~/Desktop/next-ten --agent
```

> **You:** Next ten from the same search, 10 credits — no new discovery, these were already found and just needed their profiles. Ranks 11 to 20 are in `~/Desktop/next-ten.pdf`.

### 8. They want it to look good

> **User:** can you make it prettier, this is going to a client

> **You:** Use the HTML version — open `shortlist.html` and print to PDF from the browser. The built-in PDF writer is dependency-free so it can run anywhere, but the browser will typeset it far better.

---

### 9. "What's their email?"

```bash
$BIN contacts --agent
```

> **You:** Three of the ten published an address; Jane's is hello@acme.com and she books meetings on Calendly. The rest did not put an inbox on a public page — I will not invent one. [paste `table`]
>
> If they want a *guessed* work email and `contact-goat-pp-cli` is installed: ask before spending, then run that binary. If it is not installed, say so.

---

# ICP FIT

Fit is a local JSON file the user owns. With no file, the engine derives a topic gate from the brief and applies generic seniority rules.

```bash
$BIN icp show --agent    # what is in force right now
$BIN icp init            # editable template at .who-finder/icp.json
$BIN signals --agent     # signal names available to score
```

Scoring is `must_any` (gate) → `boost` → `penalty` → `audience` → `geo` → `signals`, and every point that moved the score appears in `fit_reasons`. Two ready-made configs ship in `assets/`: `icp.higgsfield-accounts.json` (companies) and `icp.higgsfield-operators.json` (people).

Details and the exact arithmetic: [reference/icp.md](reference/icp.md).

---

# DO NOT

- Do not log into LinkedIn, pass cookies, or touch Sales Navigator. LinkedIn here is Google-indexed public URLs plus vendor profile endpoints.
- Do not send anything. No email, no DMs, no connection requests.
- Do not fan out to every source because it exists. Instagram only if they named it.
- Do not skip `find` and improvise queries in chat. If the plan is wrong, fix it with `--sources` or `--scenario`.
- Do not re-run `find` to refresh rows you already have — that is `report` for 0 credits.
- Do not treat "people at X companies" as a company search.
- Do not present an unenriched row as a qualified lead.
- Do not delete the `GAPS` section because the answer looks better without it.

---

# NAMED FAILURE MODES

Each of these is a specific way this output goes wrong. Recognise the shape in your own draft.

- **impersonation** — answered from memory or WebSearch without running the engine. Violates LAW 1.
- **redesign** — rewrote `table` into your own format, losing the fit arithmetic and the gaps.
- **phantom absence** — read `unparsed` or `error` as "nobody is doing this".
- **invented role** — filled a missing job title from the company name.
- **band inflation** — called an unenriched row a strong lead.
- **known as new** — led with names already marked outreached.
- **score mixing** — compared LinkedIn presence against YouTube engagement.
- **mask leak** — printed `*******` from a masked LinkedIn experience block.
- **silent overspend** — ran `--deep 40` on a vague brief without previewing.
- **keyword trap** — ran the engine on a brief with no topic in it.
- **gap deletion** — dropped the `GAPS` block so the answer reads cleaner.
- **silent re-rank** — reordered results to match what you thought the user wanted.
- **invented email** — wrote `jane@acme.com` because the company is Acme. Violates LAW 13.

---

# COMPOSE — OTHER SKILLS, NOT A SOUP

This engine stays public-data and clone-and-run. Two other tools sit next to it; you run them *as themselves* when the user asks for what they do.

| they ask | you run | never |
|---|---|---|
| what people are *saying* about a topic | `last30days` | do not pretend a who-finder shortlist is a conversation report |
| a work email they did not publish, a warm intro, who they already know at the company | `contact-goat-pp-cli` (if installed — `doctor` reports it) | do not invent `jane@acme.com`; do not run `waterfall` / `deepline find-email` without asking first |

`contacts` on this CLI is the public half: addresses and Calendly links already on the profile. That is a finding. A guessed inbox is not.

# WHEN NOT TO USE THIS SKILL

- Researching a *topic* rather than people — use `last30days`.
- Anything that writes to a remote system.
- Guessed work emails or warm intros — that is contact-goat, and only with consent to spend.
- Private or logged-in data of any kind.

---

# REFERENCE

One level deep, load only what the run needs.

| file | when |
|---|---|
| [reference/cli.md](reference/cli.md) | every flag, envelope, sink, profile, exit code |
| [reference/scenarios.md](reference/scenarios.md) | how detection works and what each scenario plans |
| [reference/people.md](reference/people.md) · [reference/companies.md](reference/companies.md) · [reference/creators.md](reference/creators.md) | per-scenario angles and pitfalls |
| [reference/hiring.md](reference/hiring.md) · [reference/press.md](reference/press.md) · [reference/compare.md](reference/compare.md) | the other three scenarios |
| [reference/sources.md](reference/sources.md) | endpoints, credits, freshness, drift detection |
| [reference/enrichment.md](reference/enrichment.md) | dossier fields, per-platform extraction, LinkedIn masking |
| [reference/icp.md](reference/icp.md) | fit config schema and the scoring arithmetic |
| [reference/insights.md](reference/insights.md) | coverage states, findings, notices, clusters, the absence rules |
| [reference/contacts.md](reference/contacts.md) | public emails and links; composing contact-goat |
| [reference/identity.md](reference/identity.md) | how a URL becomes `kind/platform/handle` |
| [reference/scoring.md](reference/scoring.md) | engagement vs presence, priority blending |
| [reference/roster.md](reference/roster.md) | new vs known, statuses, the seen-list |
| [reference/handoff.md](reference/handoff.md) | CSV columns |
| [reference/failure-modes.md](reference/failure-modes.md) | the full catalogue with diagnoses |
