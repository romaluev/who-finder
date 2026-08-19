# People

Named humans who work on the topic, whether or not they post about it publicly.

**Kind:** `person` · **Sources:** `linkedin_people`, `youtube`, `x` · **Score:** presence

- [Angles](#angles)
- [When to use it](#when-to-use-it)
- [What a good result looks like](#what-a-good-result-looks-like)
- [The LinkedIn reality](#the-linkedin-reality)
- [Pitfalls](#pitfalls)

## Angles

| # | source | query | weight | why |
|---|---|---|---|---|
| 1 | linkedin_people | `site:linkedin.com/in {topic}` | 1.00 | the identity you actually want |
| 2 | linkedin_people | `site:linkedin.com/in {topic} (founder OR ceo OR "head of")` | 0.85 | seniority slice of the same index |
| 3 | youtube | `{topic}` | 0.80 | corroboration — they talk about it in public |
| 4 | youtube | `{topic} interview` | 0.55 | surfaces people others invite to speak |
| 5 | x | `site:x.com OR site:twitter.com {topic}` | 0.70 | last, because handles collide and snippets mislead |

Angles 1 and 2 overlap deliberately. A profile that appears in both is a stronger match than one that appears in either, and presence scoring rewards exactly that.

## When to use it

Founders, operators, practitioners, "who works on X", "who should we pitch", "who runs growth at companies doing Y". Also the right scenario for `people at {kind of company}` — the target is humans.

## What a good result looks like

Six to fifteen entities, most of them `person/linkedin/*`, with a handful of `person/youtube/*` corroborating the same names from a different angle. Strong bands cluster on people whose headline states the topic and whose title clears the seniority rule.

If nearly every row is `person/x/*`, the LinkedIn angles came back thin and the run is weaker than it looks — X snippets are the least reliable identity source here.

## The LinkedIn reality

Two constraints shape everything about this scenario.

**Rows come from a Google index, not from LinkedIn.** No login, no cookies, no Sales Navigator. That means no engagement data at all — the score is `10 × hit_count`, pure presence. Never present these rows as if they were ranked by influence.

**Public profiles mask job history.** LinkedIn returns asterisks for experience fields on profiles viewed anonymously. The engine detects this, falls back to the role in the Google search snippet, and tags the row `masked-profile`. That fallback is why the snippet matters: it is often the only place the job title survives.

A `masked-profile` tag is a note about provenance, not a defect. It means "this title came from the search result, not the profile."

## Pitfalls

- **Do not** rank these rows against YouTube view counts — see [scoring.md](scoring.md).
- **Do not** add TikTok. If they wanted people who post, that is [creators](creators.md).
- **Do not** treat a company page that appears in the results as a person; the identity parser keeps them distinct and so should your prose.
- **Do not** report a role you did not receive. "Role not public" is a real answer.
- **Do** run `import` first if the user already has a customer or do-not-contact list, so `new` means new.

Same human on LinkedIn and YouTube is two rows, on purpose — see [identity.md](identity.md#why-the-same-human-is-two-rows).
