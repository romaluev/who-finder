# Sources

Auth: env `SCRAPECREATORS_API_KEY`, header `x-api-key`. Base `https://api.scrapecreators.com`. One credit per HTTP call unless the vendor says otherwise. `doctor` reads `/v1/credit-balance`.

Never fan out every source. The scenario picks the default set. `--sources` is an override, not a buffet.

LinkedIn in this skill is **Google-indexed public URLs**, not Sales Nav, not a member cookie.

## YouTube

- `GET /v1/youtube/search?query=…&includeExtras=true&uploadDate=this_month|this_year`
- Skip channel/playlist rows. Handle from channel handle. Engagement when extras land.
- Default for creators. Supporting source for people/companies/press/compare.

## TikTok

- `GET /v1/tiktok/search/keyword`
- Handle = author unique_id. play/digg/comment/share.
- Default for creators. Duplicates collapse on `person/tiktok/{handle}`.

## Instagram (opt-in)

- `GET /v2/instagram/reels/search`
- Google-indexed reels. Spaces in the query can 500; engine retries collapsed.
- Add only if they named Instagram.

## Google (LinkedIn people / companies / jobs, X, web, Reddit)

- `GET /v1/google/search?query=…&date_posted=last-month|last-year`
- The planner already put `site:` operators in the query. Do not wrap them again.
- These hits almost always have **zero** engagement. Presence score only.

## Freshness

`--freshness month|year|all` maps per source. `all` omits date filters. Creators default month. People/companies can use year when the space is small.
