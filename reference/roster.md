# Roster

The local memory that makes "new" mean new. Without it, every run re-presents the same names and outreach contacts people twice.

- [Where it lives](#where-it-lives)
- [Statuses](#statuses)
- [New versus known](#new-versus-known)
- [Seeding before the first run](#seeding-before-the-first-run)
- [What is stored](#what-is-stored)
- [Snapshots](#snapshots)
- [Sharing a roster](#sharing-a-roster)

## Where it lives

SQLite at `<cwd>/.who-finder/roster.sqlite`, overridable with `WHO_FINDER_HOME`, `WHO_FINDER_DB`, or `--db`.

It is per-project by default, which is usually what you want: a roster for an AI-video push and a roster for a hiring search should not de-duplicate against each other.

## Statuses

| status | meaning | set by |
|---|---|---|
| `new` | first seen, no decision yet | the engine, on insert |
| `watched` | interesting, not yet contacted | you, via `mark` |
| `outreached` | we have contacted them | you |
| `skip` | never surface again | you |
| `customer` | already a customer | you, usually via `import` |

Only `new` is set automatically. Everything else is a human decision the engine records and then respects.

## New versus known

`novelty` is computed per run and is not the same as `status`:

- A row inserted for the first time is `new`.
- A row that is still `status=new` on a later run is **still** `novelty=new` — nobody has acted on it, so it remains in the outreach queue.
- A row marked `watched`, `outreached`, `skip`, or `customer` comes back as `novelty=known`.

This distinction matters: re-finding an untouched name should not demote it, but re-finding someone you already emailed should never headline the report.

Lead with `n_new`. Known rows prove the seen-list works; they are not the news. When `n_new` is 0, say so plainly — it is a complete answer.

## Seeding before the first run

If the user already has a customer list or a do-not-contact list, `import` it **before** the first `find`:

```bash
$BIN import their-customers.csv
```

Minimum columns to seed skips: `kind,platform,handle,status`. An `id` column of the form `kind/platform/handle` works instead. See [handoff.md](handoff.md) and `assets/handoff.example.csv`.

Skipping this step is what produces the [known as new](failure-modes.md#known-as-new) failure — the first report proudly presents twelve names, four of whom are existing customers.

## What is stored

Per entity: identity, name, URL, status, first and last seen, hit count, rolled-up engagement, the query and scenario that found them, and the best sample hit.

Per dossier (after enrichment): headline, bio, audience and its kind, topics, signals, fit score, band, priority, and the full payload as JSON.

Per hit: the individual post or search result, with its own engagement and URL. This is what lets `show` reconstruct why someone ranked where they did.

No API key, no cookies, and no third-party identifiers are ever written. The roster holds public profile data and your own status decisions.

## Snapshots

Each run records a score snapshot per entity, which is what `previous_score` reads. It answers "did this identity get louder for these queries since last time" — see [scoring.md](scoring.md#previous_score) for what that does and does not mean.

## Sharing a roster

The file is a plain SQLite database and can be copied or committed. Two things to know:

Statuses are decisions, so a shared roster shares judgement calls — useful for a team working one campaign, wrong for two people running unrelated searches.

`export` produces the portable form. A CSV round-trips through `import`, which is the safer way to merge two people's work than copying the database.
