# who-finder

Describe who you're looking for. Get back a shortlist of real people — who they are, how to reach them, why each one is worth your time — as a document you can forward.

```bash
git clone https://github.com/romaluev/who-finder
cd who-finder
./who-finder find "founders of AI video tools" --deep 10
```

No key required for a thinner public-search shortlist. A ScrapeCreators key unlocks full profiles. **[Start here →](docs/start.md)**

---

## What you get back

Not a list of links. A finished report — a summary of what it found, then a page on each person:

> **1. Jane Doe** — Head of Content at Acme
> **STRONG FIT** · 24k followers · Austin
> Leads a team making AI video ads for consumer brands. Hiring a senior video producer right now.
> *How to reach her:* hello@acme.com · calendly.com/jane — she published both.
> *Easy to miss:* same person as the YouTube channel in this set; creator-shaped LinkedIn (24k followers, 500 connections).
> *Why she's here:* matches your topic, runs a team, audience in your target range, and three different phrasings of the search all surfaced her.

Everyone is ranked. Every score shows its working. Anyone the tool couldn't fully verify is marked as such rather than dressed up. It never invents a name, a title, or an email.

## Start in three minutes

You need Python 3.9+ (already on every Mac). No `pip`, no build. A key from [scrapecreators.com](https://scrapecreators.com) is optional — without it you still get a thinner shortlist.

**You use Cursor or Claude** — clone into the skills folder so you can just ask:

```bash
git clone https://github.com/romaluev/who-finder ~/.cursor/skills/who-finder
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py setup YOUR_KEY
```

Then say: *"Find me the top 10 people building AI video tools and write it up as a PDF."*

**You just want the folder:**

```bash
git clone https://github.com/romaluev/who-finder
cd who-finder
./who-finder setup YOUR_KEY
./who-finder find "founders of AI video tools" --deep 10 --dry-run
```

`--dry-run` is free and needs no key. It prints the exact searches, which backend each step would use, and the credit ceiling ($0 when every step is free).

Full walkthrough, including the thinner no-key path: **[docs/start.md](docs/start.md)**

## Guides

| | |
|---|---|
| [Start](docs/start.md) | clone, key, first search |
| [What to ask](docs/ask.md) | daily sentences for Cursor / Claude |
| [Your key](docs/key.md) | save it, check it, it worked yesterday |
| [Share with the team](SHARE.md) | one seen-list, one definition of fit |

## What it costs

DuckDuckGo, Brave, and Hacker News are free. Each ScrapeCreators search and each profile it reads is one credit. A typical *full* "top 10, written up" run is about 15 credits. `--cheap` saves those credits for enrich. You can see the number before spending, and set a hard cap it will not exceed.

## What it won't do

Send messages, log into LinkedIn, or write to your CRM. It finds and qualifies; reaching out is still yours.

---

*Machinery below — you do not need it to get a shortlist.*

## How it works

1. It picks the kind of search (people, companies, creators, hiring, press, A vs B).
2. It asks the question several ways, so it reaches people who do not use your exact words.
3. It reads public profiles — role, audience, recent posts, emails and Calendly links they published.
4. It scores each one against *your* definition of a good fit, with the arithmetic shown.
5. It ranks and remembers, so you never get the same name twice.
6. It writes Markdown, a styled web page, or a PDF.

### Reports

`--format md,html,pdf --out PATH` writes files. `html` is the best-looking (print to PDF from a browser). `pdf` needs nothing installed. "Ten more" is `more --offset 10`, not another search.

### Teach it your ICP

```bash
./who-finder icp init
./who-finder signals
```

Fit is a local JSON file you own. Two worked examples ship in `assets/`.

### Commands

```bash
./who-finder                  # what to do next — safe with no key
./who-finder setup YOUR_KEY   # save the key so tomorrow still works
./who-finder doctor           # READY (full) / READY (thinner) / KEY REJECTED
./who-finder find "founders of AI video tools" --deep 10 --dry-run
./who-finder find "founders of AI video tools" --deep 10 --format md,html --out shortlist
./who-finder contacts         # emails they published
./who-finder more --offset 10
./who-finder export --status new --band strong --out handoff.csv
```

`--agent` wraps any command in JSON. `--max-credits N` is a hard stop. Full flag list: [reference/cli.md](reference/cli.md).

### Tests

```bash
python3 -m pytest tests -q      # no network, no key required
```

## License

Apache-2.0
