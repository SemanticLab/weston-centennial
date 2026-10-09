#!/bin/sh
# Rebuild every deterministic layer, in dependency order.
#
# The judgement passes are NOT run from here -- they are Claude Opus subagents
# working to the specs in extract/*_SPEC.md, and their outputs are checked into
# the tree:
#     weston/eval_output/chunk_*.json          (EVAL_SPEC.md)
#     weston/recovered_output.json             (RECOVERED_SPEC.md)
#     weston/his_words_output/chunk_*.json     (HIS_WORDS_SPEC.md)
#     weston/own_voice_output/self.json        (OWN_VOICE_SPEC.md, part A)
#     weston/own_voice_output/self_joined.json   (part A follow-up: quotes that
#                                                 run across a page break)
#     weston/own_voice_output/records.json     (part B)
#     weston/own_voice_output/journeys.json    (part C)
#     weston/own_voice_output/missed_people.json (part D)
#     weston/own_voice_output/category_*.json  (CATEGORY_SPEC.md; input from
#                                               extract/build_category_input.py)
#     weston/witness_output.json               (WITNESS_SPEC.md)
#     discography/raw/credit_review_output.json
# Each "-> judge" comment below marks where a pass reads the files just built.
# If an input changes, the pass must be re-run before the merge step after it.
#
# WHICH DATABASE. The judgement passes ran against schema 1 of the corpus
# (2 October 2026), kept as linked_jazz.pre_audit.sqlite. The audited schema 2.1
# (9 October) renumbered every block id and rebuilt the person layer, so the
# judged outputs only line up with inputs built from the DB they were judged
# on. Every step up to the gate therefore reads the pre-audit copy; then
# extract/remap_block_ids.py carries every block id and block text onto the
# current DB, and the verifier and the page read the current DB. To move the
# whole build onto the audited corpus, re-run the judgement passes (see
# README.md) and drop the three lines marked "pre-audit" below.
set -e
cd "$(dirname "$0")"
export LINKED_JAZZ_DB=/Users/m/git/ch-jazz-mashup/linked_jazz.pre_audit.sqlite   # pre-audit

# ---- transcript layers (stdlib only; read-only on linked_jazz.sqlite)
uv run python extract/build_profile_docs.py      # profile / documents / cooccurrence
uv run python extract/build_quotes.py            # every block that may be about him
uv run python extract/build_relationships.py     # upstream relations: others -> him
uv run python extract/build_connections.py       # network edges, communities
uv run python extract/build_nicknames.py         # raw text sweep (recall audit)
uv run python extract/build_context.py           # -> judge: weston/eval_input/
uv run python extract/build_own_interview.py     # -> judge: his_words_input/, own_interview.txt
uv run python extract/build_answers.py           # recovered candidates
uv run python extract/build_continuations.py
uv run python extract/build_recovered_threads.py # -> judge: recovered_input.json

# ---- merge the judgement
uv run python extract/build_enriched.py          # enriched / best_quotes / false_positives
uv run python extract/merge_recovered.py         # recovered_evaluated / recovered_best
uv run python extract/build_his_words.py         # his_words.json
uv run python extract/build_own_voice.py         # own_voice.json (no coordinates yet)
uv run python extract/build_category_input.py    # -> judge: category_input.json
if [ -f weston/own_voice_output/category_b.json ]; then
  uv run python extract/build_category_disagreements.py   # -> judge (pass C)
fi

# ---- outside sources (network; everything cached under discography/cache/)
uv run python discography/harvest_discographies.py
uv run python discography/resolve_entities.py
uv run python discography/fetch_album_pages.py
uv run python discography/parse_albums.py
uv run python discography/resolve_personnel.py
uv run python discography/musicbrainz_release_groups.py
uv run python discography/geocode_places.py      # shared/places.json (needs journeys.json)
uv run python extract/build_own_voice.py         # again, now with coordinates and categories
uv run python discography/build_discography.py   # needs enriched + his_words + own_voice
                                                 # -> judge: raw/credit_review_input.json
uv run python discography/build_biography_sources.py

# ---- witnesses and the people index
uv run python extract/build_witness_input.py     # -> judge: witness_input.json
uv run python extract/build_witnesses.py         # witnesses.json (no portraits yet)
uv run python discography/build_images.py        # shared/images.json
uv run python discography/fetch_cover_art.py     # shared/cover_art.json
uv run python discography/fetch_local_images.py  # img/
uv run python extract/build_witnesses.py         # again, now with portraits; people.json
uv run python extract/build_class_of_1926.py     # shared/class_of_1926.json

# ---- onto the current DB
unset LINKED_JAZZ_DB                                                              # pre-audit
uv run python extract/remap_block_ids.py                                          # pre-audit

# ---- the gate (against the current DB)
uv run python extract/verify_all.py

# ---- the page bundle (docs/data.json, docs/transcripts.json, docs/img/)
uv run python site/build_site_data.py
