# Identity

Stable id: `kind/platform/handle`.

- LinkedIn `/in/{slug}` → `person/linkedin/{slug}`
- LinkedIn `/company/{slug}` → `company/linkedin/{slug}`
- LinkedIn `/jobs/…` title `Role | Company | LinkedIn` → `company/linkedin/{company-slug}`
- YouTube `@handle` or `/channel/…` → `{kind}/youtube/{handle}` (kind follows scenario)
- TikTok `/@{handle}` → `person/tiktok/{handle}`
- X `/user` → `person/x/{handle}`
- Web fallback: person slug from title, or company from hostname

Same human on YouTube and LinkedIn is **two rows**. Do not merge in the table. CRM can join later.

`show` / `mark` accept `kind/platform/handle` or `platform/handle` (kind defaults to person).

Parser lives in `scripts/lib/identity.py`. Do not regex URLs in chat.
