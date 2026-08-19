# People

Default sources: `linkedin_people`, `youtube`, `x`. Kind: **person**. Score mode: **presence** (Google rows have no views).

Angles the engine actually runs:

1. `site:linkedin.com/in {topic}`
2. `site:linkedin.com/in {topic} (founder OR ceo OR "head of")`
3. YouTube `{topic}`
4. YouTube `{topic} interview`
5. `site:x.com OR site:twitter.com {topic}`

LinkedIn `/in` is the identity you want. YouTube is corroboration (they talk in public). X is last because handles collide and snippets lie.

**Use when:** founders, operators, practitioners, “who works on X”, public LinkedIn people.

**Do not:** treat a company page as a person; rank these rows against YouTube view counts; add TikTok unless they said creators.

Identity is `person/linkedin/{slug}` or `person/youtube/{handle}`. Same human on two platforms is two rows. CRM merge is a later job.

If they already named a list of skip/customers, `import` first so `find` marks them known.
