# Start — one folder, three commands

You need a Mac. Ten minutes. No programming.

---

## 1. Put the folder on your machine

**Cursor / Claude** (then you only talk, you do not type commands):

```bash
git clone https://github.com/romaluev/who-finder ~/.cursor/skills/who-finder
```

**Just the folder:**

```bash
git clone https://github.com/romaluev/who-finder
cd who-finder
```

If someone handed you a zip, unzip it and `cd` into `who-finder`. Same thing.

---

## 2. Check it is alive

```bash
./who-finder doctor
```

It should say **READY**. If it says “thinner path”, that is still READY — you can find people without a paid key.

---

## 3. The three commands

### Find people or companies

```bash
./who-finder find "CMO AI video ads"
```

Swap the words for whoever you want: founders, agencies, YouTubers, journalists, companies.

```bash
./who-finder find "agencies making AI video ads"
./who-finder find "who is hiring AI video editors"
```

To save a document:

```bash
./who-finder find "CMO AI video ads" --format html --out ~/Desktop/found
```

Open `found.html`.

### Rate a list

A sheet with names and LinkedIn (or YouTube) URLs. A Clay export is fine.

```bash
./who-finder rate ~/Desktop/names.csv
```

Writes `rating.html`, `rating.md`, and `rating.pdf` in the folder you are in. Open the HTML.

If you have no sheet, try the sample:

```bash
./who-finder rate tests/fixtures/creators.csv
```

That sample has no post history, so it will not invent a price. That is correct.

### Full flow — find, then rate, one report

```bash
./who-finder run "CMO AI video ads"
```

One command. Writes `run.html` (and md/pdf). That is the e2e path.

---

## Optional later

- **Clay export** — `./who-finder rate ~/Downloads/clay-export.csv` (no Clay API key).
- **Full LinkedIn / YouTube profiles** — a key from scrapecreators.com, then `./who-finder setup YOUR_KEY`.
- **Do not spend** — add `--cheap` on `find` or `run`.

You do not need any of that for the first test.

More sentences to ask the assistant: [What to ask](ask.md).
