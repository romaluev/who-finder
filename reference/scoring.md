# Scoring

Two modes. Never mix them in one ranking sentence.

**Engagement** (creators): `views + 10*likes + 20*comments + 5*shares` on matching hits, summed per identity. Compilation-shaped titles (`best of`, `top N`, `lofi`, `N hours`, `playlist`) get flag `compilation` and score ÷ 5.

**Presence** (people, companies, hiring, press, compare): if the source gave no engagement, score = `10 * hit_count` so repeat appearances rank above one-off Google noise.

`previous_score` on a row is the last snapshot. A jump means more matching content, not “they got famous” unless the scenario is creators.

Do not compare a YouTube creator score to a LinkedIn company score. The table is already scenario-local.
