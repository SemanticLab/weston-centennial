#!/usr/bin/env python3
"""Expanded-context builder for the evaluation pass.

quotes.json ships a fixed +/-2 block window. That is too thin to tell what a
speaker actually meant, and blocks vary from a few words to 10k chars, so a
fixed block count is the wrong unit. Here the window is budgeted by characters
with a block-count floor:

  before: blocks walking backwards until >=4 blocks AND >=1200 chars,
          hard caps at 8 blocks / 4000 chars (always >=4 blocks if they exist)
  after:  same rule at 2 blocks / 700 chars, caps 4 blocks / 2000 chars

Windows never cross a document boundary. Blocks are ordered by (page, block).

Emits chunk files ready to hand to evaluation subagents.
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")  # see extract/subject.py
ROOT = Path("/Users/m/git/weston-centennial")
CHUNK_SIZE = 60

SUBJECTS = {"weston": "Q1371187"}

BEFORE_MIN_BLOCKS, BEFORE_MIN_CHARS = 4, 1200
BEFORE_MAX_BLOCKS, BEFORE_MAX_CHARS = 8, 4000
AFTER_MIN_BLOCKS, AFTER_MIN_CHARS = 2, 700
AFTER_MAX_BLOCKS, AFTER_MAX_CHARS = 4, 2000
# When the interviewer is the one raising the subject, the answer is what we
# actually want and it can run several blocks — widen the trailing window.
AFTER_Q_MIN_BLOCKS, AFTER_Q_MIN_CHARS = 6, 2200
AFTER_Q_MAX_BLOCKS, AFTER_Q_MAX_CHARS = 8, 5000

TERMINAL = ('.', '!', '?', '"', '”', '’', "'", ')', ']', '…')

# Archive page furniture that trails the actual speech. Left in `text` (we do
# not alter transcript text) but stripped before testing whether a block ends
# mid-sentence — otherwise the footer makes every Hamilton block look truncated.
# 9,715 blocks in the corpus carry the Fillius stamp.
FOOTER = re.compile(
    r"(?:©\s*Fillius\s+Jazz\s+Archive[^A-Za-z]*(?:-\s*\d+\s*-)?|"
    r"Fillius\s+Jazz\s+Archive,\s*Hamilton\s+College[^.]*\.?|"
    r"-\s*\d+\s*-)\s*$",
    re.I,
)


def strip_footer(s):
    prev = None
    while prev != s:
        prev = s
        s = FOOTER.sub("", s).strip()
    return s

COLLAPSE = re.compile(r"\s+")


def collapse(s):
    return COLLAPSE.sub(" ", s).strip() if s else (s or "")


def walk(seq, min_blocks, min_chars, max_blocks, max_chars):
    """Take from seq (already ordered outward from the target) until the
    minimums are met; never exceed the maximums."""
    out, chars = [], 0
    for b in seq:
        if len(out) >= max_blocks or chars >= max_chars:
            break
        if len(out) >= min_blocks and chars >= min_chars:
            break
        out.append(b)
        chars += len(b["text"] or "")
    return out


def main():
    import sys

    # optional subject filter: rebuilding one subject's chunks while agents are
    # still reading the other's must not touch their input files
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only and only not in SUBJECTS:
        raise SystemExit(f"unknown subject {only!r}; expected one of {list(SUBJECTS)}")

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    manifest = {}

    for subject, qid in SUBJECTS.items():
        if only and subject != only:
            continue
        # reuse the six-tier speaker-role resolution already computed by
        # build_quotes.py rather than re-deriving it here
        roles = {}
        qpath = ROOT / subject / "quotes.json"
        if qpath.exists():
            for it in json.loads(qpath.read_text(encoding="utf-8"))["items"]:
                roles[it["block_id"]] = it.get("speaker_role")

        # target blocks: the QID-reconciled person layer PLUS the text hits it
        # missed (see extract/subject.py).
        #
        # His own interview is NOT evaluated here. In the Liston build it was,
        # because her interviewer (Clora Bryant) was a peer whose remarks counted
        # as testimony; Willard Jenkins is not a witness, and what Weston says in
        # that document is read whole by the his-words and own-voice passes.
        tb = SUBJ.target_blocks(con)
        own_ids = {r[0] for r in con.execute(
            "SELECT block_id FROM blocks WHERE doc_id = ?", (SUBJ.OWN_DOC,))}
        tb = {bid: v for bid, v in tb.items() if bid not in own_ids}
        source_of = {bid: src for bid, (_, src) in tb.items()}
        q = ",".join("?" * len(tb))
        targets = con.execute(
            f"SELECT block_id, doc_id, page, block FROM blocks WHERE block_id IN ({q})",
            list(tb),
        ).fetchall()

        doc_ids = sorted({r["doc_id"] for r in targets})

        # load every block of every relevant doc once, in reading order
        docs = {}
        for did in doc_ids:
            rows = con.execute(
                """SELECT block_id, page, block, type, speaker, text
                     FROM blocks WHERE doc_id = ?
                    ORDER BY page, block""",
                (did,),
            ).fetchall()
            docs[did] = [dict(r) for r in rows]

        docmeta = {}
        for did in doc_ids:
            d = con.execute(
                """SELECT doc_id, collection, title, interviewee, interviewer,
                          year, transcript_url, source_url
                     FROM documents WHERE doc_id = ?""",
                (did,),
            ).fetchone()
            ivs = con.execute(
                "SELECT label, qid, node_key FROM doc_interviewees WHERE doc_id=? ORDER BY ord",
                (did,),
            ).fetchall()
            m = dict(d)
            m["doc_interviewees"] = [
                {"label": r["label"], "qid": r["qid"] or None, "node_key": r["node_key"]}
                for r in ivs
            ]
            docmeta[did] = m

        # surface forms this doc used for the subject (helps the evaluator spot
        # alias errors such as "Buhaina" folded into Coltrane)
        forms = {}
        for r in con.execute(
            "SELECT doc_id, surface_forms, canonical FROM persons WHERE qid=?", (qid,)
        ):
            try:
                sf = json.loads(r["surface_forms"] or "[]")
            except Exception:
                sf = []
            forms.setdefault(r["doc_id"], set()).update(sf)
        for bid, (ms, src) in tb.items():
            if src == "fts_supplement":
                for m in ms:
                    forms.setdefault(m["doc_id"], set()).update(json.loads(m["surface_forms"]))

        items = []
        for t in targets:
            did = t["doc_id"]
            blocks = docs[did]
            idx = next(
                (i for i, b in enumerate(blocks) if b["block_id"] == t["block_id"]), None
            )
            if idx is None:
                raise SystemExit(f"block {t['block_id']} not found in doc {did}")

            before = walk(
                list(reversed(blocks[:idx])),
                BEFORE_MIN_BLOCKS, BEFORE_MIN_CHARS,
                BEFORE_MAX_BLOCKS, BEFORE_MAX_CHARS,
            )
            before.reverse()
            is_question = roles.get(t["block_id"]) == "interviewer"
            if is_question:
                after = walk(
                    blocks[idx + 1:],
                    AFTER_Q_MIN_BLOCKS, AFTER_Q_MIN_CHARS,
                    AFTER_Q_MAX_BLOCKS, AFTER_Q_MAX_CHARS,
                )
            else:
                after = walk(
                    blocks[idx + 1:],
                    AFTER_MIN_BLOCKS, AFTER_MIN_CHARS,
                    AFTER_MAX_BLOCKS, AFTER_MAX_CHARS,
                )

            def shape(b):
                return {
                    "block_id": b["block_id"],
                    "page": b["page"],
                    "block": b["block"],
                    "type": b["type"],
                    "speaker": b["speaker"],
                    "text": collapse(b["text"]),
                }

            tgt = blocks[idx]
            dm = docmeta[did]
            items.append(
                {
                    "block_id": t["block_id"],
                    "subject": subject,
                    "qid": qid,
                    "doc_id": did,
                    "page": t["page"],
                    "block": t["block"],
                    "doc": {
                        "title": dm["title"],
                        "collection": dm["collection"],
                        "year": dm["year"],
                        "interviewee_field": dm["interviewee"],
                        "interviewer_field": dm["interviewer"],
                        "doc_interviewees": dm["doc_interviewees"],
                        "transcript_url": (
                            f"{dm['transcript_url']}#b{t['page']}-{t['block']}"
                            if dm["transcript_url"] else None
                        ),
                    },
                    "subject_surface_forms": sorted(forms.get(did, [])),
                    "own_interview": did == SUBJ.OWN_DOC,
                    "mention_source": source_of[t["block_id"]],
                    "speaker_role": roles.get(t["block_id"]),
                    # page-break artifacts: the pilot found target blocks that are
                    # split mid-sentence, where the continuation inverts the meaning
                    "target_starts_midsentence": bool(
                        collapse(tgt["text"]) and collapse(tgt["text"])[0].islower()
                    ),
                    "target_ends_midsentence": bool(
                        strip_footer(collapse(tgt["text"]))
                        and not strip_footer(collapse(tgt["text"])).endswith(TERMINAL)
                    ),
                    "context_before": [shape(b) for b in before],
                    "target": shape(tgt),
                    "context_after": [shape(b) for b in after],
                    "window_chars": sum(
                        len(b["text"] or "") for b in before + [tgt] + after
                    ),
                }
            )

        items.sort(key=lambda i: (i["own_interview"], i["doc_id"], i["page"], i["block"]))

        outdir = ROOT / subject / "eval_input"
        outdir.mkdir(exist_ok=True)
        for old in outdir.glob("chunk_*.json"):
            old.unlink()

        # Split evenly, and never split one interview across two chunks: the
        # evaluator has to keep `relationship` consistent within a document.
        n_chunks = max(1, -(-len(items) // CHUNK_SIZE))
        target = -(-len(items) // n_chunks)
        chunks, cur = [], []
        by_doc = {}
        for i in items:
            by_doc.setdefault(i["doc_id"], []).append(i)
        for did, its in by_doc.items():
            if cur and len(cur) + len(its) > target and len(chunks) < n_chunks - 1:
                chunks.append(cur)
                cur = []
            cur += its
        if cur:
            chunks.append(cur)
        for n, ch in enumerate(chunks, 1):
            (outdir / f"chunk_{n:03d}.json").write_text(
                json.dumps(
                    {"subject": subject, "qid": qid, "chunk": n,
                     "n_chunks": len(chunks), "count": len(ch),
                     "own_interview": False, "items": ch},
                    ensure_ascii=False, indent=1,
                ),
                encoding="utf-8",
            )

        avg_b = sum(len(i["context_before"]) for i in items) / len(items)
        avg_c = sum(i["window_chars"] for i in items) / len(items)
        manifest[subject] = {
            "items": len(items), "chunks": len(chunks), "chunk_size": CHUNK_SIZE,
            "avg_before_blocks": round(avg_b, 2),
            "avg_window_chars": round(avg_c),
        }
        print(
            f"{subject}: {len(items)} items -> {len(chunks)} chunks "
            f"(avg {avg_b:.1f} before-blocks, avg window {avg_c:.0f} chars)"
        )

    # merge, don't clobber, when only one subject was rebuilt
    mpath = ROOT / "extract" / "eval_manifest.json"
    existing = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    existing.update(manifest)
    mpath.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
    con.close()


if __name__ == "__main__":
    main()
