# Creators

This is the old creator-finder job, now one scenario. Default sources: **youtube**, **tiktok**. Score mode: **engagement**.

`score = views + 10*likes + 20*comments + 5*shares` on matching hits, then rolled up per `person/{platform}/{handle}`. Compilation / “best of” / “N hours” titles are flagged and divided by 5.

Angles: `{topic}`, `{topic} tutorial` on YouTube, `{topic}` on TikTok.

**Use when:** they said creator, influencer, UGC, youtuber, tiktoker, “who posts about”.

**Do not:** default Instagram (opt-in via `--sources instagram`); default LinkedIn (no engagement, pollutes ranking); compare a TikTok score to a YouTube score across platforms in prose. The table is already per-row.

Default `--freshness month`. `year` / `all` when they said evergreen.

If they want operators who barely post, that is `people`, not this.
