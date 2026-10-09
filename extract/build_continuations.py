#!/usr/bin/env python3
"""Second recall pass: pronoun continuations.

build_answers.py recovers answers to interviewer questions. This recovers the
larger class the evaluators kept reporting: a speaker names the subject once,
then keeps talking about him for several more turns using only "he/him/his".
Name-match extraction captures the first block and drops the rest, which is
often where the actual content is.

Confirmed losses of this shape in the Coltrane / Davis build this was ported from
(all Elvin Jones on Coltrane):
  "he wrote that after those kids got bombed in that church... I just had
   tears running down my face"
  Yusef Lateef quoting Coltrane's Swedish interview
  McCoy Tyner: "He knew the continuation of the music was in the hands of the
   younger guys and he supported that"

Candidates only. A pronoun after a mention of the subject is not guaranteed to
be the subject -- for Weston, "he" silently becomes Monk, Ellington, Dizzy
Gillespie or the speaker's own bandleader. Nothing here is verified; in the
Liston build 2 of the 10 blocks this found survived judgement.
"""

import json
import re
import sqlite3
from pathlib import Path

import os
DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")  # see extract/subject.py
ROOT = Path("/Users/m/git/weston-centennial")
SUBJECTS = {"weston": "Q1371187"}

MAX_FOLLOW = 6        # blocks to walk forward from an anchor
MIN_CHARS = 100       # skip "Yeah." / "Right."
COLLAPSE = re.compile(r"\s+")
PRONOUN = re.compile(r"\b(he|him|his)\b", re.I)
INTERJECTION_CHARS = 60   # an interviewer turn this short does not end the thought
# names that most often steal the pronoun in this corpus, per evaluator reports
RIVALS = re.compile(
    r"\b(Monk|Thelonious|Duke|Ellington|Dizzy|Basie|Max|Miles|Coltrane|Trane|Mingus|"
    r"Bird|Parker|Cecil|Ahmad|Bud|Benny|Booker|Kenny|Coleman|Hawk|Blakey|Quincy|Horace|"
    r"Herbie|Billy|Jimmy|Ron|Orrin|Melba)\b", re.I
)


def collapse(s):
    return COLLAPSE.sub(" ", s).strip() if s else ""


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    summary = {}

    for subject, qid in SUBJECTS.items():
        quotes = json.loads((ROOT / subject / "quotes.json").read_text(encoding="utf-8"))
        mention_blocks = {it["block_id"] for it in quotes["items"]}
        # anchors: blocks where an interviewee (not the interviewer) names the subject
        # ...and never in his own interview, where "he" is somebody else by definition
        anchors = [it for it in quotes["items"]
                   if it.get("speaker_role") == "interviewee" and not it.get("own_interview")]

        # blocks already recovered as question-answers, so we don't double-count
        apath = ROOT / subject / "recovered_answers.json"
        already = set()
        if apath.exists():
            for i in json.loads(apath.read_text(encoding="utf-8"))["items"]:
                already.update(a["block_id"] for a in i["answers"])

        docs = {}
        for a in anchors:
            did = a["src"]["doc_id"]
            if did not in docs:
                docs[did] = [dict(r) for r in con.execute(
                    """SELECT block_id, page, block, type, speaker, text
                         FROM blocks WHERE doc_id=? ORDER BY page, block""", (did,))]

        items, seen = [], set()
        for a in anchors:
            src = a["src"]
            blocks = docs[src["doc_id"]]
            idx = next((i for i, b in enumerate(blocks)
                        if b["block_id"] == a["block_id"]), None)
            if idx is None:
                continue

            anchor_spk = (a.get("speaker") or "").strip().lower()
            follow = []
            for b in blocks[idx + 1: idx + 1 + MAX_FOLLOW]:
                if b["block_id"] in mention_blocks:
                    break            # subject named again -> already captured
                if b["type"] not in ("dialogue", "prose"):
                    continue
                txt = collapse(b["text"])
                spk = (b["speaker"] or "").strip().lower()
                # keep the same speaker's turns, or unlabelled page-break
                # continuations; a different named speaker ends the thought --
                # unless it is only an interjection ("Uh-huh.", "Is that right?")
                if spk and anchor_spk and spk != anchor_spk:
                    if len(txt) <= INTERJECTION_CHARS:
                        continue
                    break
                if len(txt) < MIN_CHARS or not PRONOUN.search(txt):
                    continue
                if b["block_id"] in seen or b["block_id"] in already:
                    continue
                seen.add(b["block_id"])
                rivals = sorted(set(m.group(0) for m in RIVALS.finditer(txt)))
                follow.append({
                    "block_id": b["block_id"],
                    "page": b["page"], "block": b["block"],
                    "speaker": b["speaker"],
                    "speaker_missing": not bool(b["speaker"]),
                    "text": txt,
                    "competing_names": rivals,
                    "pronoun_risk": "high" if rivals else "low",
                    "transcript_url": (
                        f"{src['transcript_url'].split('#')[0]}#b{b['page']}-{b['block']}"
                        if src.get("transcript_url") else None),
                })

            if follow:
                items.append({
                    "subject": subject, "qid": qid,
                    "anchor": {
                        "block_id": a["block_id"], "speaker": a.get("speaker"),
                        "text": a["text"],
                        "transcript_url": src.get("transcript_url"),
                    },
                    "continuations": follow,
                    "src": src,
                    "status": "unevaluated_candidate",
                })

        items.sort(key=lambda i: -sum(len(c["text"]) for c in i["continuations"]))
        n = sum(len(i["continuations"]) for i in items)
        low = sum(1 for i in items for c in i["continuations"]
                  if c["pronoun_risk"] == "low")

        (ROOT / subject / "recovered_continuations.json").write_text(
            json.dumps({
                "subject": subject, "qid": qid,
                "count": len(items), "continuation_blocks": n,
                "low_risk_blocks": low,
                "method": (
                    f"From every interviewee block naming the subject, walk up to {MAX_FOLLOW} "
                    "blocks forward, keeping same-speaker (or unlabelled page-break) "
                    f"dialogue/prose turns of >={MIN_CHARS} chars that contain a he/him/his "
                    "pronoun and do not name the subject again. Stops at a fresh subject mention "
                    f"or at a different named speaker saying more than {INTERJECTION_CHARS} chars "
                    "(shorter turns are interjections and are stepped over). His own interview "
                    "is excluded. `competing_names` lists other people named in the block who "
                    "could own the pronoun and marks those blocks "
                    "pronoun_risk=high. ALL of this is "
                    "UNVERIFIED and must be classified before any of it is published."
                ),
                "items": items,
            }, ensure_ascii=False, indent=1), encoding="utf-8")

        summary[subject] = {"anchors_with_continuations": len(items),
                            "continuation_blocks": n, "low_pronoun_risk": low}
        print(f"{subject}: {len(anchors)} interviewee anchors -> {len(items)} with "
              f"continuations, {n} blocks ({low} low-risk, {n-low} with competing names)")

    (ROOT / "shared" / "recovered_continuations_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    con.close()


if __name__ == "__main__":
    main()
