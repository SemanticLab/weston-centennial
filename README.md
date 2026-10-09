# Randy Weston — centennial data extraction

What jazz musicians said about **Randy Weston** (6 April 1926 – 1 September
2018; pianist, composer, bandleader) — and what he said about them, about his
records and about the places the music took him — pulled from the Linked Jazz
2026 corpus for his 2026 centennial.

The repo has two halves: the **data layer** (`weston/`, `shared/`, `extract/`,
`discography/`) and the **page** (`site/` builds `docs/`, which is the static
site). The data layer was built first and is described below; the page is in
"The page" at the end.

It is a port of the Melba Liston build (`~/git/liston-centennial-2026`), which
was itself a port of the Coltrane / Davis one (`~/git/linked-jazz-coltrane-davis`):
same corpus, same conventions, same passes. Where it departs from the Liston
build, it is because of what his interview is — see the next section.

Source: `~/git/ch-jazz-mashup/linked_jazz.sqlite` — 1,347 oral-history interview
transcripts from four archives (Tulane/Hogan, Hamilton/Fillius,
Smithsonian/NEA Jazz Masters, Rutgers/IJS). The DB is opened read-only
everywhere and is never modified.

**The DB was rebuilt after the data layer was.** The judgement passes ran on
2 October 2026 against schema 1 of the corpus (kept beside it as
`linked_jazz.pre_audit.sqlite`). On 9 October the per-transcript audit produced
schema 2.1: every `block_id` was renumbered, Hamilton page footers were stripped
from block text, and page-break continuation blocks got their speakers resolved.
Nothing moved — `(doc_id, page, block)` is the same key in both — but the
judged outputs only line up with inputs built from the DB they were judged
against. So `build_all.sh` runs every pipeline step against the pre-audit copy
(`LINKED_JAZZ_DB`, see `extract/subject.py`), then `extract/remap_block_ids.py`
carries every block id and block text in the merged files onto the current DB
(5,569 ids in 21 files; the judges' `*_input*` / `*_output*` files stay in the
old id space), and `verify_all.py` and the page read the current DB: 700 for
700. The judged files were not re-read. Two things the audit changed that a
re-run of the judgement passes would pick up: the own-interview person layer now
carries the corrected names and QIDs that `his_words.json` arrived at by hand
(Kenny Dorham, Buddy Bolden, Lukas Foss, Mor Thiam ...), and the candidate set
of blocks about him is the same 93 (three of them now from the person layer
instead of the text sweep). Also: the audited corpus has 71 communities where
schema 1 had 58; `build_connections.py` no longer asserts the count.

## What makes him different

**Like Liston, he was interviewed. Unlike hers, his interview is a sequel.**
The Smithsonian Jazz Oral History Program recorded him on 30 October 2009; the
interviewer, the journalist Willard Jenkins, was then co-writing his
autobiography, and opens with *"since the last oral history a lot has
happened"*. So the transcript (20 pages, 111 blocks) covers roughly 1997–2009
and takes the first seventy years as read. Three consequences shape everything:

- **It is not a life story.** Liston's timeline came out of her interview; his
  cannot. 55 timeline entries were extracted, and they cluster after 1990. The
  outside record of the rest is collected, unjudged, in
  `weston/biography_sources.json` (his Wikipedia article and Wikidata item).
- **It is a walk through the records, and a string of journeys.** Jenkins asks
  about each album in turn; Weston answers with where it took him — a Shinto
  shrine in Kyoto two weeks after burying his sister on 11 September 2001, a
  bullring in Tangier, donkeys up to Jajouka, a Nubian wedding at Aswan. Two
  layers exist here that the Liston build did not have: **`records`** (34
  recordings and pieces, each with what he said it was for, joined to the
  discography) and **`journeys`** (41 occasions and places, every one with
  coordinates).
- **He talks in paragraphs.** Liston, after her stroke, answered "Yeah."; her
  build's problem was telling her words from her interviewer's. Weston's 57
  blocks run to 48,000 characters — one of them 4,000 — so the work was
  **cutting**: 129 pull quotes were cut out of 35 blocks, several to a block,
  ten of them across a page break.

Two more differences:

- **His interviewer is not a witness.** Clora Bryant, who interviewed Liston,
  was a peer, and her remarks to Liston were testimony (83 lines). Jenkins is a
  journalist and collaborator; his questions are kept as the context for the
  answers and nothing more. There is no interviewer layer.
