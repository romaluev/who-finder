# Companies

Organisations with a public page — vendors, studios, agencies, brands.

**Kind:** `company` · **Sources:** `linkedin_companies`, `youtube`, `web` · **Score:** presence

- [Angles](#angles)
- [When to use it](#when-to-use-it)
- [Two identities for one company](#two-identities-for-one-company)
- [What enrichment adds](#what-enrichment-adds)
- [Pitfalls](#pitfalls)

## Angles

| # | source | query | why |
|---|---|---|---|
| 1 | linkedin_companies | `site:linkedin.com/company {topic}` | the canonical company record |
| 2 | web | `{topic} (company OR startup) -site:linkedin.com` | catches firms with no LinkedIn presence |
| 3 | youtube | `{topic}` | channels stamped `company` in this scenario |
| 4 | web | `{topic} ("about us" OR careers OR "founded")` | pages that only a real company has |

Angle 2 excludes LinkedIn deliberately so it explores a different slice rather than re-returning angle 1.

## When to use it

Vendors, studios, agencies, brands, "who sells X", "what tools exist for Y", competitive landscape work.

Not for "people at companies doing X" — that is [people](people.md). The target of that brief is humans.

## Two identities for one company

`company/linkedin/acme` and `company/web/acme.com` are separate rows and stay separate.

They come from different sources with different evidence, and merging them requires asserting that the LinkedIn slug and the hostname belong to the same organisation. That assertion is wrong often enough — subsidiaries, acquisitions, name collisions, agencies with a dozen brand sites — that a bad merge would fabricate a company profile out of two real ones.

Both rows appearing is itself a signal: the company has both a maintained LinkedIn page and a real site.

## What enrichment adds

A LinkedIn company dossier carries headcount, industry, headquarters, and funding rounds. Those feed several ICP dimensions at once:

- `audience` is a **headcount**, with `audience_kind: employees`. It shares a column with follower counts and means something entirely different — always name the unit.
- size bands become signals: `smb` (<200), `midmarket` (200–1999), `enterprise` (2000+)
- funding becomes `funded` and, when the last round is 2024 or later, `recent-round`

A company ICP typically scores heavily on these. `assets/icp.higgsfield-accounts.json` is a worked example.

## Pitfalls

- **Do not** pull `/in` profiles into this table; they are people.
- **Do not** call a YouTube compilation channel a vendor because it appeared. Require a company page or a real site before describing something as a company.
- **Do not** mix job postings in here — that is [hiring](hiring.md), which keys on the employer for a different reason.
- **Do not** read a large headcount as a good fit by default. Whether `enterprise` is a boost or a penalty is an ICP decision; the shipped Higgsfield accounts config penalises it.
