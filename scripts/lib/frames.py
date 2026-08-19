"""Reframing: asking the same question several ways.

One phrasing only finds the people who describe themselves that way. Search for
`ai video ads` and you reach the people who wrote those three words in their
headline, and miss the person whose headline says `generative creative` and the
studio that says `performance video production` — even though all three are the
answer the user wanted.

Two kinds of reframing, and the split matters:

*Structural* frames are derived here. They rewrite a topic mechanically — widen
it, tighten it to an exact phrase, attach the category noun — and they work on
any subject in any language without knowing what the words mean.

*Semantic* frames are the synonyms and adjacent vocabulary of a field, and
deriving those needs to know that `text-to-video` and `generative video` name
the same thing. A lexicon good enough for one domain is dead weight in every
other, so the engine does not guess: the calling model supplies them with
`--frame`, which is exactly the knowledge it has and the engine does not.

Cost is why frames are not simply multiplied across every angle. The literal
frame runs the full angle set; each extra frame runs only the primary angle. So
three frames on a five-angle scenario is seven searches, not fifteen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words that carry no search value on their own, so a frame that reduces to one
# of these is dropped rather than run.
THIN = frozenset({
    "ai", "the", "new", "best", "top", "tool", "tools", "app", "apps", "tech",
    "video", "data", "digital", "online", "software", "platform", "content",
})

CATEGORY_NOUN = {
    "people": "",
    "creators": "",
    "companies": "company OR startup OR studio",
    "hiring": "hiring OR careers",
    "press": "journalist OR writer",
    "compare": "",
}


@dataclass
class Frame:
    label: str
    topic: str
    why: str
    weight: float = 1.0

    def as_dict(self) -> dict:
        return {"label": self.label, "topic": self.topic, "why": self.why, "weight": self.weight}


def _words(topic: str) -> list[str]:
    return [w for w in re.split(r"\s+", (topic or "").strip()) if w]


def broaden(topic: str) -> str:
    """Drop the leading modifier: `ai video ads` -> `video ads`.

    Reaches people working on the thing who never label it with the buzzword,
    which on emerging topics is most of the experienced ones.
    """
    w = _words(topic)
    return " ".join(w[1:]) if len(w) >= 3 else ""


def tighten(topic: str) -> str:
    """Quote the phrase so the index stops matching the words separately."""
    return f'"{topic}"' if len(_words(topic)) >= 2 else ""


def structural(topic: str, scenario: str) -> list[Frame]:
    out = [Frame("literal", topic, "the topic exactly as asked", 1.0)]

    exact = tighten(topic)
    if exact:
        out.append(Frame("exact", exact,
                         "as one phrase, so the words are not matched separately", 0.9))

    wide = broaden(topic)
    if wide and wide.lower() not in THIN and len(_words(wide)) >= 2:
        out.append(Frame("broad", wide,
                         "without the leading qualifier, to reach people who do the work "
                         "but do not use that label", 0.75))

    noun = CATEGORY_NOUN.get(scenario) or ""
    if noun:
        out.append(Frame("category", f"{topic} ({noun})",
                         f"paired with what we are looking for, to filter out coverage "
                         f"about the topic", 0.8))
    return out


def derive(topic: str, scenario: str, *, extra: list[str] | None = None,
           limit: int = 4) -> list[Frame]:
    """Structural frames first, then whatever the caller knows to add."""
    frames = structural(topic, scenario)
    for raw in extra or []:
        text = (raw or "").strip()
        if not text:
            continue
        frames.append(Frame("given", text, "supplied by the caller as another way to say it", 0.85))

    seen, out = set(), []
    for f in frames:
        # Quotes are part of the key: `ai video` and `"ai video"` are different
        # queries against an index, and collapsing them loses the precise one.
        key = f.topic.strip().lower()
        if not key or key in seen or key.strip('"') in THIN:
            continue
        seen.add(key)
        out.append(f)
        if len(out) >= max(1, limit):
            break
    return out
