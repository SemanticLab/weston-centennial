# Recovered-block spec — is this pronoun still Randy Weston?

Project root: `/Users/m/git/weston-centennial`

You are judging transcript passages from jazz oral-history interviews for a
centennial web page about **Randy Weston** (pianist, composer, bandleader;
Brooklyn, 1926–2018).

## Input — `weston/recovered_input.json`

The file's `items[]` is a list of **threads**. Each thread hangs off an `anchor`
block that named Weston. The blocks in `blocks_to_judge` come after that anchor
and **do not name him themselves** — they say only "he / him / his", or they are
the answer to a question about him. Each thread gives you:

```
kind                    answer | continuation
anchor_is               what the anchor block is
doc                     the interview: title, interviewee, interviewer, year
context_before_anchor   the 6 blocks before the anchor
anchor                  the block that named him
thread                  every block from the anchor to the last judged block, in
                        order; judge_this marks the ones you must classify
context_after           the 3 blocks after
blocks_to_judge         the blocks to classify (text is authoritative here);
                        competing_names = other names in the block that may
                        own the pronoun
```

Eleven of the threads come from **Melba Liston's** interview (Smithsonian,
1996). She was Weston's arranger for forty years; her interviewer, `Bryant`, is
the trumpeter Clora Bryant. Liston had a stroke in 1985 and her answers are
short. In that transcript **long square-bracketed passages are the
transcriber's summaries, not speech** (*"[Liston cannot recall …]"*) — never
quote them. A short answer of hers to a direct question about Weston is exactly
what this pass exists to recover: do not dismiss it for being short.

## Your central job

Decide, for each block in `blocks_to_judge`, whether it is **really still about
Randy Weston**.

**Be skeptical.** In the builds this was ported from, four or five in six
recovered blocks turned out to be about someone else: the interviewer names the
subject in passing and then asks about something different; "he" moves on to
another man just named (Thelonious Monk, Duke Ellington, Dizzy Gillespie, Max
Roach, the speaker's own bandleader); or the speaker returns to their own story. If the block is about someone
else, say who. If you cannot tell who "he" is, say so. A wrong "yes" puts a
misattributed quote on a public page; a wrong "no" only loses one quote.

Use only the text you are given. Outside knowledge is fine for recognising a
name or a record title, not for deciding what a speaker meant.

## Output — `weston/recovered_output.json`

```json
{"subject": "weston", "judged_by": "<your model>", "threads": [
  {"key": "<copied from the thread>", "kind": "<copied>", "anchor_block_id": <int>,
   "items": [ { ...one per block in blocks_to_judge, same order... } ]}
]}
```

Each item:

```json
{"block_id": 123,
 "is_about_subject": true,
 "subject_confidence": "high",
 "actually_about": "",
 "mention_kind": "substantive_comment",
 "stance": "positive",
 "stance_strength": 2,
 "content_type": ["personal_memory", "working_relationship"],
 "block_is_firsthand": true,
 "quotes_the_subject": false,
 "summary": "One sentence, past tense, naming the speaker by surname.",
 "pull_quote": "an EXACT contiguous substring of that block's text, or null",
 "notable": 1,
 "notes": ""}
```

- `subject_confidence`: `high` | `medium` | `low`
- `actually_about`: who it is really about; empty string when `is_about_subject` is true
- `mention_kind`: `substantive_comment` | `quoted_speech` | `passing_reference` |
  `anecdote_continuation` | `not_about_subject`
- `stance`: `positive` | `negative` | `mixed` | `neutral` | `null`
- `stance_strength`: 0–3
- `content_type`: any of `personal_memory`, `anecdote`, `musical_assessment`,
  `influence`, `legacy_influence`, `mentorship`, `biographical_fact`, `hearsay`,
  `comparison`, `character_description`, `working_relationship`,
  `composition`, `bandleading`, `africa`, `business`, `humor`, `criticism`,
  `historical_context`
- `notable` 0–3: 3 = vivid and quotable enough to set under a photograph. Most
  blocks are 0–1. Be harsh.
- `notes`: flag ambiguous pronouns, garbled text, anything a human should check.

If `is_about_subject` is false: `mention_kind: "not_about_subject"`, `stance:
null`, `stance_strength: 0`, `content_type: []`, `summary: ""`, `pull_quote:
null`, `notable: 0`, and name the real subject in `actually_about`.

## Rules

- `pull_quote` MUST be copied character-for-character from the block's `text` in
  `blocks_to_judge`. No ellipsis, no paraphrase, no reordering, no fixing typos.
  `null` if nothing is cleanly quotable. This is checked programmatically.
- Do not repair transcript errors, OCR garble, or "(?)" markers.
- No `pull_quote` may overlap a `[...]` span longer than 25 characters.
- Every thread in the input appears in the output with exactly as many items as
  it has `blocks_to_judge`, in the same order, `block_id` copied.
- Write the file with a short Python script (`uv run --python 3.14 python
  <script>`); keep any helper script in the scratchpad directory you were given.
  Write nothing else inside the project. Do not run git commands.
- **Validate before finishing**: the output parses; thread keys and counts match
  the input; every non-null `pull_quote` is an exact substring of its block.
