# who-finder

**Describe who you're looking for. Get back a shortlist of real people — who they are, how big their audience is, why each one is worth your time — as a document you can forward.**

You ask in plain English: *"people building AI video tools"*, *"agencies scaling generative video"*, *"journalists covering synthetic media"*. It searches public profiles, reads them, ranks the best fits against your own criteria, and writes it up. It remembers who it already showed you, so you never get the same name twice.

---

## What you get back

Not a list of links. A finished report — a summary of what it found, then a page on each person:

> **1. Jane Doe** — Head of Content at Acme
> **STRONG FIT** · 24k followers · Austin
> Leads a team making AI video ads for consumer brands. Hiring a senior video producer right now.
> *How to reach her:* hello@acme.com · calendly.com/jane — she published both.
> *Easy to miss:* same person as the YouTube channel in this set; creator-shaped LinkedIn (24k followers, 500 connections).
> *Why she's here:* matches your topic, runs a team, audience in your target range, and three different phrasings of the search all surfaced her.

Everyone is ranked. Every score shows its working. Anyone the tool couldn't fully verify is marked as such rather than dressed up.

## The one thing to try

You don't run this yourself — **you ask for it.** If you have an AI assistant set up with this skill, you just say:

> *"Find me the top 10 people building AI video tools and write it up as a PDF."*

That's the whole job. The assistant handles the rest and hands you a document.

If you're setting it up for the first time, the [setup guide](SHARE.md) walks through it in a few minutes — no programming needed.

---

*The rest of this page is for whoever sets it up or wants to know how it works.*

## How it works

1. **It understands the request.** "People", "companies", "creators", "who's hiring", "journalists", "X vs Y" are different kinds of search, and it plans accordingly.
2. **It asks the question several ways.** One phrasing only finds the people who describe themselves that way, so it reframes your topic — and you can add the field's own vocabulary — to reach the people a literal search misses.
3. **It reads public profiles.** Role, audience size, location, what they've posted recently, and any email or Calendly they published themselves. Nothing private, nothing behind a login, and it never invents an inbox.
4. **It scores each one against *your* definition of a good fit**, with the arithmetic shown — not a model's opinion.
5. **It ranks and remembers.** Best first, and it never shows you the same name twice.
6. **It writes it up** as Markdown, a styled web page, or a PDF.

## What it costs

Each search and each profile it reads costs one credit from a [ScrapeCreators](https://scrapecreators.com) key. A typical "top 10, written up" run is about 15 credits. You can see the exact cost before spending anything, and set a hard cap it will not exceed.

## What it won't do

Send messages, log into LinkedIn, or write to your CRM. It finds and qualifies people; reaching out is still yours. And it never invents a name, a job title, or a number — everything in the report came from a real public page.

---

## For the person setting it up

Everything below is the machinery. You need Python 3.9+ (already on every Mac) and one API key. No `pip`, no build, no dependencies.

```bash
git clone https://github.com/romaluev/who-finder ~/.cursor/skills/who-finder
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py
```

That second line is safe to run before anything is configured — it prints what the tool does, whether your setup is ready, and the one command worth trying first. Use `~/.claude/skills/who-finder` for Claude, or `.claude/skills/who-finder` inside a project.

**See it before you have a key** — no network, no spend, prints the exact searches it would run:

```bash
python3 .../who_finder.py find "founders of AI video tools" --deep 10 --dry-run
```

**Then add a key.** The one thing you can't skip, billed per key so everyone uses their own:

```bash
export SCRAPECREATORS_API_KEY=...
python3 .../who_finder.py doctor      # checks the key and your credit balance
```

**Verification status — read once.** The parsers were written against ScrapeCreators' documented response shapes and are covered by offline tests, but have not been exercised against a live key. Run `doctor --probe` first. If upstream has moved a field, you won't get a silent empty result — the source is reported as `UNPARSED` with a `SCHEMA DRIFT` line naming it, so a parser bug never masquerades as an empty market.

### Reports

`--format md,html,pdf --out PATH` writes the run up as files. `md` pastes anywhere, `html` is the best-looking and prints to a clean PDF from a browser, `pdf` is the attachable version and needs nothing installed. See [reference/reports.md](reference/reports.md).

"Ten more" doesn't re-run the search: `more --offset 10` continues down the ranking already found (one credit per new profile), and `report --offset 10` re-cuts a slice you already own for free.

### Framing

`--frame "generative video"` adds a phrasing the engine can't derive on its own — the field's own vocabulary. Each frame is one extra search, and anyone surfaced by more than one is flagged as corroborated. See [reference/framing.md](reference/framing.md).

### Teach it your ICP

Fit is a local JSON file you own; without one it derives generic rules from your brief.

```bash
python3 scripts/who_finder.py icp init      # editable template
python3 scripts/who_finder.py signals       # the signal names you can score
```

```json
{
  "must_any": ["ai video", "generative video"],
  "boost": { "founder": 15, "head of": 12, "agency": 10 },
  "penalty": { "student": -20, "intern": -15 },
  "audience": { "min": 1000, "sweet_min": 10000, "sweet_max": 2000000, "weight": 20 },
  "geo": { "prefer": ["united states"], "weight": 8 },
  "signals": { "hiring": 10, "funded": 12 }
}
```

Two worked examples ship in `assets/`, ported from a real GTM rubric. [reference/icp.md](reference/icp.md) walks through what survives translation.

### CLI

```bash
B="python3 scripts/who_finder.py"

$B doctor --agent                                  # health + credits
$B which "who should we pitch" --agent             # phrase -> command
$B find "founders of AI video tools" --deep 10     # the main verb
$B find "AI video ads" --frame "generative creative" --deep 10
$B find "AI video ads" --deep 10 --format md,pdf --out ~/Desktop/shortlist
$B report --status new                             # re-render the brief, 0 credits
$B more --offset 10 --limit 10                     # the next ten, enrichment only
$B enrich person/linkedin/jane-doe                 # dossier for one name
$B expand company/linkedin/acme                    # its staff + lookalikes, 0 credits
$B show person/youtube/adlab                       # full dossier card
$B mark person/linkedin/jane-doe --status outreached
$B export --status new --band strong --out handoff.csv
$B contacts                                        # emails and links they published
$B import known-customers.csv                      # seed a skip list
```

Add `--agent` to any command for a single JSON envelope. `--dry-run` previews cost, `--max-credits N` is a hard stop, `--select` trims fields, `--deliver` routes output to a file or webhook, `--profile` saves flag sets. `agent-context --agent` describes the whole CLI from live constants. Every failure is a branchable error with an exit code, not a stack trace. Full reference: [reference/cli.md](reference/cli.md).

### Where the data lives

`.who-finder/roster.sqlite` in your working directory. Override with `WHO_FINDER_HOME` or `--db`; two people can share a roster by pointing `--db` at the same file. A name stays `new` until you mark it — re-running a search never quietly retires it.

### Tests

```bash
python3 -m pytest tests -q      # 190 tests, no network, no key required
```

## License

Apache-2.0
