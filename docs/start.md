# Start — clone it, then ask

You need a Mac or Linux machine, ten minutes, and a key from [scrapecreators.com](https://scrapecreators.com). No `pip`, no install, no programming.

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

**2. Save your key so it is still there tomorrow.**

Get one at [scrapecreators.com](https://scrapecreators.com). Everyone uses their own — do not reuse a teammate's. Then:

```bash
# Cursor
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py setup YOUR_KEY

# Claude
python3 ~/.claude/skills/who-finder/scripts/who_finder.py setup YOUR_KEY
```

You should see `Key saved`. Open a **new** terminal and check:

```bash
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py doctor
```

It should say **READY**. If it says NOT SET UP, the key did not stick — see [Your key](key.md).

**3. Ask, in plain English.**

> Find me the top 10 people building AI video tools and write it up as a PDF.

That is the whole job. More things to say: [What to ask](ask.md).

---

## B. You just want the folder (no assistant)

```bash
git clone https://github.com/romaluev/who-finder
cd who-finder
./who-finder setup YOUR_KEY
./who-finder doctor
```

See a search before you spend anything:

```bash
./who-finder find "founders of AI video tools" --deep 10 --dry-run
```

That prints the exact queries and the credit ceiling. Nothing is spent, nothing is stored.

Then the real thing, written up:

```bash
./who-finder find "founders of AI video tools" --deep 10 --format md,html --out ~/Desktop/shortlist
```

Open `~/Desktop/shortlist.html` in a browser. Print to PDF if you want the pretty version.

---

## If something looks wrong

| you see | it means | do this |
|---|---|---|
| `READY` | it works | ask, or run `find` |
| `NOT SET UP` | no key on this machine | [Your key](key.md) |
| `KEY REJECTED` | the key is wrong or expired | get a new one, `setup` again |
| `command not found: python3` | Python is missing | Macs have it. On Linux: install Python 3.9+ |
| `./who-finder: Permission denied` | the file is not executable | `chmod +x who-finder` |

A typical first shortlist costs about **15 credits** (a handful of searches + 10 profiles). `--dry-run` shows the number before you agree.

It never sends email, never logs into LinkedIn, and never invents a name or an inbox.
