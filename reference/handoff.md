# Handoff CSV

`export` produces the artifact a human or a CRM picks up. It is the end of this skill's responsibility — nothing here sends anything.

- [Exporting](#exporting)
- [Columns](#columns)
- [Filtering what goes in](#filtering-what-goes-in)
- [Importing](#importing)
- [The round trip](#the-round-trip)

## Exporting

```bash
$BIN export --status new --band strong --out handoff.csv
$BIN export --status new --deliver file:~/Desktop/handoff.csv --agent
$BIN export --status new --deliver webhook:https://hooks.example.com/leads --agent
```

Zero credits — it reads the roster only. With `--deliver`, the CSV itself is the delivered body rather than the JSON envelope, because the sheet is the artifact.

Without `--out` or `--deliver`, the CSV goes to stdout.

## Columns

```
kind,platform,handle,id,name,url,status,novelty,score,previous_score,
hit_count,views,likes,comments,shares,last_query,last_scenario,
first_seen,last_seen,sample_title,sample_url,notes
```

| group | columns | note |
|---|---|---|
| identity | `kind,platform,handle,id,name,url` | `id` is `kind/platform/handle` |
| state | `status,novelty` | your decisions, and new-vs-known for this run |
| ranking | `score,previous_score,hit_count` | `score` is mode-dependent — see [scoring.md](scoring.md) |
| engagement | `views,likes,comments,shares` | **empty on every LinkedIn and web row** |
| provenance | `last_query,last_scenario,first_seen,last_seen` | how and when we found them |
| evidence | `sample_title,sample_url` | the best single hit, so a reviewer can sanity-check the row |
| free text | `notes` | yours |

The empty engagement columns on LinkedIn rows are honest rather than broken: those rows come from a Google index that reports no interaction data. A reviewer sorting the sheet by `views` will see all LinkedIn rows sink, which is a property of the source, not a ranking.

## Filtering what goes in

| flag | effect |
|---|---|
| `--status` | default `new`; the outreach queue |
| `--band` | `strong`, `possible`, `weak`, `off`, `unknown` |
| `--kind` | `person` or `company` |
| `--query` | rows found by a specific brief |
| `--limit` | default 200 |

`--status new --band strong` is the useful default for handing work to a human: names nobody has contacted, that the ICP actually endorses.

## Importing

```bash
$BIN import their-list.csv
```

Reads the same shape. Minimum to seed a skip list:

```csv
kind,platform,handle,status
person,linkedin,jane-doe,customer
company,linkedin,acme-video,skip
```

An `id` column works instead of the three parts:

```csv
id,status
person/linkedin/jane-doe,customer
```

Unknown columns are ignored, so a CSV exported from a CRM usually imports without editing.

`assets/handoff.example.csv` is a working template.

## The round trip

Export and import are symmetric, which makes the CSV the right way to merge two people's work — safer than copying the SQLite file, because it merges statuses rather than overwriting a whole roster.

The intended loop:

1. `import` the existing customer and do-not-contact list, before the first `find`.
2. `find --deep` to produce candidates.
3. `mark` as decisions get made, or edit `status` in the sheet and `import` it back.
4. `export --status new --band strong` for the next batch.

Step 1 is the one people skip, and it is what makes the first report trustworthy.
