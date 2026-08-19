# Hiring

Companies with a public open role. A req is a buying signal: someone has budget and an unmet need.

**Kind:** `company` · **Sources:** `linkedin_jobs`, `web` · **Score:** presence

- [Angles](#angles)
- [Why the identity is the company](#why-the-identity-is-the-company)
- [When to use it](#when-to-use-it)
- [Coverage limits](#coverage-limits)
- [Pitfalls](#pitfalls)

## Angles

| # | source | query | why |
|---|---|---|---|
| 1 | linkedin_jobs | `site:linkedin.com/jobs {topic}` | the largest indexed pool |
| 2 | web | `{topic} (hiring OR "open role" OR careers)` | company career pages |
| 3 | web | `site:greenhouse.io OR site:lever.co OR site:ashbyhq.com {topic}` | ATS boards, where the req is canonical |

Angle 3 is the highest-quality of the three: a Greenhouse posting is a live req at a company that runs a real hiring process.

## Why the identity is the company

A LinkedIn job page titled `AI Video Editor | Higgsfield | LinkedIn` resolves to `company/linkedin/higgsfield`, not to the posting.

Ten open roles at one studio are one prospect, not ten. Keying on the employer collapses them into a single row whose `hit_count` of 10 is itself the signal — that company is hiring hard in your topic, which is far more interesting than any individual req.

If the user wants the specific roles rather than the employers, the individual postings are still stored as hits and `show <identity>` lists them.

## When to use it

"Who is hiring for X", "which companies are staffing up on Y", "open roles in Z", recruiting-signal prospecting, and territory research where hiring indicates investment.

The `hiring` **signal** is different from the `hiring` **scenario**. Any scenario can tag a row `hiring` when the profile or recent posts mention open roles; this scenario searches job postings specifically.

## Coverage limits

Public index only. If Google has not indexed a req, it does not appear. Freshly posted roles and roles on obscure ATS platforms are systematically under-represented, and companies that hire only through recruiters are invisible.

That is a coverage limit, not a bug — but it means a company's absence here is weak evidence. Say "no indexed public reqs" rather than "not hiring".

## Pitfalls

- **Do not** scrape a logged-in ATS or LinkedIn. Public index only, always.
- **Do not** treat this as a candidate search. It finds employers, not applicants, and this tool has no candidate scenario by design.
- **Do not** report a hit count as a number of open roles. It is the number of indexed postings that matched your topic, which is a subset.
- **Do** pair it with [companies](companies.md) when the user wants both "who exists" and "who is investing".
