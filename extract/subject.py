#!/usr/bin/env python3
"""The one subject of this repo, and what makes him different from the Melba
Liston build this pipeline was ported from (~/git/liston-centennial-2026).

1. HE WAS INTERVIEWED, BUT THE INTERVIEW IS A SEQUEL. The Smithsonian Jazz Oral
   History Program recorded Randy Weston on 30 October 2009; the interviewer
   was the journalist Willard Jenkins, who was at the time co-writing Weston's
   autobiography (African Rhythms, 2010). Jenkins opens with "since the last
   oral history a lot has happened" -- the transcript covers roughly 1997-2009
   and takes the earlier life as read. It is 20 pages and 111 blocks; Weston
   speaks in long turns (45 turns, ~36k characters), the opposite of Liston's
   post-stroke "Yeah."

   So `OWN_DOC` exists, and the rule from the Liston build is kept: blocks from
   OWN_DOC are flagged `own_interview` and are never counted as "another
   musician talking about him". Unlike Clora Bryant, Jenkins is NOT treated as
   a witness -- he is an interviewer and collaborator, not a bandstand peer --
   so there is no peer-interviewer layer here. His questions are kept as the
   context for Weston's answers.

2. THE NAME-MATCHING IS NEARLY COMPLETE. Weston is reconciled to his QID in 22
   interviews besides his own. A text sweep finds only a handful the person
   layer left behind: "Randy Weston territory." (Kenny Barron), "Randy Western"
   (Billy Taylor's transcript), "Randy [Weston]" with the editor's bracket
   (Liston's), and a bare "Randy" in interviews that already name him in full
   (Benny Powell, Liston). `target_blocks()` adds those back as
   `fts_supplement` candidates; the evaluation pass decides whether each one is
   really him. A bare "Randy" anywhere else is Randy Brecker, Randy Brooks,
   Randy Newman, Zilner Randolph... and is not looked at.
"""

import os
import re

# The corpus. The judgement passes ran against schema 1 of the DB (2 October
# 2026), kept as linked_jazz.pre_audit.sqlite; the audited schema 2.1 (9 October)
# renumbered every block id and rebuilt the person layer, so the steps that
# BUILD the judges' inputs must keep reading the DB they were judged on, or the
# outputs no longer line up. build_all.sh sets LINKED_JAZZ_DB to the pre-audit
# copy for those steps and extract/remap_block_ids.py carries the result onto
# the current DB afterwards. Everything else (the verifier, the page) reads the
# current DB.
DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")
ROOT = "/Users/m/git/weston-centennial"

KEY = "weston"
QID = "Q1371187"
NODE_ID = "wd:Q1371187"
NAME = "Randy Weston"
BORN = "1926-04-06"
DIED = "2018-09-01"
OWN_DOC = "Randy-Weston-Transcription-2020_0"
OWN_DOC_DATE = "2009-10-30"          # documents.year says 2020: that is the PDF's upload year
OWN_DOC_YEAR = 2009

# blocks.speaker for his turns in OWN_DOC, lower-cased
SUBJECT_SPEAKER = "randy weston"

# His interviewer. Not a witness (see the docstring).
INTERVIEWER = {"name": "Willard Jenkins", "speaker_label": "Jenkins", "qid": "Q15449804"}

SUBJECTS = {KEY: QID}

# A text hit that the person layer did not link to his QID. "Weston" alone is
# Paul Weston, Jimmy Weston's (the club), Fitz Weston and a street in Chicago
# far more often than it is him, so the full name is required...
SUPPLEMENT_RE = re.compile(
    r"\bRandy\s+\[?Weston\]?|\bWeston,\s*Randy\b|\bRandy\s+Western\b"
)
# ...except inside an interview the person layer has ALREADY tied to him, where
# a bare "Randy" not followed by another surname is taken as a candidate.
BARE_RE = re.compile(r"\bRandy\b(?!\s+\[?[A-Z])")


def person_layer_blocks(con):
    """block_id -> list of mention dicts, from the QID-reconciled person layer."""
    out = {}
    for r in con.execute(
        """SELECT p.person_id, p.doc_id, p.canonical, p.count AS person_count,
                  p.confidence, p.surface_forms, pm.block_id, pm.start, pm.end
             FROM persons p JOIN person_mentions pm USING(person_id)
            WHERE p.qid = ? AND pm.block_id IS NOT NULL""",
        (QID,),
    ):
        out.setdefault(r["block_id"], []).append(dict(r))
    return out


def supplement_blocks(con, known):
    """block_id -> list of pseudo-mention dicts for text hits outside `known`.

    Never looks inside OWN_DOC: there a "Randy" is Jenkins addressing him.
    """
    import json

    reconciled_docs = {
        r[0] for r in con.execute("SELECT DISTINCT doc_id FROM persons WHERE qid = ?", (QID,))
    }
    out = {}
    rows = con.execute(
        """SELECT b.block_id, b.doc_id, b.text
             FROM blocks_fts JOIN blocks b ON b.block_id = blocks_fts.rowid
            WHERE blocks_fts MATCH 'Randy OR Weston' AND b.doc_id != ?""",
        (OWN_DOC,),
    ).fetchall()
    per_doc = {}
    for r in rows:
        if r["block_id"] in known:
            continue
        text = r["text"] or ""
        hits = list(SUPPLEMENT_RE.finditer(text))
        if r["doc_id"] in reconciled_docs:
            spans = [(m.start(), m.end()) for m in hits]
            hits += [m for m in BARE_RE.finditer(text)
                     if not any(s <= m.start() < e for s, e in spans)]
            hits.sort(key=lambda m: m.start())
        if not hits:
            continue
        per_doc.setdefault(r["doc_id"], []).append((r["block_id"], hits))
    for doc_id, blks in per_doc.items():
        forms = sorted({m.group(0) for _, hits in blks for m in hits})
        n = sum(len(hits) for _, hits in blks)
        for block_id, hits in blks:
            out[block_id] = [
                {
                    "person_id": None,
                    "doc_id": doc_id,
                    "canonical": "Randy Weston (unreconciled text hit)",
                    "person_count": n,
                    "confidence": None,
                    "surface_forms": json.dumps(forms, ensure_ascii=False),
                    "block_id": block_id,
                    "start": m.start(),
                    "end": m.end(),
                }
                for m in hits
            ]
    return out


def target_blocks(con):
    """Every block that may be about him: block_id -> (mentions, source)."""
    pl = person_layer_blocks(con)
    out = {bid: (ms, "person_layer") for bid, ms in pl.items()}
    for bid, ms in supplement_blocks(con, set(pl)).items():
        out[bid] = (ms, "fts_supplement")
    return out
