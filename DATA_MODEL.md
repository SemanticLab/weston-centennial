# Data model — the files a page should read

Everything is UTF-8 JSON, `indent=1`. Paths are relative to the repo root.
"Verified" below always means: re-checked by a merge script, and again by
`extract/verify_all.py` against the database, as an exact substring of the
block it names.

Read `README.md` → "Read this before building the page" first.

Conventions used throughout:

- **`notable`** 0–3 — the reader's grade of how good the thing is *for display*.
  3 = set it large (quota'd per pass). Rank on this, never on `confidence`.
- **`relation`** — one term of the corpus vocabulary: `in music group with`,
  `collaborated with`, `played with`, `toured with`, `played under`,
  `mentor of`, `influenced by`, `friend of`, `acquaintance of`, `has met`,
  `knows of`, `none`. `relation_weight` is the corpus's weight for it.
- **`url`** fields are deep links into the Linked Jazz transcript reader,
  `…?t=<doc_id>#b<page>-<block>`.
- **QIDs** come only from the corpus's person layer or from an exact unique
  label match in its `wd_people` table (`qid_source` says which). No QID was
  invented or searched for.

---

## 1. What he said — `weston/own_voice.json`

His 2009 Smithsonian interview, read whole. Top level: `doc`,
`read_this_first`, `themes`, `categories`, `stats`, and four layers.

### `self.items[]` — his pull quotes (129)

| field | |
|---|---|
| `id` | **the key.** `q001`… one-block quotes; `j01`… quotes that cross a page break. Several quotes share a `block_id` |
| `pull_quote` | verified verbatim; no transcriber's bracket; transcript spelling kept |
| `block_id`, `page`, `block`, `url` | where it is (first block, for a `j` quote) |
| `block_ids` | one id, or two when `spans_page_break` |
| `spans_page_break`, `page_break_after_chars` | the PDF cut the sentence; the quote is verified against the two blocks joined by one space |
| `chars`, `length` | `line` (≤ ~160 chars) · `passage` |
| `notable` | 3 = 13 items, 2 = 51, 1 = 65 |
| `is_top`, `top_rank` | the reader's five best |
| `category`, `category_secondary` | **the page section** (see `categories`); `category_agreed` false = settled or overruled by the adjudicator, with `category_note` |
| `theme[]` | the earlier multi-label tags (closed list in top-level `themes`) |
| `summary` | one sentence: what he is saying |
| `prompted_by`, `period` | what he was answering; when the thing happened |
| `stands_alone` | false (11) = needs the question; it is in `exchange.question` |
| `exchange` | `question[]` (Jenkins's turn(s) that set the answer off) and `earlier_in_same_answer[]` (block ids) |
| `contains_laughs_marker` | the quote includes the transcriber's "(Laughs)" |
| `notes` | what a misspelt name really is; where a neighbouring quote continues the thought |

### `categories[]` — the page sections

`key`, `label`, `order`, `definition`, `count`, `notable_2plus`. Ten sections,
designed by one reader, sorted independently by two (they agreed on 128 of
129), adjudicated by a fourth. The scheme, with its boundary rules, is
`weston/own_voice_output/category_scheme.json`.

### `timeline.items[]` — the facts the transcript states (55)

`when` (as given), `sort_year` (int or null — 22 are undated), `event`,
`place`, `stated_by` (`weston` | `jenkins` | `front_matter`),
`confirmed_by_weston`, `block_ids`, `url`, `notes`. Sorted by `sort_year`, undated
last in transcript order. **Thin before 1990** — the interview is a sequel. `notes`
(on 49) records where the transcript contradicts itself or the record.

### `records.items[]` — the recordings and pieces he discusses (34)

| field | |
|---|---|
| `key`, `order` | stable key; transcript order |
| `title`, `title_as_transcribed` | corrected published title; what the transcript has |
| `kind` | `album` · `live_album` · `composition` · `session` · `film` · `dvd` |
| `year`, `year_as_stated` | the transcript's year only (int / verbatim); never an outside one |
| `label_as_stated`, `raised_by` | `jenkins` or `weston` |
| `part_of` | key of the record a piece is on |
| `what_he_says` | 2–3 sentences, only what the transcript says |
| `title_meaning` | his gloss on the title ("Saga… means family") |
| `pull_quote`, `pull_quote_block_id`, `pull_quote_url`, `more_quotes[]` | verified |
| `personnel_as_stated[]` | `{as_transcribed, name, role}` — who he says was on it |
| `pieces_named[]` | tunes he names as on it |
| `discrepancies` | where his account conflicts with itself or the published record (25 of 34) |

Albums are joined to the discography: see `he_said_of_this_record` below.

### `journeys.items[]` — the occasions and places (41)

| field | |
|---|---|
| `key`, `order`, `title` | |
| `kind` | `concert` · `festival` · `residency` · `ceremony` · `journey` · `film_shoot` · `home` |
| `place`, `country` | corrected, mappable; `place_as_transcribed` is his words ("Gwana" → Qena) |
| `year`, `when_as_stated` | int or null; verbatim |
| `what_happened` | 3–4 sentences |
| `who_was_there[]` | `{as_transcribed, name, role}` |
| `pull_quote`, `more_quotes[]` | verified; a story quote can run to ~700 chars |
| `related_record_key` | the `records` key the occasion produced |
| `geo` | `{lat, lon, qid, label, matched_on, precision}` from `shared/places.json`; `precision` = `site` (34) · `town` (5) · `country` (1). null for the one journey with no place |
| `is_top`, `notable`, `discrepancies`, `notes` | |

`shared/places.json` is the same 40 points with the geocoder's working
(`rejected[]` = hits skipped for being in the wrong country or too far from
the named town).

---

## 2. Who he spoke of — `weston/his_words.json`

One record per person named in his interview (100 people, plus 14 entries
judged not to be people, kept with `is_person: false`).

| field | |
|---|---|
| `person_id` | corpus person id; negative = added by a reader, the name detection missed them |
| `name` | **corrected** full name |
| `as_named_in_interview`, `also_named[]` | the transcript's strings |
| `transcribed_wrong` | the transcript misspells or mishears the name (19) |
| `qid`, `qid_source`, `identity_ok`, `identity_note` | identity; `fold_contaminated` = right person, but a stray mention of someone else was folded in |
| `basis` | **filter on this.** `his_statement` (93) · `his_assent` · `interviewer_only` (5: Jenkins said it, Weston did not confirm) · `none` |
| `who_speaks_of_them` | `weston` · `both` · `jenkins_only` · `front_matter_only` |
| `relation`, `direction`, `relation_weight` | `direction`: `other_leads` · `weston_leads` · `mutual` · `na` |
| `tie[]` | `sideman`, `guest_or_one_off`, `idol`, `arranger`, `traditional_musician`, `family`, `spouse`, `teacher`, `friend`, `promoter_or_host`, `scholar_or_author`, `classical_musician`, `guide_or_stranger`, `record_producer_or_label`, `recording_staff`, `interviewer`, `unknown` |
| `instrument_or_role` | as the transcript gives it |
| `one_liner` | ≤ 8 words, lower case: how he knew them |
| `summary`, `era`, `stance`, `stance_strength`, `firsthand` | |
| `his_quote`, `his_quote_block_id`, `his_quote_url`, `more_his_quotes[]` | verified, his own turns only |
| `interviewer_quote` | Jenkins's words, when `basis` is assent or interviewer-only |
| `upstream` | what the earlier model said, and `relation_ok` (wrong for 53 of 103) |

Top-level `merged[]` holds the ten duplicate records that were folded in, with
reasons. Family members take `relation: "none"` and a `tie`.

---

## 3. Who spoke of him — `weston/witnesses.json`

One row per interview document in which a block was judged to be about him
(23 rows; 20 with `spoke_themselves: true`; 17 distinct people).

| field | |
|---|---|
| `witness_key` | the doc id |
| `name`, `qid`, `description`, `born`, `died`, `image` | the person actually speaking |
| `spoke_themselves` | **false = not a witness** (3) |
| `relation`, `direction` (`weston_leads` · `witness_leads` · `mutual` · `na`), `tier`, `contact_level`, `basis[]`, `context` | |
| `one_liner` | 3–8 words, "him/his": how they knew him. `grounded` false = a word the testimony does not contain (`ungrounded_words`) |
| `lead_quote`, `lead_block_id`, `lead_url`, `second_quote`, `more_quotes[]` | verified; the witness's own words |
| `caution` | **read before displaying** (non-empty on 19) |
| `summary`, `stance`, `stance_strength`, `notable` | |
| `doc` | title, collection, year, transcript and source URLs |
| `on_his_records`, `albums_with_him`, `instruments_on_his_records` | join to the roster |
| `he_spoke_of_them`, `he_said` | join to `his_words.json` |
| `liston_build` | Melba Liston's row only: her build's judged record for him (her interview read whole) |

Block level, if you need it: `weston/enriched.json` (84 blocks, each with
`pull_quote`, `mention_kind`, `stance`, `content_type[]`, `summary`, `notable`,
`context_before/after`, `doc`) and `best_quotes.json` (the 29 with `notable >= 2`
and a substantive kind). `recovered_best.json` holds 2 more that do not name
him (pronoun follow-ons).

---

## 4. The records — `weston/discography.json`

`releases[]` (138), sorted by year.

| field | |
|---|---|
| `title`, `qid`, `has_article`, `wikipedia_url`, `description`, `kind` | 24 have no article: title, year, label and note from his list only |
| `subject_role` | `leader` (51) · `sideman` (2) · `composer` (83: someone recorded his tune) · `sampled` (1) · `appears_on_screen` (1) |
| `subject_credit` | `found_in` (`personnel` · `tracks` · `prose` · `his_discography_list_only`), `roles[]`, `raw[]`, `tracks_naming_him[]`, `as_player`, `as_composer`, `review` (the reader's verdict, on the 4 uncertain ones) |
| `year`, `label`, `note`, `recorded`, `released`, `studio`, `venue`, `producer` | `note` = what his list says after the label ("10-inch LP", "with David Murray") |
| `tracks[]`, `personnel[]`, `session_notes[]` | from the album article |
| `musicbrainz`, `musicbrainz_matched_by` | release-group id; `wikidata` or `title` (22). Sleeve at `img/a/<mbid>.jpg` when `shared/cover_art.json` has it |
| `he_said_of_this_record` | **what he said about this record in 2009** (12 releases): `what_he_says`, `title_meaning`, `pull_quote`, `more_quotes`, `personnel_as_stated`, `pieces_named`, `discrepancies`, `notable` |

`weston/discography_personnel.json` → `people[]` (162): everyone credited on the
53 records he led or played on. `album_count`, `albums[]`, `instruments[]`,
`interviewed_in_corpus`, `interviews[]`, `said_about_subject` + `quotes[]` (what
they said of him), `he_spoke_of_them` + `he_said` (what he said of them).

`weston/compositions.json` → `items[]` (27 tunes): `title`, `spellings[]`,
`count`, `first_year`, `last_year`, `recordings[]` (`release`, `year`,
`performers[]`, `track_line` verbatim, `how` = `composer` | `sampled`). A floor,
not a count.

---

## 5. Everyone — `weston/people.json`

One record per person across four layers (215), keyed on QID (else
`name:<normalised>`): flags `witness`, `he_spoke_of`, `on_his_records`,
`network`; `layers[]`; `both_directions`; and the payload of each layer —
`witness_rows[]`, `he_said`, `records`, `edge`. Sorted both-directions first,
then `notable`, then number of layers.

## 6. Shared

- **`shared/images.json`** → `people[<QID>].image`: `url_200/400/800`,
  `license`, `attribution`, `review_flags[]`, `source`. Local copy at
  `img/p/<QID>.jpg`; `img/CREDITS.json` carries the terms.
- **`shared/class_of_1926.json`** → `others.{liston,davis,coltrane}`:
  `he_said`, `direct_edge`, `shared_neighbours`, `documents_naming_both`,
  `shared_releases` (`sessions_together` counts only records he led or played
  on), `shared_roster`. For Liston also `they_said` (her words about him, from
  her build), `weston_as_her_witness`, `liston_as_his_witness`.
- **`weston/biography_sources.json`** — `wikipedia.sections[]` (heading,
  paragraphs with the years each mentions) and `wikidata.statements[]`.
  Unjudged source material for the life his interview skips.
- **`weston/profile.json`**, **`connections.json`**, **`shared/communities.json`**
  — identity, links, the 116 network edges, his community (2, the same as the
  other three 1926 centennials).
