#!/usr/bin/env python3
"""shared/class_of_1926.json -- Weston beside the other three 1926 centennials.

Melba Liston (13 Jan 1926), Randy Weston (6 Apr 1926), Miles Davis (26 May 1926)
and John Coltrane (23 Sep 1926) were born within nine months of each other. The
other three already have a centennial build, read-only here:

    ~/git/linked-jazz-coltrane-davis    coltrane/, davis/
    ~/git/liston-centennial-2026        liston/

The Coltrane / Davis build had to say "there is no direct evidence" because
neither man was ever interviewed. The Liston build could show what she said of
each of them. This one closes a loop none of the others could: Weston and
Liston were partners for forty years and BOTH sat for the Smithsonian -- she in
1996, he in 2009 -- so for that pair the file carries each one's account of the
other, from each one's own interview, judged by each build's own readers.

For each of the three this gathers, from data already built:
  he_said             his_words.json entry for them, if Weston named them
  they_said           (Liston only) her_words.json entry for Weston, from her build
  direct_edge         the Linked Jazz network edge between them, if any
  shared_neighbours   people with an edge to both (from the corpus DB)
  documents_naming_both   interviews whose person layer has both
  shared_releases     releases in both discographies (matched on Wikidata QID)
  shared_roster       people credited on records with both

Nothing here is judged; it is all joins.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
CD_REPO = Path("/Users/m/git/linked-jazz-coltrane-davis")
LISTON_REPO = Path("/Users/m/git/liston-centennial-2026")
OTHERS = {"liston": ("Q274146", "Melba Liston", "1926-01-13", LISTON_REPO / "liston"),
          "davis": ("Q93341", "Miles Davis", "1926-05-26", CD_REPO / "davis"),
          "coltrane": ("Q7346", "John Coltrane", "1926-09-23", CD_REPO / "coltrane")}
SESSION = ("leader", "sideman")


def main():
    con = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    hw = {p["qid"]: p for p in json.loads((D / "his_words.json").read_text(encoding="utf-8"))["items"]
          if p.get("qid")}
    disc = json.loads((D / "discography.json").read_text(encoding="utf-8"))["releases"]
    roster = {p["qid"]: p for p in json.loads(
        (D / "discography_personnel.json").read_text(encoding="utf-8"))["people"] if p["qid"]}
    witnesses = json.loads((D / "witnesses.json").read_text(encoding="utf-8"))["items"]

    def neighbours(node):
        out = {}
        for r in con.execute("SELECT a,b,weight,n FROM edges WHERE a=? OR b=?", (node, node)):
            out[r["b"] if r["a"] == node else r["a"]] = {"weight": r["weight"], "n": r["n"]}
        return out

    mine = neighbours(SUBJ.NODE_ID)
    my_docs = {r["doc_id"] for r in con.execute("SELECT doc_id FROM persons WHERE qid=?", (SUBJ.QID,))}

    out = {}
    for key, (qid, name, born, their_dir) in OTHERS.items():
        node = f"wd:{qid}"
        theirs = neighbours(node)
        both = sorted(set(mine) & set(theirs) - {node, SUBJ.NODE_ID},
                      key=lambda n: -(mine[n]["weight"] + theirs[n]["weight"]))
        labels = {r["node_id"]: dict(r) for r in con.execute(
            f"SELECT node_id,label,qid FROM nodes WHERE node_id IN ({','.join('?' * len(both))})",
            both)} if both else {}
        edge = con.execute(
            "SELECT edge_id,a,b,weight,n,pair_fnv FROM edges WHERE (a=? AND b=?) OR (a=? AND b=?)",
            (node, SUBJ.NODE_ID, SUBJ.NODE_ID, node)).fetchone()
        rels = []
        if edge:
            rels = [dict(r) for r in con.execute(
                "SELECT relation,count,direction FROM edge_relations WHERE edge_id=?",
                (edge["edge_id"],))]
        their_docs = {r["doc_id"] for r in con.execute(
            "SELECT doc_id FROM persons WHERE qid=?", (qid,))}
        docs_both = sorted(my_docs & their_docs)
        doc_rows = [dict(r) for r in con.execute(
            f"SELECT doc_id,title,collection,interviewee,year,transcript_url FROM documents "
            f"WHERE doc_id IN ({','.join('?' * len(docs_both))})", docs_both)] if docs_both else []

        shared_rel, shared_people = [], []
        od = their_dir / "discography.json"
        if od.exists():
            theirs_q = {r["qid"]: r for r in json.loads(od.read_text(encoding="utf-8"))["releases"]
                        if r.get("qid")}
            for r in disc:
                if r["qid"] and r["qid"] in theirs_q:
                    t = theirs_q[r["qid"]]
                    shared_rel.append({"title": r["title"], "qid": r["qid"], "year": r["year"],
                                       "weston_role": r["subject_role"],
                                       "weston_credit": r["subject_credit"]["roles"],
                                       "their_role": t.get("subject_role"),
                                       "their_credit": (t.get("subject_credit") or {}).get("roles"),
                                       "wikipedia_url": r["wikipedia_url"]})
        op = their_dir / "discography_personnel.json"
        if op.exists():
            for p in json.loads(op.read_text(encoding="utf-8"))["people"]:
                m = roster.get(p.get("qid"))
                if m and p["qid"] not in (qid, SUBJ.QID):
                    shared_people.append({"name": m["name"], "qid": m["qid"],
                                          "albums_with_weston": m["album_count"],
                                          "albums_with_them": p["album_count"],
                                          "said_about_weston": m["said_about_subject"],
                                          "said_about_them": p.get("said_about_subject", False),
                                          "weston_spoke_of_them": m["he_spoke_of_them"]})
            shared_people.sort(key=lambda x: -(x["albums_with_weston"] + x["albums_with_them"]))

        h = hw.get(qid)
        rec = {
            "name": name, "qid": qid, "born": born,
            "he_said": ({k: h[k] for k in (
                "relation", "direction", "basis", "who_speaks_of_them", "summary", "one_liner",
                "his_quote", "his_quote_url", "more_his_quotes", "interviewer_quote", "era",
                "notable", "notes")} if h else None),
            "on_his_records": qid in roster,
            "albums_together": roster[qid]["albums"] if qid in roster else [],
            "direct_edge": ({"weight": edge["weight"], "n": edge["n"], "relations": rels,
                             "evidence_url": "https://thisismattmiller.github.io/linked-jazz-2026-network/"
                                             f"ev/{edge['pair_fnv'][:2]}/{edge['pair_fnv']}.json"}
                            if edge else None),
            "shared_neighbours": {
                "count": len(both),
                "jaccard": round(len(both) / max(1, len(set(mine) | set(theirs))), 4),
                "weston_neighbours": len(mine), "their_neighbours": len(theirs),
                "top": [{"node_id": n, "label": labels.get(n, {}).get("label"),
                         "qid": labels.get(n, {}).get("qid"),
                         "weston_weight": mine[n]["weight"], "their_weight": theirs[n]["weight"]}
                        for n in both[:40]]},
            "documents_naming_both": {"count": len(doc_rows), "items": doc_rows},
            "shared_releases": {"count": len(shared_rel),
                                "sessions_together": sum(1 for r in shared_rel
                                                         if r["weston_role"] in SESSION),
                                "items": shared_rel, "available": od.exists()},
            "shared_roster": {"count": len(shared_people), "items": shared_people[:80],
                              "available": op.exists()},
        }

        if key == "liston":
            # her account of him, from HER interview, judged by her build's readers
            hp = their_dir / "her_words.json"
            if hp.exists():
                she = next((p for p in json.loads(hp.read_text(encoding="utf-8"))["items"]
                            if p.get("qid") == SUBJ.QID), None)
                rec["they_said"] = ({k: she.get(k) for k in (
                    "relation", "direction", "basis", "tie", "era", "summary", "one_liner",
                    "her_quote", "her_quote_url", "more_her_quotes", "stance", "notable", "notes")}
                    | {"source": "~/git/liston-centennial-2026/liston/her_words.json",
                       "interview": "Smithsonian Jazz Oral History, 4-5 December 1996"}) if she else None
            # ...and how each build's witness pass rendered the other
            wp = their_dir / "witnesses.json"
            if wp.exists():
                w = next((r for r in json.loads(wp.read_text(encoding="utf-8"))["items"]
                          if r.get("qid") == SUBJ.QID), None)
                rec["weston_as_her_witness"] = ({k: w.get(k) for k in (
                    "relation", "one_liner", "summary", "lead_quote", "lead_url", "second_quote",
                    "caution", "notable")} | {"source": "~/git/liston-centennial-2026/liston/witnesses.json"}
                    ) if w else None
            mw = next((r for r in witnesses if r.get("qid") == qid), None)
            rec["liston_as_his_witness"] = ({k: mw.get(k) for k in (
                "relation", "one_liner", "summary", "lead_quote", "lead_url", "second_quote",
                "caution", "notable")} | {"source": "weston/witnesses.json"}) if mw else None

        out[key] = rec
        print(f"{name}: he_said={'yes' if h else 'no'} edge={'yes' if edge else 'no'} "
              f"shared neighbours={len(both)} (J={rec['shared_neighbours']['jaccard']}) "
              f"docs naming both={len(doc_rows)} shared releases={len(shared_rel)} "
              f"({rec['shared_releases']['sessions_together']} sessions) "
              f"shared roster={len(shared_people)}")
        if h:
            print(f"   he said: relation={h['relation']} basis={h['basis']} quote={(h['his_quote'] or '')[:110]!r}")
        if rec.get("they_said"):
            print(f"   she said: {(rec['they_said']['her_quote'] or '')[:110]!r}")

    (ROOT / "shared" / "class_of_1926.json").write_text(json.dumps({
        "subject": SUBJ.KEY, "qid": SUBJ.QID,
        "generated_from": "linked_jazz.sqlite + this repo + ~/git/linked-jazz-coltrane-davis + "
                          "~/git/liston-centennial-2026 (both read-only)",
        "note": "Four jazz musicians born in 1926. All joins; nothing judged here. he_said comes "
                "from his_words.json; liston.they_said and liston.weston_as_her_witness come from "
                "the Liston build's judged files. shared_releases counts every release in both "
                "discographies, including ones that merely carry a tune of his -- "
                "sessions_together counts only those he led or played on.",
        "weston": {"name": SUBJ.NAME, "qid": SUBJ.QID, "born": SUBJ.BORN},
        "others": out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    con.close()


if __name__ == "__main__":
    main()