- **The transcript spells by ear.** "Louie Armstrong", "Buddy Boland"
  (Bolden), "Kenny Durham" (Dorham), "Paul Robinson" (Robeson), "Dorothy
  Dandridge" in a list of pianists (surely Donegan), "Philippe Alad"
  (Jean-Philippe Allard, split across a page break), a "Montreal" festival
  with a Swiss audience (Montreux). **Quotes keep the transcript's spelling**;
  every record carries the corrected name beside it, and
  `transcribed_wrong: true` where they differ (19 people).

| direction | where | size |
|---|---|---|
| **others → him** | 22 other interviews | 83 blocks about him, 17 people who actually spoke |
| **him → others** | his own interview | 100 people, 94 with a line in his own words |
| **him → himself** | his own interview | 129 pull quotes, 55 timeline facts |
| **him → his records** | his own interview | 34 recordings and pieces, 12 joined to the discography |
| **him → the places** | his own interview | 41 journeys, 40 on the map |

## Layout

```
weston/
  profile.json               identity, links, community, headline stats
  documents.json             the interviews that name him (+ text_hit_only_documents)
  biography_sources.json     Wikipedia + Wikidata, verbatim: the life his interview skips
  --- others -> him ---
  quotes.json                every block that may be about him, with context
  relationships.json         upstream LLM relations to him (22; weak -- see witnesses.json)
  connections.json           network edges to every other person (116)
  cooccurrence.json          entities named in the same block (his own interview excluded)
  nicknames.json             raw text sweep for Weston -- the recall audit
  eval_input/ eval_output/   chunks to and from the block-level judgement
  enriched.json              ★ every block: window + judgement + provenance (84)
  best_quotes.json           ★ the verbatim-checked display shortlist (29)
  false_positives.json       blocks judged not about him (1)
  recovered_*.json           pronoun follow-ons and answers; recovered_best.json ★ (2)
  witness_input/output.json  bundles to and from the person-level judgement
  witnesses.json             ★ one row per witness: relation, caption, lead quote, caution
  --- him -> others, himself, his records, the places ---
  own_interview.json         his whole interview, block by block, roles resolved
  own_interview.txt          the same as reading text (what the judges read)
  own_interview_entities.json  places, bands, tunes, venues named in it (raw NER)
  his_relationships.json     upstream LLM relations FROM him (112; 52% wrong -- see below)
  his_words_input/ output/   chunks to and from that judgement
  his_words.json             ★ one record per person he spoke of, judged
  own_voice_output/          raw reading-pass output (self, self_joined, records,
                             journeys, missed_people, category_*)
  own_voice.json             ★ self (129) · timeline (55) · records (34) · journeys (41)
  category_input.json        the pull quotes as packaged for the section-sorting pass
  --- records ---
  discography.json           ★ 138 releases with his credit on each
  discography_personnel.json ★ 162 people on the records he led or played on + the interview join
  compositions.json          ★ his tunes on other people's records (27 tunes, 87 recordings)
  --- everyone ---
  people.json                ★ one record per person across all four layers (215)
shared/
  images.json                ★ portrait per person: Commons URLs, licence, attribution
  cover_art.json             album sleeves from the Cover Art Archive (65)
  places.json                ★ the journeys, geocoded against Wikidata (40 of 40)
  communities.json           all 58 network communities; 2 is his
  class_of_1926.json         ★ him beside Liston, Davis and Coltrane, the other 1926 centennials
  *_summary.json             stats for each pass
img/
  p/<QID>.jpg                133 portraits (200px; his also @2x)
  a/<MBID>.jpg               64 sleeves
  CREDITS.json               licence + attribution for every file
extract/                     transcript-derived layers (stdlib only) + the six *_SPEC.md files
discography/                 Wikipedia / Wikidata / Commons / MusicBrainz layers; cache/ and raw/
build_all.sh                 every deterministic step, in order
```

★ = what a page should read. Everything else is working material or audit trail.
`DATA_MODEL.md` describes the starred files field by field.

## How the judgement was done

Every decision that needs reading — is this block about him, what did he say
about this person, which line leads, what was a record for, which section does
a quote belong in — was made by **Claude Opus subagents**, each working to a
written spec in `extract/`. Sixteen agent runs in all:

