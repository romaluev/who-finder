# Companies

Default sources: `linkedin_companies`, `youtube`, `web`. Kind: **company**. Score mode: presence.

Angles:

1. `site:linkedin.com/company {topic}`
2. `{topic} (company OR startup) -site:linkedin.com`
3. YouTube `{topic}` (channel stamped company when the scenario is companies)
4. `{topic} ("about us" OR careers OR "founded")`

**Use when:** vendors, studios, agencies, brands, “who sells X”.

**Do not:** pull `/in` profiles into this table; call a YouTube compilation channel a vendor without a company page; mix hiring reqs here (that is `hiring`).

A LinkedIn company slug and a web hostname are different identities (`company/linkedin/acme` vs `company/web/acme`). That is intentional — do not collapse them in the table.
