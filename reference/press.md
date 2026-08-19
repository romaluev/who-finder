# Press

Journalists, hosts, and interviewers who cover the topic.

**Kind:** `person` · **Sources:** `web`, `youtube` · **Score:** presence

- [Angles](#angles)
- [When to use it](#when-to-use-it)
- [The noisiest scenario](#the-noisiest-scenario)
- [Pitfalls](#pitfalls)

## Angles

| # | source | query | why |
|---|---|---|---|
| 1 | web | `{topic} (journalist OR reporter OR "staff writer" OR byline)` | role words near the topic |
| 2 | web | `{topic} (interview OR "talks to" OR "spoke with")` | interviewers, who are often the better contact |
| 3 | youtube | `{topic} interview` | podcast and video hosts |
| 4 | web | `site:substack.com {topic}` | independent writers, increasingly where the beat lives |

Angle 4 matters more than it used to. A large share of specialist coverage has moved to independent newsletters, and those writers are usually more reachable than staff reporters.

## When to use it

Journalists, reporters, press, coverage, media, podcast hosts, "who writes about X", "who should we pitch this story to".

## The noisiest scenario

Press has the weakest identity signal of the six, because a byline is not a URL pattern.

Web fallback identity is `person/web/{name-slug}` derived from the page title, and page titles are inconsistent — some carry the author, many carry only the headline and the outlet. Expect a lower share of clean identities here than in [people](people.md), and expect more rows that need a human glance.

Prefer rows where the URL is an author page rather than an article: those parse reliably and are the actual person. A row whose evidence is a single article is a weaker lead than one that appeared across several.

Enrichment helps less here too. There is no journalist profile endpoint, so most press rows stay at `MAYBE` or `?` unless they also have a YouTube presence. That is honest — do not upgrade them in prose.

## Pitfalls

- **Do not** dump outlet homepages as people. `person/web/techcrunch-com` is a parsing artifact, not a journalist.
- **Do not** treat a brand's YouTube channel as a reporter.
- **Do not** mix this ranking with creator engagement. A journalist's value is their beat and their readership, not their view count.
- **Do** run with `--freshness year` when the topic is niche. A month of coverage in a small space is often two articles.
