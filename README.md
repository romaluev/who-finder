# who-finder

Find people. Rate who is worth buying. One folder, three commands.

```bash
./who-finder find "CMO AI video ads"
./who-finder rate names.csv
./who-finder run "CMO AI video ads"
```

No programming. No `pip`. A key is optional.

**[Start here →](docs/start.md)**

---

## What each command does

| Command | You give it | You get back |
|---|---|---|
| `find` | keywords | a shortlist of real people or companies |
| `rate` | a CSV, a Clay export, or the file `find` wrote | who to buy, at what ceiling, as a document |
| `run` | keywords | `find` then `rate` — writes `run.html` you can forward |

It never invents a name, an email, or a price. If it could not measure something, the report says so.

## Install (once)

You need a Mac and Python (already there).

**You use Cursor or Claude** — then you only ask in English:

```bash
git clone https://github.com/romaluev/who-finder ~/.cursor/skills/who-finder
```

Say: *Find me 10 people making AI video ads.*  
Or: *Rate this Clay export.*  
Or: *Find CMOs in AI video and tell me who to buy.*

**You just want the folder:**

```bash
git clone https://github.com/romaluev/who-finder
cd who-finder
./who-finder doctor
```

`doctor` saying READY is enough to start. Full walkthrough: [docs/start.md](docs/start.md).

## Guides

| | |
|---|---|
| [Start](docs/start.md) | install, first find, first rate, full flow |
| [What to ask](docs/ask.md) | sentences for Cursor / Claude |
| [Your key](docs/key.md) | optional — full LinkedIn / YouTube profiles |
| [Economy](docs/economy.md) | Clay first, paid scrapers last |

## What it won't do

Send messages. Log into LinkedIn. Write to your CRM. Guess an email. Invent a price from follower count.
