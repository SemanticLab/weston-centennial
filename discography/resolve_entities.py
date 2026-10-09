#!/usr/bin/env python3
"""Step 2 - resolve every harvested link to a Wikidata entity and type it.

The discography pages link to a mix of releases, people, record labels, venues,
instruments and stray concepts ("Album cover" turns up as the first link of a
personnel line reading "George Gray / Viceroy - cover design"). Rather than
guess from cell position, ask Wikidata what each article IS via P31.

Output: discography/raw/entities.json - every link, its QID, and a bucket:
  release | person | label | other | unresolved
"""

import json
from collections import Counter
from pathlib import Path

from wiki_common import (COMPOSITION_CLASSES, GROUP_CLASSES, HUMAN,
                         RELEASE_CLASSES, pageprops, wd_entities)

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
SUBJECTS = ("weston",)

# P31 values for things that are clearly not works or people.
LABEL_CLASSES = {"Q18127": "record label", "Q1762059": "film production company",
                 "Q4830453": "business", "Q891723": "public company"}


def bucket(ent):
    if ent is None or ent.get("missing"):
        return "unresolved"
    p31 = set(ent.get("P31") or [])
    if p31 & set(RELEASE_CLASSES):
        return "release"
    if HUMAN in p31:
        return "person"
    if p31 & set(GROUP_CLASSES):
        return "group"
    if p31 & set(COMPOSITION_CLASSES):
        return "composition"
    if p31 & set(LABEL_CLASSES):
        return "label"
    return "other"


VOCAB = {**RELEASE_CLASSES, **LABEL_CLASSES, **COMPOSITION_CLASSES, **GROUP_CLASSES,
         HUMAN: "human"}


def main():
    titles, where = [], {}
    for subject in SUBJECTS:
        d = json.loads((RAW / f"{subject}_rows.json").read_text(encoding="utf-8"))
        for r in d["rows"]:
            for c in r["cells"]:
                for l in c["links"]:
                    t = l["title"]
                    titles.append(t)
                    where.setdefault(t, []).append(
                        {"subject": subject, "section": r["section"],
                         "section_path": r["section_path"],
                         "header": c["header"], "col": c["col"],
                         "is_row_header": c["is_row_header"],
                         "row_text": c["text"][:200],
                         "table": r["table"], "row": r["row"],
                         # where the row came from and, for a discography
                         # bullet, what the bullet itself says
                         "source": r.get("source"), "group": r.get("group"),
                         "italic": l.get("italic"),
                         "year": r.get("year"), "title_text": r.get("title_text"),
                         "leader_text": r.get("leader_text"),
                         "label_text": r.get("label_text"),
                         "note_text": r.get("note_text")})

    titles = list(dict.fromkeys(titles))
    print(f"resolving {len(titles)} distinct article titles ...")
    props = pageprops(titles)

    qids = [p["qid"] for p in props.values() if p.get("qid")]
    print(f"fetching {len(set(qids))} Wikidata entities ...")
    ents = wd_entities(qids)

    out = {}
    for t in titles:
        p = props.get(t) or {}
        ent = ents.get(p.get("qid")) if p.get("qid") else None
        b = bucket(ent)
        out[t] = {
            "requested_title": t,
            "title": p.get("title") or t,
            "redirected": (p.get("title") or t) != t,
            "qid": p.get("qid"),
            "bucket": b,
            "label": (ent or {}).get("label"),
            "description": (ent or {}).get("description"),
            "P31": (ent or {}).get("P31") or [],
            "classes": [VOCAB.get(c, c) for c in ((ent or {}).get("P31") or [])],
            "performers": (ent or {}).get("P175") or [],
            "labels_p264": (ent or {}).get("P264") or [],
            "publication_dates": (ent or {}).get("P577") or [],
            "occupations": (ent or {}).get("P106") or [],
            "instruments": (ent or {}).get("P1303") or [],
            "birth": ((ent or {}).get("P569") or [None])[0],
            "death": ((ent or {}).get("P570") or [None])[0],
            "image": ((ent or {}).get("P18") or [None])[0],
            "musicbrainz": ((ent or {}).get("P436") or [None])[0],
            "seen_in": where[t],
        }

    (RAW / "entities.json").write_text(
        json.dumps({"count": len(out), "entities": out}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    c = Counter(v["bucket"] for v in out.values())
    print("\nbuckets:", dict(c))
    print("\nunresolved / other (spot-check these):")
    for t, v in out.items():
        if v["bucket"] in ("unresolved", "other"):
            print(f"  [{v['bucket']:10}] {t[:52]:54} {v['qid'] or '-':10} "
                  f"{(v['description'] or '')[:50]}")


if __name__ == "__main__":
    main()
