# Scenarios

The engine classifies the brief, then runs that scenario's `angles`. You do not pick Google operators. You do not merge four scenarios into one crawl.

Detection order (first match wins after compare-regex): **compare → hiring → press → creators → companies → people**.

Person-words beat company-words: `people at AI video companies` is **people**. `companies building AI video` is **companies**. Bare `who is` is a people trigger; `who is hiring` is hiring because hiring is earlier in the order.

Forced override: `--scenario people|companies|creators|hiring|press|compare`. Use it when auto is wrong, not as a default.

## What each angle is for

Each scenario ships 3–5 queries. Primary source is weight 1.0. Adjacent angles are lower weight so a noisy web query cannot drown a LinkedIn `/in` hit. Compare clones the same angle list onto side `a` and side `b`.

| scenario | you are looking for | do not use it for |
|---|---|---|
| people | named humans (founders, operators, ICs) | subscriber lists, job reqs |
| companies | orgs with a public page | individual creators |
| creators | people whose **posts** match the topic | execs who never publish |
| hiring | companies with a public req | candidates |
| press | bylines and interviewers | brand social accounts |
| compare | two briefs, same sources | three-way bake-offs (split into two finds) |

Topic stripping drops filler (`find`, `me`, `please`) and scenario words (`founders`, `companies`, `hiring`). Quoted phrases are the topic verbatim: `people posting "text to video"` → `text to video`.

If the planner is wrong, pass `--sources youtube,web` or `--scenario`. Do not rewrite the queries in chat.

See also: [people.md](people.md), [companies.md](companies.md), [creators.md](creators.md), [hiring.md](hiring.md), [press.md](press.md), [compare.md](compare.md).
