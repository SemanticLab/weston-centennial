# Category spec — sorting the own-voice pull quotes

Project root: `/Users/m/git/weston-centennial`

Randy Weston (pianist, composer, bandleader; Brooklyn, 1926–2018) gave one
oral-history interview that is in this corpus: the Smithsonian Jazz Oral History
Program, 30 October 2009, interviewed by Willard Jenkins. A centennial web page
will be built from it. An earlier reading pass cut 129 verbatim pull quotes out
of that interview. The page will show them in sections, and each quote has to
sit in exactly one section. This pass decides the sections and sorts the quotes
into them.

## Read this before anything else

1. **It is a sequel, not a life story.** Jenkins opens with "since the last
   oral history a lot has happened"; the talk covers roughly 1997–2009 (the
   Verve records, the Gnawa, Egypt, Japan, his marriage) and reaches back only
   when Weston chooses to. The sections have to fit what he actually talks
   about — do not design a biography's chapters.
2. **He talks in long paragraphs.** Each pull quote is a cut from one; several
   quotes come from the same turn. Categorise the cut, not the turn.
3. **The transcript spells by ear** ("Louie Armstrong", "Paul Robinson" for
   Robeson, "Dorothy Dandridge" where Donegan is surely meant). Read through it.

## Your input

`weston/category_input.json` — `items[]`, in transcript order:

| field | meaning |
|---|---|
| `id` | the key (`q001`… single-block quotes, `j01`… quotes that cross a page break); unique |
| `pull_quote` | the quote the page will show — **this is what you categorise** |
| `question` | Jenkins's question that set the turn off |
| `block_text` | the whole turn (or the two page-halves of it) the quote was cut from |
| `summary` | one sentence from the earlier pass saying what the line is about |
| `prompted_by`, `period` | what he was answering, and when the thing happened |
| `theme` | the earlier pass's multi-label tags — a hint, not a decision |
| `notable` | 1–3, how good the earlier pass thought the line was |

Read the whole file before deciding anything.

## What a category is

A category is a **section of the page a reader would choose to open**. It is
about **subject matter** — what the line is about — not about tone, quality,
length or how good it is.

- **Between 7 and 10 categories.**
- **Every quote gets exactly one primary category.** No "other", no
  "miscellaneous", no catch-all for lines that show his character: a line that
  shows who he is is still a line *about something* (his teacher, his shoes at
  the shrine, his father), and it goes there.
- **Balance.** No category should hold more than about a fifth of the quotes,
  and none fewer than about eight. If a subject is too thin to stand, fold it
  into its nearest neighbour; if one is swallowing everything, split it. Check
  the balance of the `notable >= 2` quotes too: a section whose lines are all
  graded 1 will be empty on the page.
- **Categorise the pull quote in its exchange**, not the whole block.
- **Subject over setting.** A line about what music is, said while describing a
  concert in a church, is about music if the idea is the point and about the
  concert if the occasion is the point. Ask: what would a reader who opened
  this section expect to find?
- **His ideas and his stories are different sections.** Much of what he says is
  a belief (Africa as the source, the ancestors, music as a spiritual language)
  and much is a story (the shrine, the donkeys, the wedding). A scheme that
  puts all the beliefs in one section and all the stories in another has not
  done the work: find the subjects inside each.
- A **secondary** category is allowed when a quote would be equally at home in
  a second section. Use it sparingly — fewer than a third of quotes.

---

## Pass A — design the scheme

Write `weston/own_voice_output/category_scheme.json`:

```json
{
 "categories": [
  {
   "key": "snake_case_key",
   "label": "One to three words, as a section heading",
   "definition": "One or two sentences: what belongs here.",
   "includes": ["kinds of line that belong", "..."],
   "excludes": ["kinds of line that look as if they belong but go elsewhere, and where"],
   "expected": 0
  }
 ],
 "order_rationale": "Why the categories are in this order.",
 "boundary_rules": [
  "When a line is both X and Y, it goes to ... because ..."
 ],
 "notes": "Anything the sorters need to know."
}
```

- `categories` is in the **order the page should show them**.
- `label` is what a visitor reads. Plain words; no colons, no puns.
- `includes` / `excludes` describe **kinds** of line. Do **not** cite ids or
  quote the input: two readers will sort the quotes independently from your
  definitions, and examples drawn from the data would decide their answers for
  them.
- `boundary_rules` are where the work is. Find every pair of categories a line
  could fall between and say which way it goes.
- `expected` is your rough count, so the balance rule can be checked.

Before you finish, walk the whole input once more against your scheme and
confirm that every quote has one clear home.

---

## Pass B — sort the quotes

You are given the scheme (`weston/own_voice_output/category_scheme.json`). You
may not change it. Write the file named in your instructions:

```json
{
 "items": [
  {
   "id": "q001",
   "category": "key",
   "secondary": "key or null",
   "confidence": "high | medium | low",
   "reason": "A short clause: why this section. Required when confidence is not high or a boundary rule decided it."
  }
 ],
 "scheme_problems": ["Any quote kinds the scheme has no clear home for, or rules that conflict."]
}
```

- One entry for **every** `id` in the input.
- `category` and `secondary` must be keys from the scheme. `secondary` is null
  unless the quote is equally at home in a second section.
- Work from the definitions and boundary rules, quote by quote. Do not sort by
  page position or by what the neighbouring quotes got.

---

## Pass C — settle the disagreements

Two readers sorted the quotes independently. You are given the scheme, the
input, and `weston/own_voice_output/category_disagreements.json` — the quotes
where their primary categories differ, each with both readers' answers and
reasons. For each, read the quote in its exchange and decide. You may choose
either reader's answer or, rarely, a third category.

The two readers work from the same boundary rules, so they can agree on a quote
and both be uneasy about it. Pass C therefore also reviews every quote that
either reader marked below `high` confidence or named in `scheme_problems`
(`category_a.json`, `category_b.json`). For those the test is the one the
scheme itself sets — *what would a reader who opened this section expect to
find?* — and a boundary rule that sends a line somewhere its own words do not
belong may be overruled for that line. Leave a quote out of your output if the
readers' answer should stand; include it only to change the primary category
(`sided_with: "neither"`).

Write `weston/own_voice_output/category_adjudicated.json`:

```json
{
 "items": [
  {
   "id": "q001",
   "category": "key",
   "secondary": "key or null",
   "sided_with": "a | b | neither",
   "reason": "One sentence."
  }
 ],
 "scheme_problems": ["Patterns in the disagreements that point at a fault in the scheme."]
}
```

## Rules for all passes

- Write your output with a short Python script run via `uv run --python 3.14
  python <script>`, kept in the scratchpad directory you were given. Write
  nothing inside the project except the one output file you were assigned. Do
  not run git commands.
- Validate before finishing: the file parses; every `category` / `secondary`
  is a key of the scheme; (Pass B) every input `id` appears exactly once.
