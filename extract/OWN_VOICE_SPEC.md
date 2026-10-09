# Own-voice spec — Randy Weston in his own words

Project root: `/Users/m/git/weston-centennial`

Randy Weston (pianist, composer, bandleader; Brooklyn, 6 April 1926 –
1 September 2018) gave one oral-history interview that is in this corpus: the
Smithsonian Jazz Oral History Program, 30 October 2009. A centennial web page
will be built from it. Two of the three 1926 centennial subjects done before
him — John Coltrane and Miles Davis — were never interviewed, so their pages
could only show what other people said. His can show **him**.

## Read this before anything else

1. **It is a sequel.** The interviewer opens with *"since the last oral history
   a lot has happened"*. The conversation covers roughly 1997–2009 — the Verve
   records, the Gnawa of Morocco, Egypt, Japan, his marriage, the NEA award —
   and reaches back only when Weston chooses to (his parents, Coleman Hawkins at
   the Five Spot, Tangier in 1972). It is not a life story and must not be made
   into one.
2. **The interviewer is not a witness.** Speaker `Jenkins` is **Willard
   Jenkins**, a jazz journalist who was co-writing Weston's autobiography. He
   supplies names and dates; Weston accepts or rejects them.
3. **Weston talks in long turns** — 45 turns, ~48,000 characters, one of them
   4,000 characters. Almost nothing he says is a ready-made one-liner: the
   pull quotes have to be **cut out of paragraphs**. That cutting is the work.
4. **Names and some facts are transcribed by ear.** *"Louie Armstrong"*,
   *"Buddy Boland"* (Bolden), *"Kenny Durham"* (Dorham), *"Paul Robinson"*
   (Robeson), *"Diana Washington"* (Dinah), *"bass nova"*, and a "Montreal Jazz
   Festival" in 1974 before a "Swiss audience" that is surely Montreux. Quote
   the transcript exactly as it stands; record what you think is meant in
   `notes`, never in the quote.
5. **Square brackets are the transcriber**: `[inaudible]` and two small word
   insertions (`[comprised of]`, `[it was a]`). No quote may contain a `[`.
   Parenthesised `(Laughs)` is the transcriber too; avoid it where you can.

## Your input

- **`weston/own_interview.txt`** — the whole transcript, one block per line:

  ```
  [b309813 p0.7] Randy Weston: Right, I recorded for Verve in Paris, …
  ```

  `b309813` is the `block_id`; `p0.7` is page.block; `*` after a speaker means
  the label was inherited across a page break — the block continues the one
  before it mid-sentence. **Read the entire file, start to finish, before
  writing anything.** About 57,000 characters.
- **`weston/own_interview.json`** — the same blocks as structured data
  (`items[]`: `block_id`, `speaker_effective`, `speaker_role` = `subject` |
  `interviewer` | `none`, `text`, `people[]`). Use it for validation.
- **`weston/his_relationships.json`** — the people the pipeline detected in the
  interview (`items[].person.as_named_in_interview`, plus `skipped.items`). You
  need it only for Part D.
- **`weston/own_interview_entities.json`** — places, venues, works the tagger
  found (raw, unjudged). A checklist for Parts B and C, not a source.

(All block ids and values in the examples below are invented, to show shape only.)

Your assignment says which **parts** to produce. Each part is its own output
file. Do only the parts you are assigned.

---

## Part A — `weston/own_voice_output/self.json`: Weston in his own words

His best lines about **his own life, music and beliefs**. Not what he says about
other people for their own sake (another pass does that) — what he says about
being Randy Weston: the ancestors, Africa, the blues, his parents, Brooklyn, the
piano, the masters he shook hands with, the Gnawa, the spirits that guide him.

```json
{"subject": "weston", "part": "self", "count": <n>,
 "top": ["q007", "q031", "q002", "q019", "q044"],
 "items": [
  {"id": "q001",
   "block_id": 300001,
   "pull_quote": "exact contiguous substring of that Weston block",
   "theme": ["ancestors"],
   "period": "",
   "summary": "One sentence, past tense: what he is saying and about what.",
   "prompted_by": "what Jenkins had just asked, in a few words",
   "stands_alone": true,
   "context_block_ids": [],
   "length": "line",
   "stance": "positive",
   "notable": 2,
   "notes": ""}
 ],
 "timeline": [ ... ]}
```

- Select **every** Weston passage worth showing — expect somewhere between 60
  and 120. Completeness matters more than a tidy number: a later step filters by
  `notable`.
