# Sharing this with your team

Public repo: **https://github.com/romaluev/who-finder**

## Send them this

> Install:
> ```bash
> git clone https://github.com/romaluev/who-finder ~/.cursor/skills/who-finder
> export SCRAPECREATORS_API_KEY=...   # your own key from https://scrapecreators.com
> ```
> Then ask your agent: *"find founders of AI video tools"*, *"find companies building text-to-video"*, *"who is hiring for AI video editors"*, or *"journalists covering generative video"*.

That is the whole onboarding. No pip, no build, no config file required on day one.

Swap the clone path for `~/.claude/skills/who-finder` or, for a single project, `.claude/skills/who-finder` inside the repo they are working in.

## Their agent can learn the tool by itself

Two commands mean nobody has to read documentation before their first useful run:

```bash
python3 .../who_finder.py agent-context --agent          # the whole CLI, machine-readable
python3 .../who_finder.py which "how much will this cost"
```

And nobody has to guess what a search will cost. `--dry-run` prints the exact queries and the credit ceiling without spending anything or even needing a key — it is the safest possible first command:

```bash
python3 .../who_finder.py find "AI video agencies" --deep 10 --dry-run
```

## Each person needs their own API key

Credits are billed per key, so keys are not shared. `doctor` reports `skipped-unconfigured` and exits 4 until one is set, which is a clear signal rather than a confusing empty result.

```bash
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py doctor --agent
```

## Rosters are per-person unless you decide otherwise

The seen-list lives in `.who-finder/roster.sqlite` in whatever directory the agent is working from. Two ways to make it shared:

- point everyone at one file: `--db /shared/team-roster.sqlite`
- or set `WHO_FINDER_HOME` to a synced folder

Shared rosters are what stop two people cold-emailing the same person in the same week. Without one, "new" means new *to you*.

## Give the team a shared ICP

Fit scoring is a JSON file. Commit one to your own repo and have people point at it:

```bash
python3 .../who_finder.py find "BRIEF" --deep 10 --icp ./team-icp.json
```

Or seed a skip list of existing customers before anyone searches, so they never surface as fresh leads:

```bash
python3 .../who_finder.py import known-customers.csv
```

Format is in [assets/handoff.example.csv](assets/handoff.example.csv).

## Do not send

- your API key
- the rest of the Higgsfield workspace
- `creator-finder` — this replaced it
- HubSpot / HeyReach exports, or anything CRM-shaped

This tool researches and hands off a CSV. It does not message anyone, and it should not be wired into a sending pipeline without a human in between.
