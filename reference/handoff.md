# Handoff CSV

`export` writes columns:

`kind,platform,handle,id,name,url,status,novelty,score,previous_score,hit_count,views,likes,comments,shares,last_query,last_scenario,first_seen,last_seen,sample_title,sample_url,notes`

Default `--status new`. This does **not** send mail or DMs.

`import` reads the same shape. Minimum to seed skips: `kind,platform,handle,status`. `id` of the form `kind/platform/handle` is enough if kind/platform/handle columns are empty.

After they say they contacted someone: `mark kind/platform/handle --status outreached`. After they say never again: `--status skip`. After they are a customer: `--status customer`.
