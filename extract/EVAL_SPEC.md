# Evaluation spec — classifying what was said about Randy Weston

You are judging **what a jazz musician actually said** about **Randy Weston**
(pianist, composer, bandleader; Brooklyn, 6 April 1926 – 1 September 2018) in an
oral-history interview, for a centennial web page.

*(Ported from the Melba Liston centennial build, itself ported from the
Coltrane / Davis one. The method is the same; the traps are his.)*

Project root: `/Users/m/git/weston-centennial`

## Your input

One chunk file: `weston/eval_input/chunk_NNN.json`.
Each item is one transcript block that mentions the subject, wrapped in an
expanded window:

```
context_before[]  ~4-8 preceding blocks (~1200-4000 chars)
target            THE block that mentions the subject
context_after[]   2-4 blocks, or 6-8 when the interviewer is speaking
doc               title, collection, year, interviewee(s), interviewer, deep link
subject_surface_forms      the name variants this interview used for the subject
speaker_role               interviewee | interviewer | unknown (pre-computed, imperfect)
target_starts_midsentence  target begins lowercase — it is a page-break continuation
target_ends_midsentence    target has no terminal punctuation — it continues below
mention_source             person_layer | fts_supplement (see trap 1)
```

**Read the whole window before judging.** The single most common failure is
reading `target` alone.

Every item is from **somebody else's** interview. Weston's own oral history
(Smithsonian, 2009) is read by a different pass and is not in your chunk. There
are only 84 of these blocks in the entire 1,347-interview corpus, from 22
interviews, so each one matters. Be exact.

## The Melba Liston interview (26 of the 84 blocks)

`doc_id: Liston_Melba_Interview_Transcription` is the largest single source.
Melba Liston (1926–1999), trombonist and arranger, wrote the arrangements for
Weston's records for forty years. Three things about that document:

- **The interviewee is `Liston`; the interviewer is `Bryant`** — Clora Bryant, a
  trumpeter and friend of hers. Bryant knows the story and often *tells* it;
  Liston answers "Yeah." Bryant is still the interviewer: a block where Bryant
  raises Weston is `interviewer_question` (capped at `notable: 1`), and you
  summarize Liston's **answer**.
- **Liston had a stroke in 1985**, eleven years before the interview. Her turns
  are short. When she does say a full sentence about Weston it is plain and
  exact — do not pass over a line because it is short.
- **Square brackets there are the transcriber, not the speaker.** Long ones are
  summaries of stretches she could not manage (*"[Liston cannot recall what
  happened next.]"*); short ones are name expansions (*"Randy [Weston]"*). A
  block whose only mention of him is inside a long bracketed summary is
  `transcriber_summary` (`notable: 0`, no `pull_quote`). **Never put a long
  bracketed summary in a `pull_quote`.**

## Known traps