| pass | spec | agents | input → output |
|---|---|---|---|
| block evaluation | `EVAL_SPEC.md` | 2 | 84 blocks in windows → `eval_output/` |
| recovered blocks | `RECOVERED_SPEC.md` | 1 | 45 pronoun/answer blocks → `recovered_output.json` |
| his words | `HIS_WORDS_SPEC.md` | 3 | 113 detected "people" → `his_words_output/` |
| own voice A: self + timeline | `OWN_VOICE_SPEC.md` | 1 (+1 follow-up) | the whole transcript → `self.json`, `self_joined.json` |
| own voice B + C: records, journeys | `OWN_VOICE_SPEC.md` | 1 | the whole transcript → `records.json`, `journeys.json` |
| own voice D: missed people | `OWN_VOICE_SPEC.md` | 1 | the whole transcript → `missed_people.json` |
| witnesses | `WITNESS_SPEC.md` | 1 | 23 bundles → `witness_output.json` |
| album credits | *(in the prompt)* | 1 | 4 uncertain credits → `raw/credit_review_output.json` |
| sections | `CATEGORY_SPEC.md` | 4 | 129 pull quotes → `own_voice_output/category_*.json` |

The his-words and own-voice readers each read **the entire transcript** before
judging anything.

**No judge's quote is trusted.** Every merge script re-verifies every quote as an
exact substring of one source block, spoken by the right voice, with no
transcriber's bracket in it, and drops what fails. `extract/verify_all.py` then
re-does the whole check independently against the database rather than the
intermediate JSON: **700 quotes checked, 0 failures**, and no quote had to be
dropped at any merge step. Ten of his quotes cross a page break (the PDF's
pages cut his sentences in two, and a block is a page's worth of a turn); those
are verified against the two consecutive blocks joined by one space and must
actually cross the join.

**Duplicates** in his interview (one person under two spellings: "Neil Clark" /
"Neil Clarke", "Billy Hopper" / "Billy Harper", "Kofi Ghanaba" / "Guy Warren",
"Jean" + "Philippe Alad" across a page break) were flagged by the readers in
`same_person_as` and folded in `build_his_words.py`; the ten absorbed records
are kept under `his_words.json` → `merged`, each with the reason.

**Identifiers are never invented.** A corrected name ("Kenny Durham" → Kenny
Dorham) gets a QID only on an exact, unique label match in the corpus's own
`wd_people` table, never by search, and not when the reader's confidence in the
correction was low. That gave 16 people a QID. One such match was refused by
hand: the only "John Williams" in the table is a jazz musician, and the man
conducting the Boston Pops is not him (`build_his_words.py` → `QID_DENY`).

### Sections of "In his own words"

Every pull quote in `own_voice.json` → `self` carries a `category`: one of ten
page sections, listed in `own_voice.json` → `categories`.

| section | quotes | graded 2+ |
|---|---|---|
| What Music Is | 17 | 8 |
| Africa the Source | 9 | 4 |
| Ancestors and Destiny | 11 | 9 |
| Family and Brooklyn | 14 | 11 |
| The Masters | 8 | 4 |
| At the Piano | 10 | 4 |
| Records and Compositions | 20 | 7 |
| Morocco and the Gnawa | 16 | 8 |
| On the Road | 13 | 4 |
| His Marriage | 11 | 5 |

The pass is `extract/CATEGORY_SPEC.md`: one Opus subagent designed the scheme
from the quotes (31 boundary rules), two sorted all 129 independently, a fourth
settled the one quote they split on and reviewed the 23 either had doubts
about, overruling the scheme on one (the piano teacher who "gave up on" him
goes with his childhood, not with the NEA award that prompted the story). The
sorters agreed on 128 of 129, but that measures how tightly the boundary rules
are written, not how obvious the sections are: both sorters independently named
the same six weak spots, and the adjudicator's seven `scheme_problems` are in
`own_voice_output/category_adjudicated.json` for whoever revises it. The older
multi-label `theme` is still on each item.

## The numbers

| | |
|---|---|
| interviews naming him (other than his own) | **22** reconciled to his QID; the text sweep added 6 blocks, 1 in an interview not otherwise linked (Kenny Barron's) |
| blocks about him in those interviews | **83** of 84 evaluated (1 false positive) |
| …where the wider context changed the reading | 61% |
| people who said something about him in their own words | **17** (20 interviews; Powell, Owens, Keepnews twice each) |
| display shortlist (`best_quotes.json`) | **29** |
| recovered pronoun/answer blocks really about him | 7 of 45 (16%) |
| people named in his own interview | 113 detected + 11 the detection missed → **100 real people** after judgement and merging |
| …with a relation established | 89 |
| …with a line in his own words | **94** (192 verified quotes) |
| …whose name the transcript misspells | 19 |
| his lines about himself | **129** (13 at the top grade; 10 across a page break) |
| biographical timeline entries | 55 (49 confirmed by Weston; 49 carry a note) |
| recordings and pieces he discusses | **34** (27 with a quote; 25 with a discrepancy noted) |
| journeys and places | **41** (39 with a quote; 40 geocoded) |
| releases | **138** — 114 with an article, 24 listed without one |
| …as leader / sideman / someone recorded his tune / sampled | 51 / 2 / 83 / 1 |
| his tunes on other people's records | 27 tunes, 87 recordings — *Hi-Fly* 34, *Little Niles* 12 |
| people credited on the records he led or played on | 162 (127 with a QID) |
| …who were interviewed in the corpus | 29 |
| …and said something about him | **5** |
| …whom he spoke of | **27** |
| people with a portrait | 132 of 183 (72%); 14 of the 16 witnesses with a QID |
| network edges | 116 |

**Two people appear in both directions and in all four layers** — they spoke of
him, he spoke of them, they are on his records and in the network: **Melba
Liston** and **Benny Powell**.

## What came out of it

**The upstream model was wrong about his interview half the time.** Of 103
relations it classified *from* him that the readers judged, **53 were wrong
(52%)** — against 59% for Liston. The cause is different. Hers was a model
taking the interviewer's words for hers; his is a model reading every name in
a band roll-call as `in music group with` (it is usually one record date:
`collaborated with`) and every revered elder as `knows of` (he shook their
hands). It also typed 14 non-people as people — the Gnawa, Isis and Osiris, the
Archbishop of Canterbury, the album title *Zep Tepi*, "Western musicians".
`his_relationships.json` is kept as the audit trail; **use `his_words.json`**.

**Few people talk about him, and the ones who do worked for him.** He is named
in 22 interviews against Coltrane's 299. Half of what was said comes from two
people: Melba Liston (26 blocks in her interview, 32 in her witness bundle) and
Benny Powell, his trombonist (two interviews, 19 blocks). Every substantive
stance is positive or neutral — there is no dissent in this corpus.

> "he said, “I’m just trying to put the magic back in music.” And boy can he
> ever do it. He is a spellbinder." — Benny Powell
>
> "I wrote for him up until I had the stroke. After I had the stroke and got
> over a little bit, I’m writing for him again. I think he pulled me out of it –
> helped anyway. I thank him very much for sticking with me, because nobody else
> did." — Melba Liston
>
> "Randy Weston gave me a stack of about an inch of his lead sheets. One of the
> things he said was, “You’ve gotta have your stuff written out if you want
> people to record it.”" — Jimmy Owens
>
> "Randy Weston is a remarkable musician who has over the years taken the
> historical line from Africa that has been developed in the Americas and has
> done something very special with it." — Billy Taylor

**His own top lines** (`own_voice.json` → `self`, `notable: 3`):

> "People say, “Randy Weston, you did this! You did!” I didn’t do any of those
> things. Somehow I was put into a certain place at a certain time, you know."
>
> "The blues is always underneath it all because the blues, I feel, is the
> language of our people, how we survived."
>
> "Well, the approach is always the same—just love. Just love."
>
> "For me, the continent was swinging before man ever arrived."
>
> "I shook Louie Armstrong’s hand in Oklahoma City. I’ll never forget that
> handshake."

**The Liston loop closes.** Weston and Liston were partners for forty years and
both sat for the Smithsonian — she in 1996, he in 2009 — so
`shared/class_of_1926.json` → `liston` carries each one's account of the other
from each one's own interview, judged by each build's own readers. Hers: *"I
think he pulled me out of it."* His: *"I went to see her, and I insulted her as
only musicians can do… I said to her, 'You have to do these arrangements stroke
or no stroke, handicap or no handicap.'"* The Liston build flagged that passage
as sensitive; here it is his best line about her, and her own account of the
same months sits beside it. Her bundle in `witnesses.json` also carries
`liston_build` — what the readers of her whole interview concluded — and the
four of her lines about him that do not name him were added to it so they could
be quoted.

**His discography is a leader's and a composer's.** His Wikipedia list has 51
records as leader and two as a sideman. The sweep of album articles that link
to him found 83 more on which someone else recorded one of his tunes, and one
that samples him (The Prodigy's *Smack My Bitch Up*, "In Memory Of"). It also
found 587 albums that link to him only because a sideman's navbox does (every
Freddie Hubbard, David Murray and Coleman Hawkins album page); those are
rejected, because the album's own page never credits him.

**Half his own records have no Wikipedia article** — most of the 1970s and
everything after 1998 except *Khepera*: exactly the records his interview is
about. They are in the discography from his list, without personnel; 22 of
them got a MusicBrainz id (and so a sleeve) by exact title match against his
own release groups.

## Read this before building the page

1. **Every witness row carries a `caution`** (19 of 23). Read them. Orrin
   Keepnews's lead line is *Miles Davis's* remark, reported — caption it as
   Miles's. Wendy Oxenhorn's *"Him, and Randy Weston and Jimmy Heath"* — "Him"
   is Sonny Rollins. Benny Powell's Morocco story conflates the Gnawa with
   Jajouka and says "Brian Smith" for Brian Jones. Hubert Laws's Weston passage
   directly follows remarks about women that should not be shown with it.
2. **`spoke_themselves: false` is not a witness.** Three rows: Ron Carter's
   Hamilton interview (Weston is only in the archive's front-matter biography),
   Kenny Barron and Lonnie Liston Smith (the name is the interviewer's).
3. **In the Liston interview, many of the good lines about him are Clora
   Bryant's** ("Randy is your horn right now", "Randy likes fourths and
   seconds"). She is the interviewer there; those lines are graded as questions
   and are not in any witness quote.
4. **`name` is corrected, quotes are not.** A quote reads "Paul Robinson" under
   a record whose `name` is Paul Robeson. Check `transcribed_wrong` before
   setting a quote beside a name. Three corrections are low-confidence guesses
   and got no QID: "Walter Rodney" → Wallace Roney, "Frank Gap" → Frank Gant
   (this one did match), "Clifford Jones" (Jordan or Jarvis — left as
   transcribed).
5. **The transcript's dates are not reliable.** He gives both 1991 and 1981 for
   the Boston Pops concert; Jenkins dates the NEA Jazz Masters award to 2003
   where the transcript's own header says 2001; the header gives his death as 1
   February 2018 (it was 1 September); he says he was 17 when *Body and Soul*
   came out (he was 13). 49 of 55 timeline entries carry a `notes`, and 25 of
   34 records a `discrepancies`. Nothing was silently corrected.
6. **Timeline entries with `stated_by: "jenkins"` and `confirmed_by_weston:
   false` are not his testimony**.
7. **A composer credit is not a session.** 83 releases carry him only on a
   track line. The roster (`discography_personnel.json`) is built from the 53
   records he led or played on only; `compositions.json` covers the other 84.
   That count is a floor: only albums with an article that links to him are
   seen.
8. **`he_said_of_this_record` is his account, not the record's.** He says the
   1997 Montreal blues night "came out on an album called *Volcano*";
   *Volcano Blues* is a 1993 studio record. Show `discrepancies` or leave the
   claim out.
9. **Journey coordinates have a `precision`.** `site` = the place itself;
   `town` = only the city matched (the Five Spot → New York City; the bullring
   → Tangier); `country` = Saint Lucia. The Brooklyn church of the three
   religions is placed on Lafayette Avenue — the transcript does not name it.
   One journey (the 2009 O'Farrill concerts) has no place.
10. **Sensitive material exists.** His account of getting Liston to write again
    (*"I insulted her… called her all kinds of names… She cried a little
    bit"*); his sister's funeral on 11 September 2001, told with a joke
    (*"Only my sister would be buried on a day like today"*). Both are flagged
    in `notes`, not filtered.
11. **His Afrocentric history is his.** The Shang dynasty as "one of the
    original African/Chinese dynasties", the diatonic scale from "the ancient
    Nubian people". These are in `self` and `records` as what he said; a page
    should present them as his beliefs, not as fact.
12. **Check `review_flags` before using a portrait large**, and print
    `attribution` — 90 images require it. 18 are Linked Jazz thumbnails with no
    licence metadata.
13. **Cover art is not free.** 64 sleeves from the Cover Art Archive are in
    `img/a/`, copyrighted and supplied for identification. Using them was an
    explicit editorial call in the earlier builds; it is carried over here on
    the same terms and should be re-decided before publishing. 22 were matched
    by title, not by Wikidata (`musicbrainz_matched_by: "title"`).
14. **Confidence is useless for ranking; `notable` is quota'd.** Same as the
    earlier builds. Rank by `notable`, then relation weight.

## Rebuilding

```sh
./build_all.sh        # every deterministic step, the verification gate, the page bundle
```

It is safe to re-run: the Wikipedia/Wikidata/Commons/MusicBrainz responses are
cached under `discography/cache/`, images already on disk are skipped, and the
judgement outputs are read from the tree. The script's comments mark where each
judgement pass reads its input; if one of those inputs changes, that pass has to
be re-run (a subagent, the spec, the input file) before the merge step after it.

## What was not ported, and what is new

Not ported: the Liston page's timeline lanes (`lanes.json`); the
interviewer-testimony layer (`own_voice.bryant`), because Jenkins is not a
witness; the evaluation of own-interview blocks, which existed only to grade
that testimony.

New here: `own_voice.records` and `own_voice.journeys`;
`shared/places.json` (Wikidata geocoding with a country and distance check);
`compositions.json`; `biography_sources.json`; quotes that span a page break;
MusicBrainz ids by title for un-articled records; `same_person_as` merging and
`transcribed_wrong` in the his-words pass; Liston as a fourth member of
`class_of_1926.json`, with her build's account of him.

## The page

`docs/` is the site: `index.html`, `style.css`, `app.js`, two images that came
with the design (`img/weston.jpg`, Brian McMillen's 1984 photograph from
Commons, CC BY-SA 3.0; `img/linked-jazz.png`, the mark), and everything
`site/build_site_data.py` writes: `data.json`, `transcripts.json`, and the
portraits and sleeves it copies from `img/`. The design is the Linked Jazz
design system (warm paper, one blue, Libre Franklin for the interface,
Newsreader for his words) as laid out in the Design canvas
<https://claude.ai/artifact/YNEwH8V7ZG6isbjWwcUPAV>; the page follows that
canvas section for section.

Sections, and the file each reads:

| section | from |
|---|---|
| hero | `profile.json`, `biography_sources.json` (birth and death), the quote named by `site/editorial.json` (`hero_quote_id`) |
| In his own words | `own_voice.json` → `self`, in the category pass's ten sections; 3 shown per section, then all |
| Journeys | `own_voice.json` → `journeys`: a Leaflet map (OpenStreetMap tiles, loaded from cdnjs) of the 40 geocoded places, point size by precision, each popup opening the card or the passage; then the cards (39 with a quote), 8 shown, then all in transcript order |
| Records | `own_voice.json` → `records` (27 with a quote); plus every record under his name from `discography.json`, with sleeves, each linked to Wikipedia or MusicBrainz and to what he said of it |
| Compositions | `compositions.json`: 27 tunes, who recorded each |
| People in his story | `his_words.json`: the 93 he spoke of with a verified quote, with up to two more lines each |
| Who spoke of him | `witnesses.json` filtered by `site/editorial.json`: 15 passages from 12 people; the lede says 17 spoke and why 5 are not shown |
| Relationships | `people.json`: an SVG of everyone on the page around him, an arrowhead pointing at whoever is spoken of, each node a link to the card |
| Sources, credits | `profile.json`, `shared/images.json` |

Every quote opens in place: the page fetches `transcripts.json` (his interview
whole; each witness's interview as a window around the quoted turn) and shows
the turns around the quote with the quoted words marked, and a link to the
archive's own PDF or object page. No quote links to the transcript reader
(the build refuses if one does). The builder re-verifies every quote it writes
against `own_interview.json` and stops if one fails.

`site/editorial.json` holds the display decisions the data cannot make by rule,
each with a `why` quoting the row's `caution`: three witness rows hidden (Dave
McKenna's height joke, Harold Ousley's half-sentence, Curtis Fuller's garbled
bill), notes under seven others (Keepnews's lead is Miles Davis's remark; Liston
spoke eleven years after her stroke; Oxenhorn's "Him" is Sonny Rollins), and
which second quotes are shown. The hero lede is the only prose on the page not
drawn from a source file.

The search box in the header finds people, tunes, records, journeys and
sections on the page and scrolls to them, opening a list as far as the item.
The page works at 360px; the network drawing scrolls sideways there.

To publish, serve `docs/` as static files. `index.html` carries a hash of each
asset in its URL, so a cached copy is never stale. The repo is
<https://github.com/SemanticLab/weston-centennial>; `.github/workflows/pages.yml`
uploads `docs/` to GitHub Pages on every push to `main` (the repository's Pages
source must be set to "GitHub Actions"). Nothing is built in the action: the
page bundle is produced locally by `build_all.sh` and committed.

## Licence

MIT, see `LICENSE`. The transcripts quoted belong to their archives (the
Smithsonian Jazz Oral History Program and the Hamilton College Fillius Jazz
Archive) and are linked to at source; the photograph and portraits carry their
own Commons licences, listed under "Image credits" on the page.
