# Compare

Two briefs, identical treatment, one table with a `side` column.

**Trigger:** ` vs `, ` versus `, `compare ` · **Sources:** LinkedIn people, LinkedIn companies, YouTube · **Score:** presence, per side

- [How it works](#how-it-works)
- [When to use it](#when-to-use-it)
- [Reading the result](#reading-the-result)
- [Two-way only](#two-way-only)
- [Pitfalls](#pitfalls)

## How it works

The engine splits the brief on the comparison token, strips each half independently, and runs **the same angle list** against both sides. Every step is tagged `side: a` or `side: b`.

Identical treatment is the whole design. A comparison where one side got an extra query angle or a different freshness window produces a difference that is an artifact of the search rather than of the world — and it is invisible in the output.

Cost is therefore roughly double a single-scenario run. `--dry-run` shows both sides' queries.

## When to use it

"Runway vs Pika", "compare the AI video scene in LA and Berlin", "who is bigger, X or Y" — any question whose answer is a contrast between two populations.

Not for evaluating two products on features. This compares *who shows up* around each term, which is a proxy for scene size and activity, not for product quality.

## Reading the result

The table already carries the `side` column and the per-side counts. Paste it.

If the user wants a narrative, three bullets is the right length:

- who appeared only on side A
- who appeared only on side B
- who appeared on both

That last group is usually the most interesting and the easiest to miss — people or companies active in both scenes are natural bridges, and they are the reason a comparison is worth running rather than two separate finds.

## Two-way only

`A vs B vs C` is not supported. Run two comparisons, or ask the user which pair matters.

Three-way splitting triples the cost and produces a table nobody reads, and the pairwise result is the one that answers the actual question.

## Pitfalls

- **Do not** write a verdict with section headers. There is no winner in the data — there is a count of who showed up.
- **Do not** declare a winner from YouTube views on one side and LinkedIn snippets on the other. Both sides are presence-scored precisely so the comparison is like-for-like; introducing engagement on one side breaks that.
- **Do not** read a side's lower count as inferiority. It can mean a smaller scene, a less-indexed term, or a name collision — check `source_status` for that side before drawing a conclusion.
- **Do** watch for asymmetric coverage in `GAPS`. If a source errored on one side only, the comparison is invalid and you should say so rather than reporting the counts.
