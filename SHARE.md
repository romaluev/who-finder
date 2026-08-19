# Sharing this with your team

**who-finder** — describe who you're looking for, get back a ranked shortlist of real people with a page on each, written up as a document you can forward.

Repo: **https://github.com/romaluev/who-finder**

## The short version, for anyone

You don't run this yourself. Once it's set up with your AI assistant, you just ask in plain English:

> *"Find me the top 10 people building AI video tools and write it up as a PDF."*
> *"Who's hiring for AI video editors?"*
> *"Journalists covering generative video."*
> *"Show me ten more."*

You get back a document: a summary of what it found, then a page on each person — who they are, how to reach them (only addresses they published), what you'd miss on a first scan, and why they're worth your time. It never shows you the same name twice, and it never invents a name, a number, or an email.

## Setting it up (a few minutes, no programming)

You need two things.

**1. The skill.** Paste this into a terminal once:

```bash
git clone https://github.com/romaluev/who-finder ~/.cursor/skills/who-finder
```

(Use `~/.claude/skills/who-finder` instead if your assistant is Claude.)

**2. Your own key.** The searches are paid for with credits from a key you get at [scrapecreators.com](https://scrapecreators.com). Everyone uses their own — they're not shared. Once you have it:

```bash
export SCRAPECREATORS_API_KEY=your-key-here
```

That's it. To check it worked, this tells you in plain language whether you're ready:

```bash
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py doctor
```

**Want to see it before you get a key?** This shows exactly what a search would do and cost, without spending anything:

```bash
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py find "AI video agencies" --deep 10 --dry-run
```

## For the person rolling it out

Everything below is optional and only matters if you're coordinating a team.

**A shared seen-list stops two people emailing the same lead.** By default each person's history is their own. To share it, point everyone at one file with `--db /shared/team-roster.sqlite`, or set `WHO_FINDER_HOME` to a synced folder. Without this, "new" means new *to you*.

**A shared definition of a good fit keeps everyone consistent.** Fit scoring is a JSON file; commit one and have people pass `--icp ./team-icp.json`. Seed a skip list of existing customers first with `import known-customers.csv` so they never surface as fresh leads.

**Agents can learn the tool themselves.** `agent-context --agent` describes the whole CLI from live constants, and `which "how much will this cost"` maps a plain-English phrase to the right command — so nobody reads documentation before their first useful run.

## Don't send

- your API key
- the rest of the Higgsfield workspace
- `creator-finder` — this replaced it
- HubSpot / HeyReach exports, or anything CRM-shaped

This researches people and hands you a document. It doesn't message anyone, and it shouldn't be wired into a sending pipeline without a human in between.
