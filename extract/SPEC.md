# Shared extraction spec — Randy Weston centennial data build

Ported from the Melba Liston centennial build (`~/git/liston-centennial-2026`),
itself ported from the Coltrane / Davis one (`~/git/linked-jazz-coltrane-davis`).
Same corpus, same conventions, one subject.

## Source
Read-only SQLite: `/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite`
Schema doc: `/Users/m/git/ch-jazz-mashup/SQLITE.md` (READ IT FIRST)
Never write to the DB. Open read-only (`file:...?mode=ro`).

## Subject
| key | person | QID | node_id | community |
|---|---|---|---|---|
| `weston` | Randy Weston (6 Apr 1926 – 1 Sep 2018), pianist, composer, bandleader | `Q1371187` | `wd:Q1371187` | 2 |

All of this lives in `extract/subject.py`; import it rather than repeating it.

**He is an interviewee.** `OWN_DOC = Randy-Weston-Transcription-2020_0`
(Smithsonian Jazz Oral History, 30 Oct 2009, interviewer Willard Jenkins
`Q15449804`). Every script must decide what it does with that document; the
rule is: its blocks are flagged `own_interview`, are never counted as "another
musician talking about him", and are not sent to the block-evaluation pass at
all — they are read whole by the his-words and own-voice passes. Jenkins is not
a witness.

**This phase = data only, no HTML.**

## Output layout
```
weston/<file>.json      everything about the subject
shared/<file>.json      cross-cutting: images, places, communities, summaries
extract/<script>.py     transcript-derived layers  (stdlib only)
discography/<script>.py Wikipedia / Wikidata / Commons / MusicBrainz layers (bs4 + lxml)
img/                    local copies of portraits and sleeves
```
Run anything with `uv run python <script>` from the repo root.

## Universal JSON conventions
- UTF-8, `json.dump(..., ensure_ascii=False, indent=1)`.
- Every top-level file is an object with
  `{"subject": "weston", "qid": "Q1371187", "generated_from": "...", "count": <n>, "items": [...]}`
  plus task-specific keys.
- Any record derived from a transcript block carries provenance: `doc_id`,
  `block_id`, `page`, `block`, and a deep link
  `<documents.transcript_url>#b<page>-<block>`.
- Network deep link: `https://thisismattmiller.github.io/linked-jazz-2026-network/#<node_id>`
- Sort `items` by descending significance so a page can take top-N.
- Text is verbatim from the DB. Only runs of whitespace are collapsed; the raw
  form is kept in `text_raw` when that changed anything.

## Identity rule
Resolve people via `persons.qid` / `nodes.qid`, not by raw text search — with one
deliberate exception. The person layer left a handful of real mentions behind
("Randy Weston territory.", "Randy Western", "Randy [Weston]", a bare "Randy"
in an interview that names him in full elsewhere). `subject.target_blocks()`
adds those back as `mention_source: "fts_supplement"`; they are candidates until
the evaluation pass confirms each one.

Names inside his own interview are spelled by ear ("Kenny Durham", "Paul
Robinson"). The readers give the corrected name; a QID is attached to a
corrected name only on an exact, unique label match in the corpus's own
`wd_people` table, never by search, and never when the reader's confidence in
the correction is low.

## Judgement
Anything that requires reading and deciding — is this block about him, what did
he say about this person, which quote leads, what a record was for — is done by
**Claude Opus subagents** working to a written spec in this directory
(`EVAL_SPEC.md`, `RECOVERED_SPEC.md`, `HIS_WORDS_SPEC.md`, `OWN_VOICE_SPEC.md`,
`CATEGORY_SPEC.md`, `WITNESS_SPEC.md`). The scripts package the inputs and merge
the outputs; every merge re-verifies every quote as an exact substring of its
source block and drops what fails, and `verify_all.py` re-checks the lot against
the database.

## Style
Fail loudly on schema surprises. Print a short summary at the end of each script.
