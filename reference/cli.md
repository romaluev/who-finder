# CLI reference

Everything the engine exposes. `SKILL.md` carries the rules; this file carries the surface.

- [Invocation](#invocation)
- [The envelope](#the-envelope)
- [Global flags](#global-flags)
- [Field projection with --select](#field-projection-with---select)
- [Delivery sinks with --deliver](#delivery-sinks-with---deliver)
- [Profiles](#profiles)
- [Cost control](#cost-control)
- [Exit codes and the error envelope](#exit-codes-and-the-error-envelope)
- [Command by command](#command-by-command)
- [Environment](#environment)
- [Self-description](#self-description)

## Invocation

```bash
BIN="python3 $SKILL_DIR/scripts/who_finder.py"
```

Python 3.11+, standard library only. No pip, no build, no network at import time. `scripts/who_finder.py` is always a sibling of `SKILL.md`.

## The envelope

Every command with `--agent` emits exactly one JSON object on stdout, one line, and nothing else.

```json
{
  "meta":    { "source": "who-finder", "version": "3.2.0", "credits_spent": 12, "...": "..." },
  "plan":    { "scenario": "people", "steps": [ ... ] },
  "table":   "the rendered human report",
  "results": { "...": "command-specific payload" }
}
```

`meta` is always present. `plan` appears on `find`. `table` appears wherever there is something to show a human — it is the user-facing answer and is meant to be pasted, not parsed.

Failures replace `results` with `error`:

```json
{
  "meta":  { "source": "who-finder", "ok": false },
  "error": { "code": 8, "name": "budget refused — ...", "message": "plan needs up to 25 credits, --max-credits is 6",
             "fix": "raise --max-credits, lower --deep, or narrow --sources", "estimate": { "...": "..." } }
}
```

`error.fix` is a next action, not an apology. Read it before improvising a retry.

Without `--agent`, commands print `table` if they have one and pretty JSON otherwise. That mode is for humans; scripts should always pass `--agent`.

## Global flags

Accepted before or after the subcommand — `--profile x find "..."` and `find "..." --profile x` are the same call.

| flag | effect |
|---|---|
| `--agent` | JSON envelope on stdout |
| `--select PATHS` | keep only these dotted paths |
| `--deliver SINK` | `stdout` \| `file:<path>` \| `webhook:<url>` |
| `--profile NAME` | apply a saved flag set; explicit flags still win |
| `--db PATH` | override the roster location |
| `--version` | print version and exit |

## Field projection with `--select`

A `--deep 10` run returns ten dossiers. That is usually more than the caller needs and it crowds out the reasoning that should follow. Name the fields instead:

```bash
$BIN find "AI video founders" --deep 10 --agent \
  --select results.n_new,results.entities.id,results.entities.priority,results.entities.fit_band
```

Paths are dotted. Lists traverse element-wise, so `results.entities.id` means "the id of every entity" and returns a list — you never need an index.

**`meta` and `error` always survive projection.** A caller that could project away the credit count or a failure state would be able to mistake a broken run for a thin one, so those two keys are not projectable.

Paths that match nothing are dropped rather than emitted as `null`, so a typo shows up as a missing key rather than a fake empty value.

## Delivery sinks with `--deliver`

Routes the output somewhere instead of stdout. When a sink is used, stdout gets a small receipt rather than a second copy.

| sink | behaviour |
|---|---|
| `stdout` (default) | print |
| `file:<path>` | write atomically — temp file plus rename, so a reader never sees a partial write. Parent directories are created. |
| `webhook:<url>` | POST the body; `application/json` in agent mode, `text/plain` otherwise |

On `export` the delivered body is the CSV itself rather than the envelope, because the sheet is the artifact. `--out <path>` remains as shorthand for `--deliver file:<path>`.

A bad sink exits `9` and names the supported set.

## Profiles

A saved set of flag values for a command you run repeatedly — a nightly sweep, a standing scenario.

```bash
$BIN profile save nightly --set deep=10 --set scenario=people --set freshness=month
$BIN profile list --agent
$BIN profile show nightly --agent
$BIN --profile nightly find "AI video ops hires"
$BIN profile delete nightly
```

Values coerce: `10` is an int, `true`/`false` are booleans, everything else is a string.

**Precedence is explicit flag > profile > default.** A profile only fills a flag you did not set, so `--profile nightly find "..." --deep 3` runs at depth 3. `agent-context` lists saved profiles under `available_profiles` so a caller can discover them at runtime.

Stored at `<home>/profiles.json`. Names are restricted to letters, digits, dot, underscore and hyphen — a profile name becomes part of no path, and the restriction keeps it that way.

## Cost control

Discovery costs one credit per query angle; enrichment costs one per profile and zero on a cache hit. Nothing else costs anything.

**Preview before spending:**

```bash
$BIN find "AI video tooling" --deep 25 --dry-run
```

`--dry-run` prints the exact queries the planner produced and the credit ceiling, touches no network, needs no API key, and writes nothing to the roster. It is the honest way to get consent for a spend, and the fastest way to see whether the planner understood the brief.

**Cap the spend:**

```bash
$BIN find "AI video tooling" --deep 25 --max-credits 20
```

The cap is evaluated against the plan *before* the first request. Over budget exits `8` and returns the estimate and the plan in the error envelope, so a caller can decide what to trim without re-planning.

The estimate is a ceiling, not a forecast: cached profile reads are free, so real spend is often lower. `meta.credits_spent` after a run is the actual figure.

## Exit codes and the error envelope

| code | name | typical cause |
|---|---|---|
| 0 | success | |
| 2 | usage error | unknown scenario or source, malformed `--set`, empty plan |
| 3 | not found | id absent from the roster, nothing to enrich, no lateral links |
| 4 | auth required | `SCRAPECREATORS_API_KEY` missing, or rejected with 401/403 |
| 5 | upstream API error | vendor 5xx, timeout, unreadable response |
| 8 | budget refused | plan exceeds `--max-credits` |
| 9 | delivery failed | unknown or unwritable `--deliver` sink |
| 10 | config error | `icp.json` is malformed or unreadable |

Codes are a stable contract: a number never changes meaning, and a new condition gets a new number.

Exit `10` deserves a note. A malformed `icp.json` **stops the run** rather than falling back to the generic rules. Someone who edited that file expects their rules to be the ones scoring the results, and a quiet fallback would produce a plausible ranking against the wrong ICP — the kind of error nobody catches.

## Command by command

### `find` — the primary verb

```bash
$BIN find "BRIEF" [--deep N] [--scenario S] [--sources a,b] [--limit N]
                  [--freshness month|year|all] [--new-only] [--dry-run]
                  [--max-credits N] [--icp PATH] [--cache 1d|3d|7d|14d|30d]
                  [--show N] [--full]
                  [--frames N] [--frame PHRASE ...]
                  [--format md,html,pdf,json] [--out PATH]
```

Detects the scenario, plans angles, reframes the topic, searches, parses identities, de-dupes against the roster, enriches the top `N`, scores ICP fit, ranks, renders.

`--full` includes complete dossiers in the JSON; without it `results.dossiers` is empty and the compact per-entity fields carry the summary. `--show` controls how many cards the rendered brief prints, independent of how many entities the JSON carries.

`--frames N` (default 3) caps how many ways the topic is asked; `--frames 1` disables reframing. `--frame PHRASE` is repeatable and adds vocabulary the engine cannot derive. Each extra frame is exactly one more search. See [framing.md](framing.md).

`--format` writes files instead of printing a brief, and `--out` is a path **without** an extension. See [reports.md](reports.md).

### `report` — re-render for free

```bash
$BIN report [--status S] [--kind K] [--query Q] [--band B]
            [--limit N] [--offset N] [--format F] [--out PATH]
```

Rebuilds from stored data. Zero credits, no network. This is the correct response to "show me that again", "just the strong ones", or "the companies only" — never re-run `find` for those.

`--limit` is the size of the slice and `--offset` skips that many from the top, keeping true rank numbers so two reports can sit side by side. With `--format` it writes documents rather than printing.

### `more` — the next N, without searching again

```bash
$BIN more [--offset N] [--limit N] [--status S] [--kind K] [--query Q]
          [--format F] [--out PATH]
```

Walks further down the ranking discovery already produced and enriches whatever has not been enriched yet: **one credit per new profile, zero for discovery.** Exits `3` when the ranking is exhausted, and `4` if unenriched rows remain but no API key is set — in that case `report --offset N` still pages through what is already stored, for free.

### `enrich` — fill in stored rows

```bash
$BIN enrich [IDENTITY ...] [--status S] [--kind K] [--limit N] [--cache 7d]
```

One credit per profile, zero on a cache hit. Use it to resolve a `?` band on a specific name instead of upgrading it in prose.

### `expand` — lateral discovery for free

```bash
$BIN expand IDENTITY
```

Pulls "people also viewed" profiles and listed employees out of a dossier you already paid for. Zero credits. Returns nothing (exit 3) on platforms that expose no lateral links.

### `setup` — save the key

```bash
$BIN setup YOUR_KEY
$BIN setup            # status + where the file lives
$BIN setup --clear    # forget the saved file
```

Writes `~/.who-finder/key` (or `$WHO_FINDER_HOME/key`) at mode 0600. `export SCRAPECREATORS_API_KEY` still wins if both are set. The file is why a clone still works tomorrow. See [docs/key.md](../docs/key.md).

### `doctor` — health

```bash
$BIN doctor [--probe]
```

Reports one of `ready`, `ready-thin`, `auth-failed`, `error`, plus a capability card per backend (DuckDuckGo, HN, ScrapeCreators, Brave, yt-dlp, last30days, contact-goat). Missing ScrapeCreators is `ready-thin` (usable), not a stop. A rejected key still notes that the thin path is available. `--probe` spends one credit on a real YouTube search and is the only command that proves the live paid path end to end.

### `agent-context` — self-description

```bash
$BIN agent-context --agent
```

Commands with their credit costs, scenarios, sources, signals, bands, statuses, exit codes, env vars, resolved paths, saved profiles, and the cost model. Generated from the same constants the commands use, so it cannot drift from real behaviour. Read this instead of guessing at flags.

### `which` — capability lookup

```bash
$BIN which "who should we pitch in AI video" --agent
```

Maps a natural-language capability to a command. Exit 0 means a confident match, 2 means none.

### Roster commands

```bash
$BIN list [--status S] [--query Q] [--kind K] [--scenario S] [--limit N]
$BIN new  [--query Q] [--kind K] [--limit N]
$BIN show IDENTITY
$BIN mark IDENTITY --status new|watched|outreached|skip|customer
$BIN export [--status S] [--band B] [--kind K] [--limit N] [--out PATH]
$BIN contacts [--status S] [--band B] [--kind K] [--limit N]
$BIN import PATH.csv
```

All zero credits. `import` before your first `find` when the user already has a skip or customer list — that is what makes "new" mean new. `contacts` prints emails and links already on stored profiles; it does not guess a work inbox. See [contacts.md](contacts.md).

### Config and meta

```bash
$BIN icp show|init [--icp PATH]
$BIN signals
$BIN scenarios
$BIN search QUERY --sources youtube    # debug hatch: one raw keyword, no planner
$BIN feedback "what surprised you" [--context find]
$BIN feedback list [--limit N]
```

`search` bypasses the planner and is for diagnosing the engine, not for answering a user. If you find yourself reaching for it to answer a question, the answer is `find` with `--sources` or `--scenario`.

`feedback` appends to `<home>/feedback.jsonl` and is never transmitted anywhere. Write what *surprised* you, one line, specific — that is the part that compounds.

## Environment

| var | default | purpose |
|---|---|---|
| `SCRAPECREATORS_API_KEY` | — | required for anything that spends credits |
| `WHO_FINDER_HOME` | `./.who-finder` | roster, ICP, profiles, feedback |
| `WHO_FINDER_DB` | `<home>/roster.sqlite` | roster path only |
| `WHO_FINDER_ICP` | `<home>/icp.json` | ICP config path only |

The key is read from the environment and never written to disk, never logged, and never included in any envelope — `doctor` reports only whether it is present.

## Self-description

Two commands exist so an agent can drive this CLI without reading documentation:

```bash
$BIN agent-context --agent    # the whole surface, machine-readable
$BIN which "<capability>"     # phrase to command
```

Prefer them over guessing. They are generated from the live constants, so they stay correct as the tool changes.
