#!/usr/bin/env python3
"""Merge the subagent's judgements back onto the recovered blocks.

Produces, per subject:
  recovered_evaluated.json  every recovered block + its judgement + provenance
  recovered_best.json       the verified, quotable shortlist ready for the page

The headline number here is the VALIDATION RATE: what fraction of the blocks
that name-matching missed are genuinely about the subject. Anything judged
not-about-subject is kept (with the real referent named) so the miss is
auditable rather than silently dropped.

Safe to run while the classification is still in flight.
"""

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path("/Users/m/git/weston-centennial")
OUT = ROOT / "weston" / "recovered_output.json"
SUBJECTS = {"weston": "Q1371187"}


def main():
    raw = json.loads(OUT.read_text(encoding="utf-8"))
    MODEL_NOTE = (f"{raw.get('judged_by') or 'Claude Opus'} subagent working to "
                  "extract/RECOVERED_SPEC.md; whole set in one pass, with the surrounding "
                  "transcript on both sides of every thread")
    judged, errors = {}, []
    for r in raw["threads"]:
        subject = r["key"].split(":")[0]
        for it in r["items"]:
            # namespaced by subject, as in the two-subject build this came from
            judged[(subject, it["block_id"])] = {
                **it, "_kind": r["kind"], "_key": r["key"]}

    summary = {}
    for subject, qid in SUBJECTS.items():
        # rebuild the block -> (anchor, provenance) map from the recovery files
        meta = {}
        for fname, kind, akey, bkey in (
            ("recovered_answers.json", "answer", "question", "answers"),
            ("recovered_continuations.json", "continuation", "anchor", "continuations"),
        ):
            path = ROOT / subject / fname
            if not path.exists():
                continue
            for it in json.loads(path.read_text(encoding="utf-8"))["items"]:
                for b in it[bkey]:
                    meta[b["block_id"]] = {
                        "source": kind, "anchor": it[akey], "block": b, "src": it["src"]}

        items, missing = [], 0
        for bid, m in sorted(meta.items()):
            j = judged.get((subject, bid))
            if j is None:
                missing += 1
                continue
            b = m["block"]
            pq = j.get("pull_quote")
            if pq and pq not in b["text"]:      # belt and braces
                pq = None
            # the Liston interview carries long transcriber summaries in brackets
            if pq and any(m.start() < b["text"].index(pq) + len(pq) and m.end() > b["text"].index(pq)
                          for m in re.finditer(r"\[[^\]]{26,}\]", b["text"])):
                pq = None
            items.append({
                "block_id": bid,
                "subject": subject,
                "qid": qid,
                "source": m["source"],
                "anchor": {"block_id": m["anchor"]["block_id"],
                           "speaker": m["anchor"].get("speaker"),
                           "text": m["anchor"]["text"]},
                "speaker": b.get("speaker"),
                "speaker_missing": b.get("speaker_missing", not bool(b.get("speaker"))),
                "text": b["text"],
                "competing_names": b.get("competing_names", []),
                "pronoun_risk": b.get("pronoun_risk"),
                # --- judgement ---
                "is_about_subject": j.get("is_about_subject"),
                "subject_confidence": j.get("subject_confidence"),
                "actually_about": j.get("actually_about") or "",
                "mention_kind": j.get("mention_kind"),
                "stance": j.get("stance"),
                "stance_strength": j.get("stance_strength"),
                "content_type": j.get("content_type") or [],
                "block_is_firsthand": j.get("block_is_firsthand"),
                "quotes_the_subject": j.get("quotes_the_subject"),
                "summary": j.get("summary") or "",
                "pull_quote": pq,
                "notable": j.get("notable"),
                "notes": j.get("notes") or "",
                "quote_rejected_non_verbatim": bool(j.get("pull_quote_rejected")),
                "judged_by": "opus_subagent",
                "transcript_url": b.get("transcript_url"),
                "doc_id": m["src"].get("doc_id"),
                "doc": {k: m["src"].get(k) for k in
                        ("title", "collection", "year", "interviewee", "interviewer")},
            })

        real = [i for i in items if i["is_about_subject"]]
        rej = [i for i in items if not i["is_about_subject"]]
        best = [i for i in real
                if i["pull_quote"] and (i["notable"] or 0) >= 2]
        best.sort(key=lambda i: (-(i["notable"] or 0),
                                 {"high": 0, "medium": 1, "low": 2}.get(
                                     i["subject_confidence"], 3),
                                 -(i["stance_strength"] or 0)))

        by_risk = Counter(
            (i["pronoun_risk"] or "n/a", bool(i["is_about_subject"])) for i in items)
        stats = {
            "judged": len(items),
            "awaiting_judgement": missing,
            "about_subject": len(real),
            "validation_rate_pct": round(100 * len(real) / len(items), 1) if items else 0,
            "rejected_not_about_subject": len(rej),
            "by_source": dict(Counter(i["source"] for i in items)),
            "validation_rate_by_source": {
                s: round(100 * sum(1 for i in items if i["source"] == s and i["is_about_subject"])
                         / max(1, sum(1 for i in items if i["source"] == s)), 1)
                for s in ("answer", "continuation")},
            "validation_rate_by_pronoun_risk": {
                f"{k}": round(100 * by_risk[(k, True)] /
                              max(1, by_risk[(k, True)] + by_risk[(k, False)]), 1)
                for k in ("low", "high", "n/a")
                if by_risk[(k, True)] + by_risk[(k, False)]},
            "by_stance": dict(Counter(i["stance"] for i in real if i["stance"])),
            "by_mention_kind": dict(Counter(i["mention_kind"] for i in items)),
            "by_notable": dict(Counter(i["notable"] for i in real)),
            "quotes_rejected_non_verbatim": sum(
                1 for i in items if i["quote_rejected_non_verbatim"]),
            "shortlist": len(best),
            "top_misattributions": dict(Counter(
                i["actually_about"] for i in rej if i["actually_about"]).most_common(12)),
        }

        base = {"subject": subject, "qid": qid, "judged_by": MODEL_NOTE,
                "source": "blocks recovered by build_answers.py + build_continuations.py "
                          "that name-matching never captured"}
        (ROOT / subject / "recovered_evaluated.json").write_text(
            json.dumps({**base, "count": len(items), "stats": stats, "items": items},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        (ROOT / subject / "recovered_best.json").write_text(
            json.dumps({**base, "count": len(best),
                        "method": "is_about_subject AND notable>=2 AND verbatim pull_quote; "
                                  "ranked by notable, subject_confidence, stance_strength",
                        "items": best}, ensure_ascii=False, indent=1), encoding="utf-8")

        summary[subject] = stats
        print(f"\n=== {subject} ===")
        print(f" judged {len(items)}  (awaiting {missing})")
        print(f" genuinely about him: {len(real)} ({stats['validation_rate_pct']}%)"
              f"   rejected: {len(rej)}")
        print(f" validation rate by source: {stats['validation_rate_by_source']}")
        print(f" validation rate by pronoun_risk: {stats['validation_rate_by_pronoun_risk']}")
        print(f" new shortlist quotes: {len(best)}   "
              f"non-verbatim quotes rejected: {stats['quotes_rejected_non_verbatim']}")
        if stats["top_misattributions"]:
            top = list(stats["top_misattributions"].items())[:5]
            print(f" most common real referents: {top}")

    (ROOT / "shared" / "recovered_eval_summary.json").write_text(
        json.dumps({"judged_by": MODEL_NOTE, "thread_errors": len(errors),
                    "subjects": summary}, ensure_ascii=False, indent=1), encoding="utf-8")
    if errors:
        print(f"\n{len(errors)} threads errored")


if __name__ == "__main__":
    main()