1. **`mention_source: "fts_supplement"` means identity is UNVERIFIED.** A text
   search added the few blocks the name-matching missed: **"Randy Western"** (a
   transcriber's mishearing), **"Randy [Weston]"**, and a bare **"Randy"** in an
   interview that names him in full elsewhere. Decide from the window whether
   each is really him, using only what the window gives you (who else is named,
   the band, the instrument, the era). Say how sure you are in `confidence`. If
   you cannot tell, `is_about_subject: false`, `confidence: "low"`, and explain.
2. **Other Westons and other Randys exist in this corpus**: arranger and
   bandleader **Paul Weston**, the New York club **Jimmy Weston's**, bassist
   **Fitz Weston**, singer **Kim Weston**; trumpeters **Randy Brecker**, **Randy
   Brooks** and **Randy Sandke**, songwriter **Randy Newman**, singer **Randy
   Crawford**. Any of these is a `false_positive`.
3. **The editor supplied the name, not the speaker.** Smithsonian transcripts
   expand a bare first name as *"Randy [Weston]"*. The block is still about him
   (`is_about_subject: true`), but note that the name is editorial — and a
   `pull_quote` containing the bracketed insertion is fine only if it is an
   exact substring.
4. **Interviewer prompts answered with "Yeah."** When the interviewer raises
   him (*"You worked with Randy Weston for a long time…"*) that is
   `interviewer_question`; summarize the **answer** found in `context_after` and
   say in `notes` whether the interviewee added anything of their own.
5. **Page-break splits invert meaning.** When `target_ends_midsentence` or
   `target_starts_midsentence` is true, the adjacent block is **mandatory**
   reading.
6. **Pronouns flip inside a block.** "He" after a Weston mention can become
   Thelonious Monk, Duke Ellington, Dizzy Gillespie, Max Roach, Booker Ervin or
   the speaker's own bandleader within a sentence. Check antecedents inside the
   target, not just before.
7. **Lists.** He is very often one name in a roll-call — of pianists (*"Monk,
   Randy Weston, Herbie Nichols"*), of Brooklyn musicians, of Riverside artists,
   of leaders someone worked for. That is `list_item` unless the speaker goes on
   to say something about him.
8. **Speaker mis-segmentation.** `speaker_role` is a heuristic and is sometimes
   wrong — trust the text over the label. Hamilton transcripts label speakers by
   initials (`BP` = Benny Powell, `MR` = the interviewer Monk Rowe); a blank
   speaker is usually a page-break continuation of the previous voice.
9. **His tunes travel without him.** *Hi-Fly*, *Little Niles*, *Berkshire
   Blues*, *Pam's Waltz*, *Babe's Blues*. A block that is about one of his
   compositions — someone recorded it, wrote lyrics to it, arranged it — IS
   about him (`is_about_subject: true`, `content_type` includes `composition`),
   even if he is named only as its composer. A block that merely lists the tune
   among others is `passing_reference` or `list_item`.
10. **Archive apparatus is ingested as speech**: front-matter biographies,
    transcriber's notes, rights statements, back-matter indexes.
    `archive_boilerplate`, `notable: 0`.

## Your output

Write `weston/eval_output/chunk_NNN.json`:

```json
{"subject": "weston", "chunk": N, "count": <n>,
 "chunk_top": [<block_id>, <block_id>, <block_id>],
 "items": [ ... ]}
```

One record per input item, **in the same order, one per input item, no drops**
(the values below show shape only):

```json
{
 "block_id": 272159,
 "is_about_subject": true,
 "mention_kind": "substantive_comment",
 "quotes_the_subject": false,
 "stance": "positive",
 "stance_strength": 2,
 "stance_target": "subject",
 "content_type": ["personal_memory", "working_relationship"],
 "relationship": "personally",
 "block_is_firsthand": true,
 "topics": ["Morocco", "African Rhythms sextet"],
 "summary": "Powell recalled going to Morocco with Weston and said the years in his band had been glorious.",
 "pull_quote": "an exact contiguous substring of target.text",
 "notable": 2,
 "context_changed_reading": true,
 "truncated_target": false,
 "confidence": "high",
 "notes": ""
}
```

### Field definitions

**`is_about_subject`** (bool) — does this block actually concern Randy Weston?
False for the trap cases above. If false, set `mention_kind: "false_positive"`,
`stance: null`, `stance_strength: 0`, `content_type: []`, `summary: ""`,
`pull_quote: null`, `notable: 0`, and explain in `notes` who it is really about.

**`mention_kind`** — exactly one of:
- `substantive_comment` — the speaker says something of substance about him
- `quoted_speech` — the block reports words **Weston himself said** (prefer this
  over `substantive_comment` when the block's value is his own words)
- `passing_reference` — named in passing, no real content
- `list_item` — one name in a list of names
- `interviewer_question` — the *interviewer* raises him; the answer is usually
  in `context_after` — summarize the **answer** and say so in `notes`
- `third_party_topic` — the block is about two *other* people, he is incidental
- `archive_boilerplate` — not interview speech at all (headers, front matter,
  indexes, rights statements, transcriber's notes outside a turn)
- `transcriber_summary` — the mention is only inside a transcriber's long
  square-bracketed summary (the Liston interview)
- `false_positive` — not actually about him

**`quotes_the_subject`** (bool) — does the block contain reported speech by
Weston? Can be true alongside any `mention_kind`.

**`stance`** — `positive` | `negative` | `mixed` | `neutral` | `null`.
Neutral = factual/biographical, no evaluative content. Do not inflate:
admiration is common in this corpus, but so is frank criticism and praise that
carries a reservation, and "mixed" is the honest answer more often than people
expect. Judge the *speaker's* attitude, not his reputation.

For `interviewer_question` items, score the **interviewer's own framing** if it
carries an attitude, else neutral. Such items may never exceed `notable: 1`.

**`stance_target`** — `subject` | `associates`. Stance is always scored toward
*Weston himself*. Use `associates` when the judgement really lands on the band,
the record label, the arranger or the scene he was with rather than on him.

**`stance_strength`** 0–3 — 0 none, 1 mild, 2 clear, 3 emphatic.

**`content_type`** — one or more of: `personal_memory`, `anecdote`,
`musical_assessment` (his playing, his sound, his time), `composition` (his
tunes and writing), `bandleading` (what it was like to work for him),
`africa` (Morocco, Tangier, the Gnawa, Nigeria, his African project generally),
`influence`, `legacy_influence`, `mentorship`, `biographical_fact`, `hearsay`,
`comparison` (to Monk, Ellington or anyone else), `character_description`,
`working_relationship`, `business` (labels, contracts, clubs, money), `humor`,
`criticism`, `historical_context`.

**`relationship`** — the speaker's relation to him, judged from the whole window
and **kept consistent across every item from the same interview**:
`personally` (played with / met / knew him), `secondhand` (knows of him, heard
stories), `unclear`, `not_applicable` (a neutral interviewer or a false
positive). If any block in the window shows first-person contact, use
`personally` throughout that document. Do not use outside biographical knowledge.

**`block_is_firsthand`** (bool) — does *this specific block* report the speaker's
own direct experience of him (vs. general opinion or hearsay)?

**`topics`** — 0–4 short free-text tags (bands, venues, records, tunes, places).

**`summary`** — ONE sentence, past tense, naming the speaker by surname: what
they say about him. For `interviewer_question`, summarize the answer. Empty
string for false positives and boilerplate.

**`pull_quote`** — the best display sentence(s) for a web page. It **MUST be an
exact, contiguous substring of `target.text`** — no ellipsis, no reordering, no
case changes, no splicing across blocks. Trim to a sentence boundary; if no clean
boundary exists, quote the fragment and note it. `null` if nothing is quotable.
This is validated programmatically; a non-substring is a hard failure.

**`notable`** 0–3 — how good is this for the page?
- `3` = a sentence you would set in 24pt type under a photograph: vivid,
  specific, about him, needs no setup. **Hard quota: at most 5 items per chunk.**
- `2` = solid, usable with a little context
- `1` = minor
- `0` = unusable
Be a harsh grader. Most items are 0–1.

**`chunk_top`** (top-level) — the `block_id`s of the 3 best items in your chunk,
best first.

**`context_changed_reading`** (bool) — true if the expanded context changed how
you read the target block versus reading it alone. Be honest.

**`truncated_target`** (bool) — the target block begins or ends mid-sentence at a
page break. (The input pre-flags this; correct it if the flag is wrong.)

**`confidence`** — `high` | `medium` | `low` for your own judgement.

**`notes`** — short free text, or `""`. Ambiguous pronouns, speaker
mis-segmentation, an editorially inserted name, suspected metadata errors, a
conflict with another item, a good line about him that sits in a neighbouring
block rather than the target — anything a human should check.

## Write incrementally — this is mandatory

1. **Before you start**, check whether your output file already exists. If it
   does, read it, count the valid records, and resume from the next item.
2. **Write after every 15 items.** Rewrite the whole output file each time with
   everything finished so far (`count` = records actually written).
3. Only the final write needs to satisfy the full-count validation.

## Rules

- **Never invent text.** Every `pull_quote` must appear verbatim in `target.text`.
- **Don't use outside knowledge** to decide what someone said — only the window.
  Outside knowledge is fine for recognizing a name or a record title.
- Do not fix, clean, or improve transcript text. Quote around ASR/OCR errors or
  leave the item unquotable.
- If a window is garbled, say so in `notes` and lower `confidence`.
- Output valid JSON, UTF-8, `ensure_ascii=False`. Write it with a short Python
  script run via `uv run --python 3.14 python <script>` — do not print records to
  the terminal.
- **Other agents run concurrently.** Any helper script you write MUST live in
  the scratchpad directory you were given and carry your chunk number in its
  filename. Write to no path in the project other than your own output chunk.
  Do not run git commands.
- Exactly as many output records as input items, in the same order.
- **Validate before finishing** (short Python script): output parses, record
  count equals input count, `block_id` at each index matches the input, every
  non-null `pull_quote` is an exact substring of that item's `target.text`, no
  `pull_quote` from the Liston interview overlaps a `[...]` span longer than 25
  characters, and no more than 5 items have `notable == 3`.
