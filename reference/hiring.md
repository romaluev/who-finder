# Hiring

Kind: **company**. Sources: `linkedin_jobs`, `web`. Score: presence (a job card is a signal, not a view count).

Angles:

1. `site:linkedin.com/jobs {topic}`
2. `{topic} (hiring OR "open role" OR careers)`
3. `site:greenhouse.io OR site:lever.co OR site:ashbyhq.com {topic}`

The identity is the **company**, not the job. LinkedIn job titles like `AI Video Editor | Higgsfield | LinkedIn` parse to `company/linkedin/higgsfield`. That is how you de-dupe ten reqs from one org.

**Use when:** hiring, jobs, open roles, recruiting, headcount, careers.

**Do not:** scrape a logged-in ATS; treat this as a candidate search; log into LinkedIn.

Public index only. If Google has not indexed the req, it will not appear. That is a coverage limit, not a bug.
