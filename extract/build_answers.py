#!/usr/bin/env python3
"""Recover the answers that the mention-based extraction never captured.

Multiple evaluation agents independently reported the same recall gap: when an
interviewer asks "How about John Coltrane?" (the example is from the build this
was ported from) and the musician answers without
ever repeating the name, that answer contains no surface form, so the person
layer never indexes it and it is absent from quotes.json. The question is
captured; the payload is not.

Confirmed misses of exactly this shape:
  Kenny Davern  — "Well I never really cared for his playing. I never cared
                   for his sound." (the corpus's sharpest Coltrane dissent)
  Chuck Israels — "one of the respected tenor players of the day, not the icon
                   that he later became"
  Wendell Harrison — "John is an experience... The sound is bigger than all of us"

This script walks forward from every interviewer-spoken block that DOES mention
the subject and collects the answering turns that do NOT, emitting them as
candidate quotes for evaluation.
"""

import json
import re
import sqlite3
from pathlib import Path

import os
DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")  # see extract/subject.py
ROOT = Path("/Users/m/git/weston-centennial")
SUBJECTS = {"weston": "Q1371187"}

MAX_ANSWER_BLOCKS = 4      # how far past the question to follow
MIN_CHARS = 80             # ignore "Yeah." / "Right."
COLLAPSE = re.compile(r"\s+")


def collapse(s):
    return COLLAPSE.sub(" ", s).strip() if s else ""


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out_summary = {}

    for subject, qid in SUBJECTS.items():
        qpath = ROOT / subject / "quotes.json"
        if not qpath.exists():
            raise SystemExit(f"missing {qpath}; run build_quotes.py first")
        quotes = json.loads(qpath.read_text(encoding="utf-8"))

        # interviewer-spoken blocks that mention the subject = the questions
        # ...outside his own interview: there every answer is Weston speaking, which
        # the own-interview passes read whole rather than by window
        questions = [
            it for it in quotes["items"]
            if it.get("speaker_role") == "interviewer" and not it.get("own_interview")
        ]
        # every block already attributed to the subject anywhere in the corpus
        mention_blocks = {it["block_id"] for it in quotes["items"]}

        docs = {}
        for q in questions:
            did = q["src"]["doc_id"]
            if did not in docs:
                docs[did] = [
                    dict(r) for r in con.execute(
                        """SELECT block_id, page, block, type, speaker, text
                             FROM blocks WHERE doc_id=? ORDER BY page, block""",
                        (did,),
                    )
                ]

        items, seen = [], set()
        for q in questions:
            src = q["src"]
            blocks = docs[src["doc_id"]]
            idx = next(
                (i for i, b in enumerate(blocks) if b["block_id"] == q["block_id"]), None
            )
            if idx is None:
                continue

            qspk = (q.get("speaker") or "").strip().lower()
            answers = []
            for b in blocks[idx + 1: idx + 1 + MAX_ANSWER_BLOCKS]:
                # stop once the interviewer speaks again — the answer is over
                spk = (b["speaker"] or "").strip().lower()
                if spk and qspk and spk == qspk and answers:
                    break
                if b["block_id"] in mention_blocks:
                    continue          # already captured by the person layer
                if b["type"] not in ("dialogue", "prose"):
                    continue
                txt = collapse(b["text"])
                if len(txt) < MIN_CHARS:
                    continue
                if b["block_id"] in seen:
                    continue
                seen.add(b["block_id"])
                answers.append(
                    {
                        "block_id": b["block_id"],
                        "page": b["page"], "block": b["block"],
                        "speaker": b["speaker"], "text": txt,
                        "transcript_url": (
                            f"{src['transcript_url'].split('#')[0]}#b{b['page']}-{b['block']}"
                            if src.get("transcript_url") else None
                        ),
                    }
                )

            if answers:
                items.append(
                    {
                        "subject": subject,
                        "qid": qid,
                        "question": {
                            "block_id": q["block_id"],
                            "speaker": q.get("speaker"),
                            "text": q["text"],
                            "transcript_url": src.get("transcript_url"),
                        },
                        "answers": answers,
                        "src": src,
                        "status": "unevaluated_candidate",
                    }
                )

        items.sort(key=lambda i: -sum(len(a["text"]) for a in i["answers"]))
        n_ans = sum(len(i["answers"]) for i in items)

        path = ROOT / subject / "recovered_answers.json"
        path.write_text(
            json.dumps(
                {
                    "subject": subject, "qid": qid,
                    "count": len(items), "answer_blocks": n_ans,
                    "method": (
                        "For every interviewer-spoken block that mentions the subject, the "
                        f"next {MAX_ANSWER_BLOCKS} blocks are collected, keeping dialogue/prose "
                        f"turns of >={MIN_CHARS} chars that are NOT already attributed to the "
                        "subject by the person layer, stopping when the interviewer speaks "
                        "again. These are CANDIDATES: the answer to a question about the "
                        "subject is usually but not always about the subject. Nothing here has "
                        "been evaluated — treat as unverified until classified."
                    ),
                    "items": items,
                },
                ensure_ascii=False, indent=1,
            ),
            encoding="utf-8",
        )
        out_summary[subject] = {"questions_with_answers": len(items),
                                "recovered_answer_blocks": n_ans}
        print(f"{subject}: {len(questions)} interviewer questions -> "
              f"{len(items)} with recoverable answers, {n_ans} new answer blocks")

    (ROOT / "shared" / "recovered_answers_summary.json").write_text(
        json.dumps(out_summary, ensure_ascii=False, indent=1), encoding="utf-8")
    con.close()


if __name__ == "__main__":
    main()
