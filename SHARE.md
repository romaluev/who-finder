# How to share this (you will not run it)

This folder is the product. Not the Higgsfield repo. Not `creator-finder`. Not your API key.

## What you send

1. Zip **this directory** (`who-finder/`, the one that contains `SKILL.md`).
2. Or put this directory in its own git repo and send the clone URL.
3. Send a one-line note:

> Drop this folder into `.claude/skills/who-finder` or `~/.cursor/skills/who-finder`. Set `SCRAPECREATORS_API_KEY` to your own key from https://scrapecreators.com. Ask your agent: “find people who …”, “find companies that …”, “who is hiring for …”, or “find creators posting about …”.

Do not send:

- the rest of Higgsfield
- `SCRAPECREATORS_API_KEY`
- a `make install` / pip package
- HubSpot, HeyReach, last30days, or the LinkedIn options PDF
- `creator-finder` (this folder replaced it)

## What they do

Recipient install is in [README.md](README.md). Their agent reads `SKILL.md`. Their seen-list is sqlite in **their** working directory (`.who-finder/roster.sqlite`), so two people can share a roster by committing that folder or passing `--db`.

You do not need to run a search first. If they already have a skip/customer list, they `import` a CSV; they do not need yours.
