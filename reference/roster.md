# Roster

SQLite at `<cwd>/.who-finder/roster.sqlite` unless `WHO_FINDER_HOME` or `--db`.

Statuses: `new | watched | outreached | skip | customer`.

**new** = first insert, and it stays new until someone marks another status. Re-finding a still-new row is still the outreach queue (`novelty=new`). Re-finding after skip/outreached/customer/watched is `novelty=known`.

Lead the user with **new**. Known rows prove the seen-list works; they are not the headline.

`import` a CSV of skip/customer **before** the first find when they already have a list. Example: `assets/handoff.example.csv`.

Do not put the roster in `~/.hf-creators` or mix HubSpot ids into this file.
