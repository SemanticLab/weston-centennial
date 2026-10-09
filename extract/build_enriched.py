#!/usr/bin/env python3
"""Merge the subagent evaluation chunks back onto the quote windows.

Produces, per subject:
  enriched.json         every evaluated block: window + classification + provenance
  best_quotes.json      the display-ready shortlist (notable 3/2, verbatim-checked)
  false_positives.json  blocks the evaluators rejected, for auditing the alias layer

Safe to run while the evaluation is still in flight — it reports coverage and
merges whatever chunks exist.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# The input flag `target_starts_midsentence` tests whether the block's first
# character is lowercase, so it misses every continuation that resumes on a
# proper noun ("Miles and then became…", "Cunningham…", "Brandeis."). Evaluators
# reported this on nearly every chunk. A far better test is whether the PREVIOUS
# block ended without terminal punctuation -- recomputed here so the published
# data carries a signal the page can trust.
_FOOTER = re.compile(
    r"(?:©\s*Fillius\s+Jazz\s+Archive[^A-Za-z]*(?:-\s*\d+\s*-)?|-\s*\d+\s*-)\s*$", re.I
)
_TERMINAL = ('.', '!', '?', '"', '”', '’', "'", ')', ']', '…')


def _continues_previous(context_before):
    """True when the block before this one ends mid-sentence."""
    if not context_before:
        return False
    prev = (context_before[-1].get("text") or "").strip()
    while True:
        stripped = _FOOTER.sub("", prev).strip()
        if stripped == prev:
            break
        prev = stripped
    return bool(prev) and not prev.endswith(_TERMINAL)

ROOT = Path("/Users/m/git/weston-centennial")
SUBJECTS = {"weston": "Q1371187"}

NET = "https://thisismattmiller.github.io/linked-jazz-2026-network/#wd:"


def main():
    summary = {}

    for subject, qid in SUBJECTS.items():
        indir, outdir = ROOT / subject / "eval_input", ROOT / subject / "eval_output"

        windows, order = {}, []
        for f in sorted(indir.glob("chunk_*.json")):
            for it in json.loads(f.read_text(encoding="utf-8"))["items"]:
                windows[it["block_id"]] = it
                order.append(it["block_id"])

        evals, chunk_top, missing_chunks, dangling_top = {}, [], [], []
        for f in sorted(indir.glob("chunk_*.json")):
            o = outdir / f.name
            if not o.exists():
                missing_chunks.append(f.name)
                continue
            d = json.loads(o.read_text(encoding="utf-8"))
            written = {rec["block_id"] for rec in d["items"]}
            # an interrupted run can leave chunk_top pointing at a block it read
            # but never classified -- drop those rather than trust them
            for bid in (d.get("chunk_top") or []):
                if bid in written:
                    chunk_top.append(bid)
                else:
                    dangling_top.append((f.name, bid))
            for rec in d["items"]:
                evals[rec["block_id"]] = rec

        top_set = set(chunk_top)
        items, bad_quotes = [], []

        for bid in order:
            w, e = windows[bid], evals.get(bid)
            if e is None:
                continue

            pq = e.get("pull_quote")
            if pq and pq not in w["target"]["text"]:
                bad_quotes.append(bid)
                pq = None  # never publish a quote we cannot verify

            items.append(
                {
                    "block_id": bid,
                    "subject": subject,
                    "qid": qid,
                    # --- what was said -------------------------------------
                    "speaker": w["target"]["speaker"],
                    "speaker_role": w["speaker_role"],
                    "own_interview": w.get("own_interview", False),
                    "mention_source": w.get("mention_source"),
                    "text": w["target"]["text"],
                    "pull_quote": pq,
                    "pull_quote_verified": bool(pq),
                    # --- the judgement -------------------------------------
                    "is_about_subject": e.get("is_about_subject"),
                    "mention_kind": e.get("mention_kind"),
                    "quotes_the_subject": e.get("quotes_the_subject"),
                    "stance": e.get("stance"),
                    "stance_strength": e.get("stance_strength"),
                    "stance_target": e.get("stance_target"),
                    "content_type": e.get("content_type") or [],
                    "relationship": e.get("relationship"),
                    "block_is_firsthand": e.get("block_is_firsthand"),
                    "topics": e.get("topics") or [],
                    "summary": e.get("summary"),
                    "notable": e.get("notable"),
                    "is_chunk_top": bid in top_set,
                    "context_changed_reading": e.get("context_changed_reading"),
                    "truncated_target": e.get("truncated_target"),
                    # recomputed, reliable: the previous block ended mid-sentence,
                    # so this block's opening words belong to it
                    "continues_previous_block": _continues_previous(w["context_before"]),
                    "ends_midsentence": w["target_ends_midsentence"],
                    "confidence": e.get("confidence"),
                    "notes": e.get("notes") or "",
                    # --- context + provenance ------------------------------
                    "context_before": w["context_before"],
                    "context_after": w["context_after"],
                    "doc": w["doc"],
                    "doc_id": w["doc_id"],
                    "page": w["page"],
                    "block": w["block"],
                }
            )

        def dist(key):
            return dict(Counter(i[key] for i in items if i[key] is not None).most_common())

        real = [i for i in items if i["is_about_subject"]]
        fps = [i for i in items if not i["is_about_subject"]]

        # display shortlist: real, substantive, verbatim-quotable, ranked
        # Only other people's interviews are evaluated here (see build_context.py);
        # Weston's own words are own_voice.json's job.
        kinds_ok = {"substantive_comment", "quoted_speech"}
        best = [
            i for i in real
            if i["notable"] and i["notable"] >= 2
            and i["mention_kind"] in kinds_ok
            and i["pull_quote"]
        ]
        best.sort(
            key=lambda i: (
                -(i["notable"] or 0),
                not i["is_chunk_top"],
                {"high": 0, "medium": 1, "low": 2}.get(i["confidence"], 3),
                -(i["stance_strength"] or 0),
            )
        )

        ctx = sum(1 for i in items if i["context_changed_reading"])
        content = Counter(c for i in real for c in i["content_type"])
        topics = Counter(t for i in real for t in i["topics"])

        stats = {
            "evaluated": len(items),
            "expected": len(order),
            "coverage_pct": round(100 * len(items) / len(order), 1) if order else 0,
            "chunks_missing": missing_chunks,
            "dangling_chunk_top_refs": dangling_top,
            "about_subject": len(real),
            "false_positives": len(fps),
            "context_changed_reading": ctx,
            "context_changed_pct": round(100 * ctx / len(items), 1) if items else 0,
            "non_verbatim_quotes_dropped": len(bad_quotes),
            "other_interviews": {
                "evaluated": sum(1 for i in items if not i["own_interview"]),
                "about_subject": sum(1 for i in real if not i["own_interview"]),
                "documents": len({i["doc_id"] for i in real if not i["own_interview"]}),
                "by_mention_kind": dict(Counter(
                    i["mention_kind"] for i in items if not i["own_interview"]).most_common()),
                "by_stance": dict(Counter(
                    i["stance"] for i in real if not i["own_interview"] and i["stance"]).most_common()),
                "shortlist": sum(1 for i in best if not i["own_interview"]),
            },
            "fts_supplement": {
                "evaluated": sum(1 for i in items if i["mention_source"] == "fts_supplement"),
                "confirmed_as_him": sum(1 for i in real if i["mention_source"] == "fts_supplement"),
            },
            "by_mention_kind": dist("mention_kind"),
            "by_stance": dist("stance"),
            "by_notable": dist("notable"),
            "by_relationship": dist("relationship"),
            "by_content_type": dict(content.most_common()),
            "top_topics": dict(topics.most_common(40)),
            "shortlist_size": len(best),
        }

        base = {
            "subject": subject, "qid": qid, "network_url": NET + qid,
            "generated_from": "linked_jazz.sqlite + subagent evaluation pass",
        }
        (ROOT / subject / "enriched.json").write_text(
            json.dumps({**base, "count": len(items), "stats": stats, "items": items},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        (ROOT / subject / "best_quotes.json").write_text(
            json.dumps({**base, "count": len(best),
                        "method": "is_about_subject AND notable>=2 AND mention_kind in "
                                  "{substantive_comment, quoted_speech} "
                                  "AND verbatim pull_quote; "
                                  "ranked by notable, chunk_top, confidence, stance_strength",
                        "items": best}, ensure_ascii=False, indent=1), encoding="utf-8")
        (ROOT / subject / "false_positives.json").write_text(
            json.dumps({**base, "count": len(fps),
                        "method": "blocks the evaluators judged not to be about the subject; "
                                  "audit list for the upstream alias layer",
                        "items": [{k: i[k] for k in
                                   ("block_id", "doc_id", "speaker", "text", "notes", "doc",
                                    "mention_source")}
                                  for i in fps]}, ensure_ascii=False, indent=1),
            encoding="utf-8")

        summary[subject] = stats
        print(f"\n=== {subject} ===")
        print(f" evaluated {len(items)}/{len(order)} ({stats['coverage_pct']}%)"
              f"  missing chunks: {len(missing_chunks)}")
        print(f" about-subject {len(real)}   false positives {len(fps)}")
        print(f" context changed reading: {ctx} ({stats['context_changed_pct']}%)")
        print(f" shortlist: {len(best)}   dropped non-verbatim quotes: {len(bad_quotes)}")
        print(f" stance: {stats['by_stance']}")
        print(f" kinds:  {stats['by_mention_kind']}")

    (ROOT / "shared" / "eval_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