- **Several items may come from one block.** His turns are paragraphs holding
  three or four separable thoughts; give each its own item, with a
  non-overlapping `pull_quote`. Do not quote a whole 2,000-character turn.
- **`id`** — `q001`, `q002`, … in transcript order. Unique.
- **`pull_quote`** — exact, contiguous substring of ONE block whose
  `speaker_role` is `subject`. No ellipsis, no splicing, no tidying, no `[`.
  Start at a sentence start and end at a sentence end wherever the text allows.
  Aim for **one to four sentences**; a quote over ~450 characters needs a
  reason (a story that cannot be cut) — say it in `notes`.
- **`length`** — `line` (≤ ~160 chars: could be set large) | `passage`
  (a few sentences) | `story` (a longer anecdote that has to run whole).
- **`theme`** — one or more of this closed list:
  `ancestors` (the ancestors, the spirits that guide him, destiny, "I was put in
  a certain place at a certain time") ·
  `africa` (Africa as the source; ancient Egypt and Nubia; "Africa's
  contribution"; African civilisation and history) ·
  `gnawa_morocco` (Tangier, the Gnawa, Jajouka, the African Rhythms club, the
  1972 festival) ·
  `the_blues` ·
  `spirit_of_music` (music as a spiritual language; nature, vibration, the
  planet; love as the approach) ·
  `family` (father, mother, sister, wife, son; "all of my music is geared
  towards family") ·
  `brooklyn` (growing up, the neighbourhood, the black church, poverty and love) ·
  `the_masters` (Ellington, Monk, Hawkins, Basie, Nat Cole, Armstrong, Holiday —
  the royalty; the handshakes; the baton passed) ·
  `the_piano` (solo piano, his reluctance, trio versus ensemble, the instrument
  itself, his teacher giving up on him) ·
  `melba_liston` (the partnership) ·
  `records` (what a particular record or composition was for) ·
  `the_band` (his musicians; "adventures") ·
  `journeys` (Japan, Egypt, Canterbury, Alexandria, St. Lucia, Mississippi —
  ceremonies and travels outside Morocco) ·
  `machines_and_human_contact` ·
  `race_and_history` (slavery, segregation, the cotton field, what his parents'
  generation endured) ·
  `recognition` (the NEA Jazz Masters award, honours) ·
  `character` (a line that simply shows who he is: humour, modesty, his size)
- **`period`** — when the thing he describes happened, as the transcript gives
  it, or `""`.
- **`stands_alone`** (bool) — can the quote be read cold, with no setup?
  If false, `context_block_ids` must list the block(s) a reader needs (usually
  Jenkins's question immediately before).
- **`stance`** — his attitude to what he is describing: `positive` | `negative`
  | `mixed` | `neutral`.
- **`notable`** 0–3 — `3` = set it in large type under his photograph. **At most
  12 items may be 3.** `2` = good, usable. `1` = minor but real. Do not include
  `0`s.
- **`top`** — the `id`s of your five best, best first.

### The timeline (same file, top level)

```json
"timeline": [
  {"when": "1967", "sort_year": 1967, "event": "First met the Gnawa, in Tangier.",
   "place": "Tangier, Morocco",
   "block_ids": [300001], "stated_by": "weston", "confirmed_by_weston": true, "notes": ""}
]
```

Every datable or sequenceable fact about his life and work **the transcript
itself states** — births and deaths in the family, first recordings, record
dates, concerts, journeys, the club, the festival, the marriage, awards.
`stated_by`: `weston` | `jenkins` | `front_matter`. `confirmed_by_weston`: true
when he says it or clearly assents. `sort_year` is your best integer year for
ordering, or `null` when the transcript gives no way to place it. `place` as
the transcript gives it, or `""`.

**The transcript contradicts itself and the record in places** — he gives both
1991 and 1981 for the Boston Pops concert; Jenkins says the NEA award was 2003
where the transcript's own header says 2001; a "Montreal" festival has a Swiss
audience. Record what the transcript says, one entry per claim, and put the
conflict — and what you believe is right, if you know — in `notes`. Do not
silently correct and do not add facts from outside knowledge.

---

## Part B — `weston/own_voice_output/records.json`: the records, in his words

Jenkins walks him through his recordings one by one. For **every recording,
composition or filmed work** discussed or named in the transcript — the new
albums Jenkins asks about, the older ones Weston reaches back to (the first
Riverside album, the 1959 Five Spot date), individual pieces he explains
(*Earth Birth*, *Tamashii*, *Three African Queens*), the documentary film — one
record:

```json
{"subject": "weston", "part": "records", "count": <n>,
 "items": [
  {"key": "saga",
   "title_as_transcribed": "Saga",
   "title": "Saga",
   "kind": "album",
   "year_as_stated": "’95",
   "year": 1995,
   "label_as_stated": "Verve",
   "raised_by": "jenkins",
   "block_ids": [300001, 300002],
   "what_he_says": "Two or three sentences, past tense: what the record was, what the title means, what he wanted from it — only what the transcript says.",
   "title_meaning": "the meaning he gives for the title, in his terms, or \"\"",
   "pull_quote": "exact contiguous substring of ONE Weston block",
   "pull_quote_block_id": 300001,
   "more_quotes": [{"block_id": 300002, "quote": "…"}],
   "personnel_as_stated": [
     {"as_transcribed": "Billy Higgins", "name": "Billy Higgins", "role": "drums"}],
   "pieces_named": ["Uncle Nemo"],
   "part_of": null,
   "discrepancies": "",
   "notable": 2,
   "notes": ""}
 ]}
```

- **`kind`** — `album` | `live_album` | `composition` (a single piece or suite)
  | `session` (a date he describes without an album title) | `film` | `dvd`.
- **`title`** — the correct published title when you recognise it (outside
  knowledge allowed for titles and spellings only); `title_as_transcribed` is
  what the transcript has. If you are not sure, repeat the transcribed form and
  say so in `notes`.
- **`year_as_stated` / `year`** — what the transcript says, verbatim, and your
  integer reading of it. `year: null` if the transcript gives none. Never a
  year from outside knowledge — put that in `discrepancies` instead.
- **`raised_by`** — `jenkins` | `weston`.
- **`personnel_as_stated`** — everyone **he or Jenkins names as playing on or
  working on this record**, in order, with the role the transcript gives
  (`""` if none). `name` is the corrected spelling.
- **`pieces_named`** — titles of tunes/movements he names as being on it.
- **`part_of`** — the `key` of another record in your list when this is a piece
  on it (*Tamashii* → the trio album), else `null`.
- **`discrepancies`** — where the transcript's account conflicts with itself or
  with the published record as you know it (wrong year, a garbled title, a
  personnel name that cannot be right). Say what and why. `""` if none.
- **`pull_quote`** / **`more_quotes`** (up to 3) — his best lines about *this
  record*: exact substrings of ONE Weston block each, no `[`, trimmed to the
  sentences that are about the record. `null` / `[]` when he says nothing
  quotable.
- **`notable`** 0–3 — how good is this entry for a page that shows a record
  sleeve with his words beside it? At most 5 may be 3.

Order the items as the transcript raises them.

---

## Part C — `weston/own_voice_output/journeys.json`: the adventures

*"When I play with Randy Weston we don't do gigs, we have adventures."* The
interview is a sequence of journeys and ceremonies: a church in Brooklyn with
three religions in it, donkeys up a mountain to Jajouka, a bullring in Tangier,
a Shinto shrine two weeks after his sister's funeral on 11 September 2001,
Canterbury, the library at Alexandria, a Nubian wedding at Aswan, a cotton
field in the Mississippi Delta. For **every such occasion he recounts** — a
concert, a festival, a ceremony, a trip, a residency — one record:

```json
{"subject": "weston", "part": "journeys", "count": <n>,
 "top": ["kamigamo_shrine", "…", "…"],
 "items": [
  {"key": "kamigamo_shrine",
   "title": "Solo piano at the Kamigamo shrine",
   "kind": "ceremony",
   "place_as_transcribed": "Kamigamo shrine … Kyoto, Japan",
   "place": "Kamigamo Shrine, Kyoto",
   "country": "Japan",
   "when_as_stated": "two weeks later [after 11 September 2001]",
   "year": 2001,
   "block_ids": [300001, 300002],
   "what_happened": "Three or four sentences, past tense, only what the transcript says.",
   "who_was_there": [{"as_transcribed": "Alex Blake", "name": "Alex Blake", "role": "bass, on a later visit"}],
   "pull_quote": "exact contiguous substring of ONE Weston block",
   "pull_quote_block_id": 300002,
   "more_quotes": [{"block_id": 300001, "quote": "…"}],
   "related_record_key": null,
   "discrepancies": "",
   "notable": 3,
   "notes": ""}
 ]}
```

- **`kind`** — `concert` | `festival` | `residency` | `ceremony` | `journey`
  (travel that is not a performance) | `film_shoot` | `home` (a place he lived
  or ran — the African Rhythms club, the Berkshires summers, the house in
  Brooklyn).
- **`place_as_transcribed`** — his words for where; **`place`** — the real,
  correctly spelled place, as specific as the transcript supports (a building,
  else a town), so it can be put on a map. The transcriber's ear again:
  *"Gwana"* near Karnak is Qena; *"Azwan"* is Aswan; *"Kamigano"* is Kamigamo;
  the 1974 *"Montreal"* festival with a Swiss audience is Montreux. Correct the
  place in `place`, explain in `discrepancies`. **`country`** — the modern
  country.
- **`when_as_stated` / `year`** — verbatim, and your integer reading; `null` if
  the transcript gives no way to date it.
- **`who_was_there`** — the people he names as present, with corrected names.
- **`related_record_key`** — if you are also doing Part B, the `key` of the
  record this occasion produced; else `null`.
- **`pull_quote`** / **`more_quotes`** (up to 3) — exact substrings of ONE
  Weston block each, no `[`. For a story, the quote may be long (up to ~700
  characters) if it cannot be cut.
- **`notable`** 0–3; at most 6 may be 3. **`top`** — the keys of your three best.

Also include every **place he names as part of his life** even without a story
(the Berkshires, Paris, the People's Institutional Church in Brooklyn, Oklahoma
City where he shook Armstrong's hand) as short `kind: "home"` or `"journey"`
records with `notable: 1` — the page may draw a map.

---

## Part D — `weston/own_voice_output/missed_people.json`: people the pipeline missed

The automatic name detection missed people. List **every real person named or
clearly identified in the transcript who is NOT already in
`weston/his_relationships.json`** (compare against
`items[].person.as_named_in_interview`, `items[].person.surface_forms` and
`skipped.items[]`; match loosely — a spelling variant of a detected name is
already there).

```json
{"subject": "weston", "part": "missed_people", "count": <n>,
 "items": [
  {"name": "John Example",
   "as_in_transcript": ["Mr. Example"],
   "transcribed_wrong": false,
   "block_ids": [300004, 300009],
   "who_is_this": "the bassist on his first record",
   "who_speaks_of_them": "weston",
   "basis": "his_statement",
   "relation": "collaborated with",
   "direction": "mutual",
   "tie": ["guest_or_one_off"],
   "firsthand": true,
   "stance": "neutral",
   "stance_strength": 0,
   "era": "1954",
   "summary": "One sentence, past tense.",
   "one_liner": "at most eight words, lower case",
   "his_quote": "exact substring of ONE Weston block, or null",
   "his_quote_block_id": 300005,
   "interviewer_quote": null,
   "interviewer_quote_block_id": null,
   "instrument_or_role": "bass",
   "notable": 2,
   "confidence": "high",
   "notes": ""}
 ]}
```

The fields mean exactly what they mean in `extract/HIS_WORDS_SPEC.md` — **read
its "Field definitions" section** for the vocabularies of `who_speaks_of_them`,
`basis`, `relation`, `direction`, `tie`. `who_is_this` is a plain description
from the transcript. Include unnamed-but-identified people only when the
transcript gives enough to say who they are (his father, his mother, his
sister, "Duke's sister" if not otherwise named). If there are no missed people,
write an empty `items` list; do not pad.

---

## Rules for all parts

- **Never invent text.** Every quote is an exact, contiguous substring of ONE
  block's `text` in `own_interview.json`, spoken by the right voice.
- **Only the transcript decides what was said.** Outside knowledge may be used
  to recognise and spell a name, a title or a place — never to supply a fact.
  Where you know the transcript is wrong, say so in `notes` / `discrepancies`.
- Do not fix or tidy transcript text inside a quote.
- Output valid JSON, UTF-8, `ensure_ascii=False`, written by a short Python
  script run via `uv run --python 3.14 python <script>`.
- **Write incrementally**: check whether your output file already exists and
  resume; rewrite the file after every ~20 items.
- **Other agents run concurrently.** Helper scripts go in the scratchpad
  directory you were given, with your part name in the filename. Write to no
  path inside the project except your own output file(s) under
  `weston/own_voice_output/`. Do not run git commands.
- **Validate before finishing**: output parses; every quote is an exact
  substring of the named block; Weston quotes come from `speaker_role ==
  "subject"` blocks and Jenkins quotes from `speaker_role == "interviewer"`
  blocks; no quote contains `[`; within Part A no two `pull_quote`s from the
  same block overlap and every `id` is unique; the `notable == 3` quotas hold;
  every `block_id` you cite exists.
