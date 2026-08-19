# Your key

Searches cost credits on a [ScrapeCreators](https://scrapecreators.com) key. Everyone uses their own. Do not paste a teammate's key, and do not commit one.

## Save it once

```bash
./who-finder setup YOUR_KEY
```

That writes `~/.who-finder/key` on this machine (mode 0600). It is still there tomorrow, in a new terminal, from any folder.

`export SCRAPECREATORS_API_KEY=...` also works, and wins if both are set. The problem with `export` is it dies when the window closes — which is why `setup` exists.

If you cloned into a skills folder:

```bash
python3 ~/.cursor/skills/who-finder/scripts/who_finder.py setup YOUR_KEY
```

## Check it

```bash
./who-finder doctor
```

| it says | meaning |
|---|---|
| `READY` · `API key present (file:…)` | saved on disk, good |
| `READY` · `API key present (env)` | the shell variable is set, good |
| `NOT SET UP` | nothing on this machine |
| `KEY REJECTED` | the value is wrong or expired — get a new one |

## It worked yesterday

You used `export` in a window that is now closed. Run `setup YOUR_KEY` once.

## Forget it

```bash
./who-finder setup --clear
```

That only deletes the file. If the shell variable is still set, `doctor` will keep saying present.

## A team

Each person gets their own key at scrapecreators.com and runs `setup` on their machine. Credits are billed per key, so sharing one is how you surprise each other with an empty balance.

A shared *seen-list* (so two people do not email the same lead) is a different file — `--db /shared/team-roster.sqlite` or `WHO_FINDER_HOME`. See the [team notes](../SHARE.md).
