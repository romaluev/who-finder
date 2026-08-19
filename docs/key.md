# Your keys

You can run `find` with no key. That is the thinner path: public search (DuckDuckGo, Hacker News), snippet-only cards, fit capped at MAYBE.

A [ScrapeCreators](https://scrapecreators.com) key unlocks real Google, YouTube, TikTok, Instagram, and **profile enrich**. Everyone uses their own. Do not paste a teammate's key, and do not commit one.

An optional [Brave Search](https://brave.com/search/api/) key is a better web floor than DuckDuckGo and spends **zero** ScrapeCreators credits.

## Save it once

```bash
./who-finder setup YOUR_KEY
```

That writes `~/.who-finder/key` on this machine (mode 0600). It is still there tomorrow, in a new terminal, from any folder.

Optional Brave:

```bash
./who-finder setup --brave YOUR_BRAVE_KEY
```

`export SCRAPECREATORS_API_KEY=...` and `export BRAVE_API_KEY=...` also work, and win if both file and env are set. The problem with `export` is it dies when the window closes — which is why `setup` exists.

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
| `READY` · ScrapeCreators present | full path |
| `READY` · thinner path | no paid key; `find` still runs |
| `KEY REJECTED` | the ScrapeCreators value is wrong — thin path still works |
| `Brave present` | optional web backend is on |

## It worked yesterday

You used `export` in a window that is now closed. Run `setup YOUR_KEY` once.

## Forget it

```bash
./who-finder setup --clear
./who-finder setup --clear --brave
```

That only deletes the file. If the shell variable is still set, `doctor` will keep saying present.

## A team

Each person gets their own ScrapeCreators key and runs `setup` on their machine. Credits are billed per key, so sharing one is how you surprise each other with an empty balance.

A shared *seen-list* (so two people do not email the same lead) is a different file — `--db /shared/team-roster.sqlite` or `WHO_FINDER_HOME`. See the [team notes](../SHARE.md).
