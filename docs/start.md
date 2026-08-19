# Start — clone it, then ask

You need a Mac or Linux machine and ten minutes. No `pip`, no install, no programming. A key from [scrapecreators.com](https://scrapecreators.com) is optional — without it you still get a thinner shortlist from public search.

There are two ways in. Pick one.

---

## A. You use Cursor or Claude (the usual way)

After this, you never type a command. You just ask.

**1. Put the skill where your assistant looks.**

Cursor:

```bash
git clone https://github.com/romaluev/who-finder ~/.cursor/skills/who-finder
```

Claude:

```bash
git clone https://github.com/romaluev/who-finder ~/.claude/skills/who-finder
```

**2. Try it with nothing installed.**

```bash
# Cursor
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py find "founders of AI video tools" --deep 10
```

That works with no key. It is public search only — no profile pages fetched, fit capped at MAYBE. `doctor` will say **READY** on the thinner path.

**3. (Optional) Save a key for full profiles.**

Get one at [scrapecreators.com](https://scrapecreators.com). Everyone uses their own — do not reuse a teammate's. Then:

```bash
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py setup YOUR_KEY
```

You should see `Key saved`. Open a **new** terminal and run `doctor` — it should say **READY** (full). If it still says the thinner path, the key did not stick — see [Your key](key.md).

Optional, free-tier web search that spends no ScrapeCreators credits:

```bash
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py setup --brave YOUR_BRAVE_KEY
```

**4. Ask, in plain English.**

> Find me the top 10 people building AI video tools and write it up as a PDF.

That is the whole job. More things to say: [What to ask](ask.md).

---

## B. You just want the folder (no assistant)

```bash
git clone https://github.com/romaluev/who-finder
cd who-finder
./who-finder find "founders of AI video tools" --deep 10
```

No setup required. See the exact searches and cost (often $0) before a paid run:

```bash
./who-finder find "founders of AI video tools" --deep 10 --dry-run
```

Then, if you want full profiles:

```bash
./who-finder setup YOUR_KEY
./who-finder doctor
./who-finder find "founders of AI video tools" --deep 10 --format md,html --out ~/Desktop/shortlist
```

Open `~/Desktop/shortlist.html` in a browser. Print to PDF if you want the pretty version.

---

## If something looks wrong

| you see | it means | do this |
|---|---|---|
| `READY` (full) | ScrapeCreators works | ask, or run `find --deep` |
| `READY` (thinner path) | no paid key; public search still runs | run `find` anyway, or [add a key](key.md) for profiles |
| `KEY REJECTED` | the paid key is wrong; thin path still works | get a new key, `setup` again, or run thin |
| `command not found: python3` | Python is missing | Macs have it. On Linux: install Python 3.9+ |
| `./who-finder: Permission denied` | the file is not executable | `chmod +x who-finder` |

A typical *full* shortlist costs about **15 credits** (a handful of searches + 10 profiles). A thin run is **$0**. `--dry-run` shows the number before you agree. `--cheap` keeps one framing and saves paid credits for profile enrich.

It never sends email, never logs into LinkedIn, and never invents a name or an inbox.
