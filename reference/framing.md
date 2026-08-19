# Framing

One phrasing only finds the people who describe themselves that way.

Search `ai video ads` and you reach the people who put those three words in their headline. You miss the person whose headline says `generative creative`, the studio that says `performance video production`, and the director who says nothing about AI at all because they have been doing the work since before the label existed. All three are the answer the user wanted.

Framing asks the same question several ways. It is different from angles: an **angle** varies the lens (a role filter, a different platform, an interview search), while a **frame** varies the words for the thing itself.

## Structural frames, derived by the engine

These rewrite the topic mechanically, so they work on any subject in any language without knowing what the words mean.

| frame | `ai video ads` becomes | why |
|---|---|---|
| `literal` | `ai video ads` | the topic as asked |
| `exact` | `"ai video ads"` | one phrase, so the index stops matching the words separately |
| `broad` | `video ads` | drops the leading qualifier, reaching people who do the work without using the label |
| `category` | `ai video ads (company OR startup OR studio)` | pairs the topic with what is being looked for, filtering out coverage *about* the topic |

`broad` is the one that earns its credit most often. On an emerging topic the buzzword is adopted last by the people with the deepest experience, so dropping it surfaces exactly the names a literal search cannot reach.

Frames that collapse to something unsearchable are dropped rather than run: broadening a two-word topic leaves one word, and a frame that reduces to a filler term like `ai` or `tools` would return noise for a credit.

## Semantic frames, supplied by the caller

Structural rewrites cannot know that `text-to-video` and `generative video` name the same thing. That needs the vocabulary of a field, and a lexicon good enough for one domain is dead weight in every other — so the engine does not guess.

```bash
who-finder find "people building text-to-video tools" \
  --frame "generative video" \
  --frame "AI film production"
```

A model calling this tool has exactly the knowledge the engine lacks, which is why `--frame` exists. Good frames are:

- **A different vocabulary, not a different filter.** `--frame "founders of generative video"` wastes the frame on role targeting the angles already do. `--frame "generative video"` is the useful half.
- **Terms a practitioner would write about themselves.** Not a description of them, but the words they would use in their own headline.
- **Real.** A frame for a term nobody uses costs a credit and returns noise.
- **Not a paraphrase of the brief.** If it overlaps the literal frame, it finds the same people twice.

## What it costs

Crossing every frame with every angle would multiply the bill for steeply diminishing returns, so the literal frame runs the full angle set and each additional frame runs only the primary angle.

Three frames on a five-angle scenario is **seven searches, not fifteen**. `--frames N` caps the total (default 3); `--frames 1` turns reframing off. `--dry-run` prints the exact queries and the ceiling before anything is spent.

## What it produces

Every hit records the query that found it. In a report that becomes two things:

**"Found by"** on each person, listing the phrasings that surfaced them — so you can tell someone central to the topic from someone who appeared on one narrow query.

**"Corroboration"**, when more than one framing found the same person. Independent phrasings converging is evidence the fit score cannot see, because the score reads the profile and knows nothing about how it was reached.

The roster keys hits by URL, so a person found by three framings leaves only the last one on disk. Live runs report all of them; reports rebuilt later from the roster show the last recorded query.
