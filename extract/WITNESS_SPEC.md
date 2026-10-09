# Witness spec — how each person knew Randy Weston

Project root: `/Users/m/git/weston-centennial`

A centennial web page about **Randy Weston** (pianist, composer, bandleader;
Brooklyn, 1926–2018) will show, for each person who spoke about him in an
oral-history interview, one row: *who they are — how they knew him — their best
line*.

An earlier pass judged individual transcript blocks. Your job is the step from
blocks to **people**: for each witness, read everything they said about him and
decide what their relation to him actually was, which line should lead, and the
short phrase that says how they knew him.

## Input — `weston/witness_input.json`

`items[]`, one per witness. A witness is one interview document:

```
witness_key          copy it through
doc                  the interview: title, collection, year, interviewee, interviewer
interviewees[]       who was interviewed (label, qid, description, dates)
liston_build         present only for Melba Liston (see below)
upstream_relations[] what an earlier, weaker model decided -- a lead, NOT a finding.
                     Often "knows of", often inferred from the INTERVIEWER's words.
                     Empty for witnesses that model never saw.
blocks[]             every block judged to be about him, in reading order:
    block_id, kind (mention | recovered_answer | recovered_continuation | liston_build_quote)
    speaker, speaker_role (interviewee | interviewer | unknown | null)
    mention_kind, notable, stance, summary, pull_quote, notes   <- the block-level judgement
    context_before[]   up to 4 preceding turns
    text               THE block
    context_after[]    up to 4 following turns
```

Read every block of a witness, with its context, before judging that witness.

**Melba Liston** is a special witness. She was his arranger for forty years and
is the largest single source (her 1996 Smithsonian interview). Three things:

- Her interviewer, speaker `Bryant`, is the trumpeter Clora Bryant, who knows the
  story and often tells it; Liston answers "Yeah." Bryant's lines are the
  interviewer's — never quote them as the witness's. Liston had a stroke in
  1985: her own sentences are short, plain and exact, and that is the voice.
- **Long square-bracketed passages in her transcript are the transcriber's
  summaries, not speech.** Never quote them.
- Her bundle carries `liston_build`: the record that the readers of her *whole*
  interview wrote for Weston in the Liston centennial build — relation, summary,
  her best quote and four more. The blocks those quotes come from have been
  added to `blocks[]` as `kind: "liston_build_quote"` (they do not name him; he
  is "he" or "Randy" a turn earlier). Treat it as a strong lead: you may choose
  those lines or better ones, but your quotes must be exact substrings of a
  block in this bundle like anyone else's.

**Several people were interviewed twice** (Benny Powell, Jimmy Owens, Ron
Carter, Orrin Keepnews — once for Hamilton College, once for the Smithsonian or
a second Hamilton session). Each interview is its own witness item; judge each
on its own blocks. Do not carry a fact from one interview into the other's
`one_liner`.

**Not every witness is a musician.** Orrin Keepnews produced his first records;
Dan Morgenstern is a critic; Wendy Oxenhorn runs a foundation. Judge the
relation from what they say, with the same vocabulary.

## Output — `weston/witness_output.json`

```json
{"subject": "weston", "count": <n>, "items": [ ...one per input item, same order... ]}
```

Each item (values below are invented, to show shape):

```json
{
 "witness_key": "123456",
 "speaker_name": "Jane Example",
 "speaker_qid": "Q1",
 "spoke_themselves": true,
 "relation": "in music group with",
 "direction": "mutual",
 "contact_level": "worked_together",
 "basis": ["direct_contact"],
 "context": "his sextet, 1980s–90s",
 "one_liner": "played in his band for fifteen years",
 "summary": "Example recalled touring with Weston's band and said he could turn any room into a ceremony.",
 "lead_block_id": 200001,
 "lead_quote": "exact contiguous substring of that block's text",
 "second_block_id": 200009,
 "second_quote": "exact contiguous substring, or null",
 "stance": "positive",
 "stance_strength": 2,
 "notable": 2,
 "upstream_relation_ok": false,
 "caution": "",
 "confidence": "high",
 "notes": ""
}
```

### Field definitions

**`speaker_name`** / **`speaker_qid`** — who is actually talking about him. For a
single-interviewee document this is that interviewee (copy `label` and `qid`;
fix an obviously inverted or upper-cased name). For a joint interview, decide
from the blocks' speakers which interviewee speaks of him; if it is not determinable, say so in
`notes` and use the document's first interviewee. `speaker_qid` is `null` when
the input gives none — **never invent a QID**.

**`spoke_themselves`** (bool) — did the witness say anything about him in their
**own** words? `false` when he appears only in the interviewer's question, an
editor's bracket, or the archive's front matter, and the witness merely assents
("Yeah.") or says nothing. A `false` here means the witness is not really a
witness; set `relation` from what little is established (often `knows of` or
`none`), `notable: 0` or `1`, and `lead_quote: null` unless the interviewer's
line plus the assent is itself worth showing (then quote the witness's own
words only).

