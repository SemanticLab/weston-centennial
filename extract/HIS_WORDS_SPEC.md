# His-words spec — what Randy Weston said about the people in his life

Project root: `/Users/m/git/weston-centennial`

Randy Weston (pianist, composer, bandleader; Brooklyn, 6 April 1926 –
1 September 2018) gave one oral-history interview that is in this corpus: the
Smithsonian Jazz Oral History Program, 30 October 2009. You are reading it to
establish, for each person named in it, **what he actually said about them and
how he knew them** — for a centennial web page.

## Read this before anything else

1. **It is a sequel.** The interviewer opens with *"since the last oral history
   a lot has happened"*. The conversation covers roughly 1997–2009 — the Verve
   records, the Gnawa of Morocco, Egypt, Japan, his marriage, the NEA award —
   and reaches back only when Weston chooses to (his parents, Coleman Hawkins at
   the Five Spot in 1959, Tangier in 1972). Do not expect the whole life.
2. **The interviewer is not a witness.** Speaker `Jenkins` is **Willard
   Jenkins**, a jazz journalist who was co-writing Weston's autobiography at the
   time. He supplies names and dates Weston has forgotten (*"Robert Lockwood
   Jr."*, *"Stafford James?"*) and Weston accepts or rejects them. What Jenkins
   says is context, not testimony.
3. **Weston talks in long turns** — one runs to 4,000 characters. A person is
   often one name in a band roll-call inside a paragraph about something else.
   Read for what he says *about the person*, not for the paragraph's subject.
4. **Names are spelled by ear.** The transcriber wrote what they heard:
   *"Louie Armstrong"*, *"Buddy Boland"* (Buddy Bolden), *"Kenny Durham"*
   (Kenny Dorham), *"Paul Robinson"* (Paul Robeson), *"Diana Washington"*
   (Dinah Washington), *"Philippe Alad"* (Jean-Philippe Allard — the name is
   split across a page break), *"Pharaoh Sanders"*, *"Luckas Foss"*. Recognising
   who is meant is part of your job (see `name` and `transcribed_wrong`). Quote
   the transcript exactly as it stands, misspellings included.
5. **Square brackets are the transcriber**: `[inaudible]` and two small word
   insertions (`[comprised of]`, `[it was a]`). Never quote a bracketed
   insertion as his words — quote around it.

The upstream model that first classified these relationships read a name in a
personnel list as a relationship and typed non-people as people (*"Gnawa"* is a
people, *"Isis"* a goddess, *"Mortiem"* may be a garbled name). Your job is to
replace its output with a reading a human would trust.

## Your input

- **`weston/own_interview.txt`** — the whole transcript, one block per line:

  ```
  [b309813 p0.7] Randy Weston: Right, I recorded for Verve in Paris, …
  ```

  `b309813` is the `block_id`; `p0.7` is page.block; a `*` after the speaker
  (`Randy Weston*`) means the label was inherited across a page break — the
  block continues the previous one mid-sentence. **Read the entire file first,
  start to finish.** It is about 57,000 characters. People recur; a name that is
  garbled on page 5 may be clear on page 13.
- **`weston/his_words_input/chunk_NNN.json`** — your ~38 people. Each item:

  ```
  person_id               the key — copy it through
  as_named_in_interview   the name string as the transcript has it
  surface_forms           every variant folded into this person
  upstream_identity       the Wikidata match the pipeline made (qid may be null)
  n_mentions, mention_block_ids   where the name appears (block_ids, no "b" prefix)
  is_interviewer          true for Willard Jenkins himself
  upstream                the earlier model's relation, direction, evidence —
                          a lead to check, NOT a finding
  ```

`mention_block_ids` lists only the blocks where the *name* was detected. The
person may also be discussed by pronoun around them — that is why you read the
whole transcript.

## Your output

Write `weston/his_words_output/chunk_NNN.json`:

```json
{"subject": "weston", "chunk": N, "count": <n>,
 "chunk_top": [<person_id>, <person_id>, <person_id>],
 "items": [ ... ]}
```

One record per input item, **same order, no drops**. (The values below show the
shape only — the person and the quotes are invented.)

```json
{
 "person_id": 100001,
 "is_person": true,
 "not_person_kind": null,
 "name": "John Example",
 "transcribed_wrong": false,
 "identity_ok": true,
 "identity_note": "",
 "same_person_as": null,
 "who_speaks_of_them": "weston",
 "basis": "his_statement",
 "relation": "in music group with",
 "direction": "weston_leads",
 "tie": ["sideman"],
 "firsthand": true,
 "stance": "positive",
 "stance_strength": 2,
 "era": "1990s–2009",
 "summary": "Weston named Example as the bassist on three of the records discussed and called him one of his regular guys.",
 "one_liner": "played bass in his regular trio",
 "his_quote": "I had my regular guys: John Example and …",
 "his_quote_block_id": 300001,
 "interviewer_quote": null,
 "interviewer_quote_block_id": null,
 "more_his_quotes": [{"block_id": 300010, "quote": "This time I took John Example."}],
 "instrument_or_role": "bass",
 "topics": ["trio", "Zep Tepi"],
 "notable": 2,
 "upstream_relation_ok": true,
 "confidence": "high",
 "notes": ""
}
```

### Field definitions

**`is_person`** (bool) — is this entry a real, individual human being?
False for peoples and groups (*Gnawa*), deities and mythical figures (*Isis*,
*Osiris* — Weston himself asks "Is she a myth; is she real?"), titles, places,
and descriptors. If false: set `not_person_kind` to `people_or_group` | `deity` |
`tune_title` | `company` | `descriptor` | `place` | `other`, set `relation:
"none"`, `basis: "none"`, `notable: 0`, all quotes null, `summary: ""`,
`one_liner: ""`, and say what it really is in `notes`.

**`name`** — the best full name for the person, **correctly spelled**. Outside
knowledge is welcome here and only here: "Kenny Durham" → "Kenny Dorham",
"Louie Armstrong" → "Louis Armstrong". Leave a bare or unrecognisable name as
the transcript has it rather than guess.

**`transcribed_wrong`** (bool) — true when the transcript's spelling of the name
is a mishearing or misspelling that `name` corrects. Say in `identity_note`
what the transcript has and why you read it as you do.

**`identity_ok`** (bool) / **`identity_note`** — is `upstream_identity` (the
Wikidata match) the right person, judging from the transcript? `true` when it is
plainly right, or when there is no upstream QID and nothing to dispute. `false`
when the match is wrong or when two different people were folded together — say
which in `identity_note`. If you are confident of the correct person and they are
well known, name them there; **do not invent a QID**.

**`same_person_as`** — if this entry is the same human being as *another* name
string in the transcript (*"Neil Clark"* / *"Neil Clarke"*; *"Fatu"* / *"Fatou"*
/ *"Fatoumata Mbengue"*; *"Al Hayward"* / *"Alan Hayward"*; *"Billy Hopper"* /
*"Billy Harper"*), give that other name string exactly as the transcript has
it. Otherwise `null`. Judge from the transcript; say why in `notes` when it is
not obvious.

**`who_speaks_of_them`** — `weston` | `jenkins_only` | `both` |
`front_matter_only`. Who actually utters anything about this person?
`front_matter_only` = they appear only in the archive's header or credit lines.

**`basis`** — what the relationship finding rests on. Exactly one:
- `his_statement` — Weston says it himself, in his own words
- `his_assent` — Jenkins states it and Weston confirms ("Exactly.", "Yeah.").
  The fact is established, but the words are Jenkins's.
- `interviewer_only` — Jenkins says it; Weston does not confirm, rejects it
  (*"No, not Stafford."*), or talks about something else
- `none` — nothing in the transcript establishes a relationship

**`relation`** — Weston's relation to this person. One term from the corpus's
controlled vocabulary, or `none`:

| term | use when |
|---|---|
| `in music group with` | they were members of the same working band — including his own sextet, quintet, trio |
| `collaborated with` | made music together outside a shared standing band: a record date, a one-off concert, an arranger, a co-composer, a guest |
| `played with` | performed together, no more than that is said |
| `toured with` | specifically travelled on a tour together |
| `played under` | one was the leader the other worked for (use only when the transcript frames it as leader and sideman) |
| `mentor of` | one taught, trained or guided the other |
| `influenced by` | one's music shaped the other's, with or without contact |
| `friend of` | a personal friendship is stated |
| `acquaintance of` | they knew each other; no more is established |
| `has met` | a meeting or encounter, nothing ongoing (*"I shook his hand"*) |
| `knows of` | he knew of them (heard them, admired them, read them, was asked about them) with no contact established |
| `none` | no relation between Weston and this person is established |

Pick the **strongest relation the transcript actually supports**, and be
conservative. Family members take `none` here and are described by `tie` — the
vocabulary has no kinship term.

**`direction`** — for the asymmetric relations (`played under`, `mentor of`,
`influenced by`), who holds the senior role. Exactly one of:
- `other_leads` — the other person is the leader / teacher / influence
  (Coleman Hawkins was his idol → `influenced by`, `other_leads`)
- `weston_leads` — Weston is the leader / teacher / influence
- `mutual` — the relation is symmetric (`in music group with`, `collaborated
  with`, `played with`, `toured with`, `friend of`, `acquaintance of`, `has met`)
- `na` — the relation is `knows of` or `none`

**`tie`** — one or more of: `sideman` (they played in a band he led),
`bandmate`, `bandleader` (they led a band he was in), `arranger` (they arranged
his music), `guest_or_one_off` (a guest on one date or concert),
`traditional_musician` (a Gnawa master, a Sufi singer, a Japanese or African
traditional player), `idol` (one of the masters he reveres), `teacher`,
`family`, `spouse`, `friend`, `record_producer_or_label`, `promoter_or_host`
(someone who arranged an event or received him), `scholar_or_author`,
`classical_musician`, `guide_or_stranger` (a person met on his travels),
`interviewer`, `recording_staff`, `unknown`.

**`firsthand`** (bool) — does the transcript show Weston's own direct contact
with this person?

**`stance`** — `positive` | `negative` | `mixed` | `neutral` | `null` — Weston's
attitude toward them, from what **he** says. `null` when he expresses none.
**`stance_strength`** 0–3.

**`era`** — when the connection was, as the transcript gives it ("1959",
"since 1967", "childhood"), or `""`.

**`summary`** — ONE sentence, past tense, naming him as "Weston": what he said
about this person, or what was established about them. If the content is
Jenkins's with Weston assenting, say so ("Jenkins supplied the name; Weston
agreed"). Empty string only when `is_person` is false.

**`one_liner`** — a phrase of **at most eight words**, lower case, no full stop,
that completes "Randy Weston's …" / "who …" or stands alone as a caption for how
he knew them: *"arranged his records for forty years"*, *"his idol; played on
his 1959 date"*, *"took him round the temple of isis"*. Every place, person,
title and year in it must be in the transcript. Empty string if nothing is
established.

**`his_quote`** / **`his_quote_block_id`** — the best sentence(s) **Weston
himself** says about this person. It MUST be an exact, contiguous substring of
the text of ONE block whose speaker is `Randy Weston` (or `Randy Weston*`), and
it must not include a bracketed insertion. Because his turns are long, **trim
to the sentence or two that are about this person** — never the whole
paragraph. A bare roll-call (*"I had Neil Clarke, Alex Blake; you had Billy
Harper, T.K. Blue, and Benny Powell."*) is a legitimate quote only when it is
all he says of them; prefer anything fuller. `null` if he never says anything
quotable about them. `his_quote_block_id` is the integer block id (no "b").

**`interviewer_quote`** / **`interviewer_quote_block_id`** — when `basis` is
`his_assent` or `interviewer_only`, the sentence(s) of **Jenkins's** that carry
the content: an exact, contiguous substring of ONE `Jenkins` block. `null`
otherwise.

**`more_his_quotes`** — up to 4 further quotable Weston lines about the same
person, each `{block_id, quote}` under the same exact-substring rule and each a
different sentence from `his_quote`. `[]` if none.

**`instrument_or_role`** — the instrument or role **the transcript gives** for
this person ("drums", "pipa", "president of Verve", "priest"), or `""`.

**`topics`** — 0–4 short free-text tags (bands, records, tunes, places).

**`notable`** 0–3 — how good is this person's entry for the page?
- `3` = he says something about them you would print large: vivid, specific,
  in his own words. **Hard quota: at most 5 per chunk.**
- `2` = a real relationship with a usable quote
- `1` = established but thin (a roll-call name, an assent)
- `0` = nothing usable, or not a person

**`upstream_relation_ok`** (bool) — was the earlier model's `upstream.relation`
right? (Measurement only; be honest.)

**`confidence`** — `high` | `medium` | `low`. **`notes`** — anything a human
should check: a contradiction between two passages, garbled text, a date that
looks wrong, who a doubtful name might really be.

**`chunk_top`** (top-level) — the 3 best `person_id`s in your chunk, best first.

## Write incrementally — mandatory

1. Before you start, check whether your output file exists; if so, resume after
   the last valid record.
2. Rewrite the whole output file after every 10 people (`count` = records
   written so far).

## Rules

- **Never invent text.** Quotes are exact substrings of a single block.
- **Only the transcript decides what he said.** Outside knowledge may be used
  to recognise who a name refers to and to spell it — never to supply a fact
  about his relationship with them that the transcript does not contain.
- Do not fix or tidy transcript text inside a quote.
- Output valid JSON, UTF-8, `ensure_ascii=False`. Write it with a short Python
  script run via `uv run --python 3.14 python <script>`.
- **Other agents run concurrently.** Helper scripts go in the scratchpad
  directory you were given, with your chunk number in the filename. Write to no
  path inside the project except your own output chunk. Do not run git commands.
- **Validate before finishing** against `weston/own_interview.json` (its
  `items[]` carry `block_id`, `speaker_effective`, `speaker_role` and `text`):
  output parses; record count and `person_id` order match the input; every
  `his_quote` / `more_his_quotes[].quote` is an exact substring of the `text` of
  the named block **and that block's `speaker_role` is `subject`**; every
  `interviewer_quote` is an exact substring of a block whose `speaker_role` is
  `interviewer`; no quote contains a `[`; `relation`, `direction`, `basis`,
  `who_speaks_of_them` use only the allowed values; at most 5 items have
  `notable == 3`.
