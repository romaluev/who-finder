# Contacts — public only, then compose

who-finder prints addresses and URLs that already appear on a public profile. It does not guess `jane@acme.com` from a name and a domain. That guess looks like a finding and bounces.

- [What is extracted](#what-is-extracted)
- [The `contacts` command](#the-contacts-command)
- [What is *not* extracted](#what-is-not-extracted)
- [Composing contact-goat](#composing-contact-goat)
- [Easy to miss](#easy-to-miss)

## What is extracted

From bios, headlines, snippets, published link lists, YouTube's `email` / `twitter` / `instagram` / `store` fields, LinkedIn `website` / `websites` / social keys when the vendor sends them, X profile URLs, Instagram `external_url`, TikTok bio links, and company `website`:

| kind | example | shown as |
|---|---|---|
| email | `hello@studio.com` on a YouTube channel | **How to reach them** |
| obfuscated email | `hello [at] studio [dot] com` | same, de-obfuscated |
| Calendly / cal.com | `calendly.com/jane` | **books meetings** — that is the door |
| personal site | `janedoe.com` | **Also on** |
| social | X, Instagram, GitHub, Substack… | **Also on**, labelled |
| link-in-bio | linktr.ee, bio.link | labelled as such, not a site |

`example.com`, `sentry.io`, `schema.org` and other throw-aways are dropped.

Nothing here is inferred. If the profile did not publish it, the field is omitted.

## The `contacts` command

```bash
$BIN contacts --agent
$BIN contacts --status new --band strong --limit 25 --agent
```

Zero credits. Reads the roster. The table is the list a person actually uses: name, published email, meeting link, site. The JSON carries the same plus whether `contact-goat-pp-cli` is on PATH.

`export` now adds `emails`, `website`, `calendly` columns from the same harvest, so a sheet handed to a human includes the public door.

## What is *not* extracted

- A work email built from `first.last@company.com`
- A phone number scraped from a pattern (too many false positives)
- Anything behind a LinkedIn login
- Happenstance graph, Deepline, Apollo, Hunter

Those last two are [contact-goat](https://printingpress.dev/library/sales-and-crm/contact-goat). This skill does not ship it and does not require it.

## Composing contact-goat

`doctor` reports `contact_goat.installed`. The agent may run that binary **only when**:

1. it is actually on PATH, and
2. the user asked for a work email, a warm intro, or "who do I already know there", and
3. they agreed to spend (Deepline / Happenstance API credits are not ours to burn)

Safe first call: `contact-goat-pp-cli doctor --agent`, then `dossier` or `waterfall --dry-run`. Never `waterfall` or `deepline find-email` as a surprise.

If the binary is missing, say so. Do not impersonate a lookup.

## Easy to miss

Contacts are one half of "things a ranking table hides." The other half is `notices.py` — the engine looking *across* the shortlist:

- the same name on LinkedIn and YouTube (two rows, one person)
- similar-profiles pointing at someone else in the set (a hub)
- three people listing the same employer (a cluster, not three conversations)
- a company page whose staff already appear as people
- a shared personal domain
- a city cluster of three or more
- two companies sharing an investor
- hiring *and* recently funded on the same name
- creator-shaped LinkedIn (many followers, few connections) vs operator-shaped
- a published Calendly
- a personal Gmail vs a work domain
- “former / ex- / previously” on the profile, so the company on the line may be past

Every notice cites a field. If the field is missing, the notice is omitted. They land in `results.insights.notices` and in the report under **Easy to miss**.
