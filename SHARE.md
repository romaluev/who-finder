# Sharing this with your team

Repo: **https://github.com/romaluev/who-finder**

Send them that link and this sentence:

> Clone it, run `setup` with your own key, then ask your assistant. Guide: [docs/start.md](docs/start.md)

They do **not** need the rest of any other workspace, and they must not use your API key.

## What they do

1. Clone — into `~/.cursor/skills/who-finder` (Cursor) or `~/.claude/skills/who-finder` (Claude), or any folder if they just want the CLI.
2. Get their own key at [scrapecreators.com](https://scrapecreators.com).
3. `./who-finder setup THEIR_KEY` (or the `python3 …/who_finder.py setup` form in the [start guide](docs/start.md)).
4. Ask: *"Find me the top 10 people building AI video tools and write it up as a PDF."*

What they get back, what to type next: [docs/ask.md](docs/ask.md). Key problems: [docs/key.md](docs/key.md).

## Optional — only if you coordinate a team

**A shared seen-list** stops two people emailing the same lead. By default each person's history is their own. Point everyone at one file with `--db /shared/team-roster.sqlite`, or set `WHO_FINDER_HOME` to a synced folder. Without this, "new" means new *to you*.

**A shared definition of fit** keeps scoring consistent. Commit an `icp.json` and have people pass `--icp ./team-icp.json`. Seed existing customers first with `import known-customers.csv` so they never surface as fresh leads.

**Agents can learn the tool themselves.** `agent-context --agent` describes the whole CLI from live constants. Nobody has to read `reference/` before the first useful run.

## Don't send

- your API key
- another team's repo or CRM export
- anything you would not want pasted into a shortlist

This researches people and hands you a document. It does not message anyone.