**`relation`** — the witness's relation to Weston. One of:
`in music group with` · `collaborated with` · `played with` · `toured with` ·
`played under` · `mentor of` · `influenced by` · `friend of` · `acquaintance of`
· `has met` · `knows of` · `none`.

Pick the **strongest relation the testimony actually supports**. Do not use
outside biographical knowledge to upgrade: Melba Liston's forty-year partnership
with him is `collaborated with` because *she describes it*, not because it is
famous. If the witness only saw him play, that is `knows of`. A claim of contact
needs the witness to state contact. A sideman in his band is `in music group
with` (or `played under` with `direction: weston_leads` when the witness frames
him as the boss); a producer who recorded him is `collaborated with`.

**`direction`** — for `played under`, `mentor of`, `influenced by`:
`weston_leads` (he was the leader / teacher / influence) or `witness_leads` (the
witness was). Otherwise `mutual`, or `na` for `knows of` / `none`.

**`contact_level`** — `worked_together` | `knew_personally` | `met_briefly` |
`same_scene` | `no_contact` | `unclear`.

**`basis`** — how the witness knows of him at all; every one that applies:
`direct_contact`, `saw_live`, `recordings`, `reputation`, `press_or_study`,
`shared_associates`, `none_evident`.

**`context`** — the band, record, place or period the connection belongs to, **as
the testimony gives it** ("his sextet, Morocco, 1980s–90s"), or `""`.

**`one_liner`** — the caption phrase: **3 to 8 words, lower case, no final
period**, starting with a verb or preposition, referring to Weston as "him" /
"he" / "his", never by name. Rules, the first absolute:
1. Use ONLY facts stated in this witness's blocks. No place, band, club, record,
   instrument, year or person may appear unless the testimony contains it. A dull
   true phrase beats a vivid invented one.
2. Do NOT restate the relation label — the page prints it beside the phrase.
   Bad: "was a friend of his". Good: "went to morocco with his band" (if that
   is what was said).
3. If nothing specific is supported, return `""`.

**`summary`** — ONE sentence, past tense, naming the witness by surname: the gist
of everything they said about him.

**`lead_block_id`** / **`lead_quote`** — the single best thing this witness said
about him, for display beside their name. `lead_quote` MUST be an exact,
contiguous substring of the `text` of the block `lead_block_id` (one of this
witness's `blocks[]`), and must be the **witness's own words** — not the
interviewer's, and not a bracketed editorial insertion standing alone. You may
improve on the block-level `pull_quote` (shorter, cleaner, a better sentence) as
long as it stays an exact substring. `null` / `null` if the witness said nothing
quotable.

**`second_block_id`** / **`second_quote`** — a second, different line worth
showing, same rules, from a different sentence (same or another block). `null`
if none.

**`stance`** — `positive` | `negative` | `mixed` | `neutral` — the witness's
attitude to Weston across all their blocks. **`stance_strength`** 0–3.

**`notable`** 0–3 — how good is this witness's row for the page, taken as a
whole? `3` = a first-hand witness with a line you would print large (**at most
6**). `2` = a real connection and a usable quote. `1` = thin but genuine. `0` =
nothing usable / not really a witness.

**`upstream_relation_ok`** (bool or null) — was the earlier model's relation
right? `null` when `upstream_relations` is empty.

**`caution`** — anything that should stop a line being displayed unqualified: a
factual claim that is probably wrong (say what and why you doubt it), a quote
that reads misleadingly out of context, a remark set inside a passage a reader
could find offensive, an uncertain identification (e.g. a name the transcript
garbles, "Randy Western"), a line whose "he" a cold reader would take for
someone else. `""` if none. This field is read by a human before publication.

**`confidence`** — `high` | `medium` | `low`. **`notes`** — anything else.

## Rules

- **Never invent text.** Quotes are exact substrings of one block's `text`.
- **Only the testimony decides.** Outside knowledge may be used to recognise a
  name, a band or a record and to fix the spelling of the witness's own name —
  never to supply a fact about the relationship.
- Do not fix or tidy transcript text inside a quote.
- Exactly one output item per input item, same order, `witness_key` copied.
- Output valid JSON, UTF-8, `ensure_ascii=False`, written with a short Python
  script run via `uv run --python 3.14 python <script>`. Helper scripts go in
  the scratchpad directory you were given. Write nothing inside the project
  except `weston/witness_output.json`. Do not run git commands.
- **Write incrementally** — rewrite the output file after every 8 witnesses, and
  resume from an existing file if there is one.
- No quote may overlap a `[...]` span longer than 25 characters (the Liston
  transcriber's summaries).
- **Validate before finishing**: output parses; count and `witness_key` order
  match the input; every non-null `lead_quote` / `second_quote` is an exact
  substring of the `text` of the named block, and that block belongs to that
  witness; every `one_liner` is ≤ 8 words, lower case, with no final period;
  `relation`, `direction`, `contact_level`, `basis` use only the allowed values;
  at most 6 items have `notable == 3`.
