#!/usr/bin/env python3
"""Step 4 - turn 4,121 raw personnel credits into identified people.

Three tiers of identification, best first:

  1. wikilink   the credit line linked to an article that Wikidata types as a
                human (Q5). Authoritative. Rejects the traps -- "George Gray /
                Viceroy - cover design" links to "Album cover", not a person.
  2. name-match a credit with no link whose name string exactly matches a name
                already resolved via tier 1 somewhere else in the discography.
                Sidemen are linked on one album and bare text on the next.
  3. corpus     an unlinked name that matches a person in the oral-history
                authority file (wd_people.names), which is already
                QID-reconciled. This is the tier that earns its keep: it is how
                an unlinked sideman becomes joinable to the interviews.

Anything still unidentified keeps its name string and is marked unidentified
rather than dropped -- the roster stays complete and auditable.

Output: discography/raw/personnel_resolved.json
"""

import json
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path

from wiki_common import HUMAN, pageprops, wd_entities

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
LJ = "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite"


def norm(s):
    """Fold for name comparison: strip accents, punctuation, case, nicknames."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\"“”'’]", "", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def load_corpus_names():
    """normalised name -> {qid, label} from the oral-history authority file."""
    out = {}
    con = sqlite3.connect(f"file:{LJ}?mode=ro", uri=True)
    for qid, label, names in con.execute(
            "select qid, label, names from wd_people"):
        cands = [label]
        try:
            cands += json.loads(names or "[]")
        except Exception:  # noqa: BLE001
            pass
        for c in cands:
            n = norm(c)
            # single-token names ("Miles", "Trane") are far too collision-prone
            if n and len(n.split()) >= 2:
                out.setdefault(n, {"qid": qid, "label": label})
    con.close()
    return out


def main():
    albums = json.loads((RAW / "albums.json").read_text(encoding="utf-8"))["albums"]

    link_titles = sorted({p["links"][0]["title"]
                          for a in albums.values() for p in a["personnel"]
                          if p["links"]})
    print(f"tier 1: resolving {len(link_titles)} linked articles ...")
    props = pageprops(link_titles)
    ents = wd_entities([p["qid"] for p in props.values() if p.get("qid")])

    # title -> person record, only where Wikidata says Q5
    by_title = {}
    for t in link_titles:
        p = props.get(t) or {}
        e = ents.get(p.get("qid")) if p.get("qid") else None
        if e and not e.get("missing") and HUMAN in (e.get("P31") or []):
            by_title[t] = {
                "qid": e["qid"], "label": e.get("label") or t,
                "description": e.get("description"),
                "wikipedia": p.get("title"),
                "birth": (e.get("P569") or [None])[0],
                "death": (e.get("P570") or [None])[0],
                "instruments_wd": e.get("P1303") or [],
                "occupations_wd": e.get("P106") or [],
                "image": (e.get("P18") or [None])[0],
            }
    print(f"        {len(by_title)} of {len(link_titles)} are humans (Q5)")

    # tier 2 index: name string -> person, learned from tier 1
    learned = {}
    for a in albums.values():
        for p in a["personnel"]:
            if p["links"] and p["links"][0]["title"] in by_title:
                learned.setdefault(norm(p["name"]), by_title[p["links"][0]["title"]])

    corpus = load_corpus_names()
    print(f"tier 3: {len(corpus)} names in the oral-history authority file")

    people, tiers = {}, Counter()
    for title, a in albums.items():
        for p in a["personnel"]:
            n = norm(p["name"])
            rec, tier = None, "unidentified"
            if p["links"] and p["links"][0]["title"] in by_title:
                rec, tier = by_title[p["links"][0]["title"]], "wikilink"
            elif n in learned:
                rec, tier = learned[n], "name_match"
            elif n in corpus:
                c = corpus[n]
                rec, tier = {"qid": c["qid"], "label": c["label"],
                             "description": None, "wikipedia": None,
                             "birth": None, "death": None,
                             "instruments_wd": [], "occupations_wd": [],
                             "image": None}, "corpus_authority"
            tiers[tier] += 1

            key = rec["qid"] if rec else f"name:{n}"
            if not n:
                continue
            ent = people.setdefault(key, {
                "key": key, "qid": rec["qid"] if rec else None,
                "name": rec["label"] if rec else p["name"],
                "identified_via": tier,
                "description": rec.get("description") if rec else None,
                "wikipedia": rec.get("wikipedia") if rec else None,
                "birth": rec.get("birth") if rec else None,
                "death": rec.get("death") if rec else None,
                "image": rec.get("image") if rec else None,
                "name_variants": set(), "roles": Counter(), "credits": [],
            })
            ent["name_variants"].add(p["name"])
            for r in p["roles"]:
                ent["roles"][r.lower()] += 1
            ent["credits"].append({
                "album": title, "album_qid": a["qid"],
                "roles": p["roles"], "note": p["note"],
                "credit_type": p["credit_type"], "group": p["group"],
            })
            p["person_key"] = key
            p["person_qid"] = rec["qid"] if rec else None
            p["identified_via"] = tier

    for e in people.values():
        e["name_variants"] = sorted(e["name_variants"])
        e["roles"] = dict(e["roles"].most_common())
        e["album_count"] = len({c["album"] for c in e["credits"]})
        e["credit_count"] = len(e["credits"])

    (RAW / "personnel_resolved.json").write_text(
        json.dumps({"count": len(people),
                    "tiers": dict(tiers),
                    "people": people}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    # albums.json now carries person_key on every credit
    (RAW / "albums.json").write_text(
        json.dumps({"count": len(albums), "albums": albums},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    ided = sum(1 for e in people.values() if e["qid"])
    print(f"\n{len(people)} distinct people/credits-holders "
          f"({ided} with a QID, {len(people) - ided} name-only)")
    print("credits by tier:", dict(tiers))
    top = sorted(people.values(), key=lambda e: -e["album_count"])[:15]
    print("\nmost-credited:")
    for e in top:
        print(f"  {e['album_count']:3} albums  {e['name'][:32]:34} "
              f"{e['qid'] or '-':10} {e['identified_via']}")


if __name__ == "__main__":
    main()
