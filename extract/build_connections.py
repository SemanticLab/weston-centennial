#!/usr/bin/env python3
"""
Build the NETWORK CONNECTIONS layer of the Randy Weston centennial extraction.
(Ported from the Coltrane / Davis build; the two-subject bridge file is gone.)

Outputs
  weston/connections.json
  shared/communities.json

Source: read-only /Users/m/git/ch-jazz-mashup/linked_jazz.sqlite
Conventions: extract/SPEC.md
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")  # see extract/subject.py
OUT_ROOT = "/Users/m/git/weston-centennial"

NETWORK_NODE_URL = "https://thisismattmiller.github.io/linked-jazz-2026-network/#{node_id}"
EVIDENCE_URL = "https://thisismattmiller.github.io/linked-jazz-2026-network/ev/{pfx}/{pair_fnv}.json"

SUBJECTS = {
    "weston": {"qid": "Q1371187", "node_id": "wd:Q1371187", "name": "Randy Weston"},
}

ABSTRACT_CHARS = 400

DIRECTION_METHOD = (
    "edge_relations.direction is stored relative to the edge's lexicographic endpoints "
    "(edges.a < edges.b): 'a_acts' = the a-side node is the actor, 'b_acts' = the b-side "
    "node is the actor, 'mutual' = reciprocal, 'na' = not applicable/undirected. "
    "We normalise to a SUBJECT-relative value in 'direction' as follows: when the subject "
    "node_id == edges.a then a_acts->subject_acts and b_acts->other_acts; when the subject "
    "node_id == edges.b then a_acts->other_acts and b_acts->subject_acts; 'mutual' and 'na' "
    "pass through unchanged. The untouched database value is retained in 'direction_raw', "
    "and 'subject_side' records whether the subject was the a or the b endpoint of that edge."
)

SPEAKER_ROLE_METHOD = (
    "speaker_role is assigned by comparing blocks.speaker against the document's "
    "interviewee/interviewer strings (documents.interviewee, documents.interviewer and every "
    "doc_interviewees.label row). Comparison is case-insensitive on alphabetic tokens of "
    "length >= 3 with common honorifics dropped; a match on any surname-length token "
    "(or an exact normalised string match) wins. Speaker labels that are bare initials "
    "('JD', 'CK') are matched against the initials of the candidate name. Interviewee "
    "(documents.interviewee + all doc_interviewees labels) is tested before interviewer. "
    "No match -> 'unknown'. This is a heuristic; 'unknown' means unmatched, not non-participant."
)

HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "prof", "rev", "sir", "the", "and", "jr", "sr"}


# ---------------------------------------------------------------- helpers


def collapse(text):
    """Collapse whitespace runs; keep None as None."""
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip()


def trim(text, n=ABSTRACT_CHARS):
    if text is None:
        return None
    t = collapse(text)
    if len(t) <= n:
        return t
    cut = t[:n]
    sp = cut.rfind(" ")
    if sp > n * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" ,;:") + "…"


def node_url(node_id):
    return NETWORK_NODE_URL.format(node_id=node_id)


def evidence_url(pair_fnv):
    if not pair_fnv:
        return None
    return EVIDENCE_URL.format(pfx=pair_fnv[:2], pair_fnv=pair_fnv)


def name_tokens(s):
    if not s:
        return set()
    toks = re.findall(r"[a-z]+", s.lower())
    return {t for t in toks if len(t) >= 3 and t not in HONORIFICS}


def norm_name(s):
    if not s:
        return ""
    return " ".join(re.findall(r"[a-z]+", s.lower()))


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    return path


def die(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- db load


con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
cur = con.cursor()
cur2 = con.cursor()  # for queries nested inside an iteration over `cur`

meta = {r["key"] if "key" in r.keys() else r[0]: r[1] for r in cur.execute("SELECT * FROM meta")}
if "evidence_url_pattern" not in meta:
    die("meta table has no evidence_url_pattern - schema surprise")

# communities
COMM = {}
for r in cur.execute("SELECT * FROM communities"):
    d = dict(r)
    kf = d.get("key_figures")
    try:
        d["key_figures"] = json.loads(kf) if kf else []
    except (json.JSONDecodeError, TypeError):
        die(f"communities.key_figures for community {d['community_id']} is not JSON: {kf!r}")
    COMM[d["community_id"]] = d
# schema 1 had 58 communities, the audited schema 2.1 has 71; the count is a
# property of the corpus build, not of this subject
if len(COMM) < 40:
    die(f"expected dozens of communities, got {len(COMM)}")


def comm_label(cid):
    if cid is None:
        return None
    c = COMM.get(cid)
    return c["label"] if c else None


# node_collections index (only fetched per node on demand -> cheap enough in bulk)
NODE_COLLS = defaultdict(list)
for r in cur.execute("SELECT node_id, collection FROM node_collections"):
    NODE_COLLS[r["node_id"]].append(r["collection"])
for v in NODE_COLLS.values():
    v.sort()

# documents index
DOCS = {}
for r in cur.execute(
    "SELECT doc_id, collection, title, interviewee, interviewer, date, year, "
    "source_url, transcript_url FROM documents"
):
    DOCS[r["doc_id"]] = dict(r)

DOC_ITV = defaultdict(list)
for r in cur.execute("SELECT doc_id, ord, node_key, label, qid FROM doc_interviewees ORDER BY doc_id, ord"):
    DOC_ITV[r["doc_id"]].append(dict(r))


def initials(s):
    """Initials of a person name, e.g. 'Clyde Kerr Jr.' -> 'ck'."""
    toks = [t for t in re.findall(r"[A-Za-z]+", s or "") if t.lower() not in HONORIFICS]
    return "".join(t[0].lower() for t in toks)


def _match(speaker, cand):
    if not cand:
        return False
    sp = (speaker or "").strip()
    if norm_name(sp) and norm_name(sp) == norm_name(cand):
        return True
    if name_tokens(sp) & name_tokens(cand):
        return True
    # speaker given as initials ("JD", "CK Jr")
    letters = re.findall(r"[A-Za-z]", sp)
    if sp and not name_tokens(sp) and 2 <= len(letters) <= 3:
        ini = "".join(letters).lower()
        ci = initials(cand)
        if ci and (ini == ci or ini == ci[:2] or ci.startswith(ini)):
            return True
    return False


def speaker_role(doc_id, speaker):
    if not speaker:
        return "unknown"
    doc = DOCS.get(doc_id) or {}
    itv_names = [doc.get("interviewee")] + [x["label"] for x in DOC_ITV.get(doc_id, [])]
    if any(_match(speaker, c) for c in itv_names):
        return "interviewee"
    if _match(speaker, doc.get("interviewer")):
        return "interviewer"
    return "unknown"


def src_block(doc_id, block_id, page, block, speaker=None):
    doc = DOCS.get(doc_id) or {}
    turl = doc.get("transcript_url")
    if turl and page is not None and block is not None:
        turl = f"{turl}#b{page}-{block}"
    return {
        "doc_id": doc_id,
        "block_id": block_id,
        "page": page,
        "block": block,
        "collection": doc.get("collection"),
        "title": doc.get("title"),
        "interviewee": doc.get("interviewee"),
        "interviewer": doc.get("interviewer"),
        "year": doc.get("year"),
        "transcript_url": turl,
        "source_url": doc.get("source_url"),
    }


# ---------------------------------------------------------------- node hydration

_node_cache = {}


def hydrate_node(node_id):
    if node_id in _node_cache:
        return _node_cache[node_id]
    r = cur.execute(
        "SELECT node_id, kind, label, is_interviewee, qid, semlab_id, mentions, docs, "
        "singleton, community, x, y, wd_image_url, semlab_thumb_url "
        "FROM nodes WHERE node_id=?",
        (node_id,),
    ).fetchone()
    if r is None:
        die(f"edge references missing node {node_id}")
    d = dict(r)
    d["community_label"] = comm_label(d["community"])
    d["collections"] = NODE_COLLS.get(node_id, [])
    d["network_url"] = node_url(node_id)
    wd = None
    if d["qid"]:
        w = cur.execute(
            "SELECT qid, label, description, birth, death, wp_title, wp_abstract, image_url, "
            "semlab_id, semlab_thumb_url, mentions, docs FROM wd_people WHERE qid=?",
            (d["qid"],),
        ).fetchone()
        if w is not None:
            wd = dict(w)
            wd["wp_abstract"] = trim(wd["wp_abstract"], ABSTRACT_CHARS)
            wd["description"] = collapse(wd["description"])
            wd["wikipedia_url"] = (
                "https://en.wikipedia.org/wiki/" + wd["wp_title"].replace(" ", "_")
                if wd.get("wp_title")
                else None
            )
            wd["wikidata_url"] = f"https://www.wikidata.org/wiki/{wd['qid']}"
    d["wd_people"] = wd
    _node_cache[node_id] = d
    return d


# ---------------------------------------------------------------- edge helpers


def edge_relations_for(edge_id, subject_side):
    rows = cur.execute(
        "SELECT relation, count, direction FROM edge_relations WHERE edge_id=? "
        "ORDER BY count DESC, relation",
        (edge_id,),
    ).fetchall()
    out = []
    for r in rows:
        raw = r["direction"]
        if raw == "mutual":
            norm = "mutual"
        elif raw == "na" or raw is None:
            norm = "na"
        elif raw == "a_acts":
            norm = "subject_acts" if subject_side == "a" else "other_acts"
        elif raw == "b_acts":
            norm = "other_acts" if subject_side == "a" else "subject_acts"
        else:
            die(f"unknown edge_relations.direction value {raw!r} on edge {edge_id}")
        out.append(
            {
                "relation": r["relation"],
                "count": r["count"],
                "direction": norm,
                "direction_raw": raw,
                "subject_side": subject_side,
            }
        )
    return out


def attested_by(edge_id):
    rows = cur.execute(
        "SELECT DISTINCT rl.doc_id FROM edge_relationships er "
        "JOIN relationships rl ON rl.rel_id = er.rel_id "
        "WHERE er.edge_id=?",
        (edge_id,),
    ).fetchall()
    out = []
    for r in rows:
        doc = DOCS.get(r["doc_id"])
        if doc is None:
            die(f"relationship points at unknown doc {r['doc_id']}")
        itvs = [x["label"] for x in DOC_ITV.get(doc["doc_id"], []) if x["label"]]
        out.append(
            {
                "doc_id": doc["doc_id"],
                "interviewee": doc["interviewee"],
                "interviewees": itvs or ([doc["interviewee"]] if doc["interviewee"] else []),
                "collection": doc["collection"],
                "year": doc["year"],
                "transcript_url": doc["transcript_url"],
                "source_url": doc["source_url"],
                "title": doc["title"],
            }
        )
    out.sort(key=lambda d: (d["year"] or 0, d["doc_id"]))
    return out


def build_edges(subject_key):
    """Return the fully hydrated per-edge items for one subject."""
    node_id = SUBJECTS[subject_key]["node_id"]
    rows = cur.execute(
        "SELECT edge_id, a, b, weight, n, pair_fnv FROM edges WHERE a=? OR b=?",
        (node_id, node_id),
    ).fetchall()
    items = []
    for e in rows:
        if e["a"] == node_id:
            subject_side, other_id = "a", e["b"]
        elif e["b"] == node_id:
            subject_side, other_id = "b", e["a"]
        else:
            die(f"edge {e['edge_id']} matched but has neither endpoint == {node_id}")
        rels = edge_relations_for(e["edge_id"], subject_side)
        docs = attested_by(e["edge_id"])
        items.append(
            {
                "edge_id": e["edge_id"],
                "weight": e["weight"],
                "n": e["n"],
                "pair_fnv": e["pair_fnv"],
                "subject_side": subject_side,
                "edge_a": e["a"],
                "edge_b": e["b"],
                "evidence_url": evidence_url(e["pair_fnv"]),
                "network_url": node_url(other_id),
                "edge_relations": rels,
                "n_documents": len(docs),
                "attested_by": docs,
                "other": hydrate_node(other_id),
            }
        )
    items.sort(key=lambda it: (-(it["weight"] or 0), -(it["n"] or 0), it["other"]["label"] or ""))
    return items


def trim_neighbour(it):
    o = it["other"]
    wd = o.get("wd_people") or {}
    return {
        "node_id": o["node_id"],
        "label": o["label"],
        "qid": o["qid"],
        "kind": o["kind"],
        "n": it["n"],
        "weight": it["weight"],
        "docs": o["docs"],
        "mentions": o["mentions"],
        "community": o["community"],
        "community_label": o["community_label"],
        "description": wd.get("description"),
        "image_url": o.get("wd_image_url") or wd.get("image_url"),
        "semlab_thumb_url": o.get("semlab_thumb_url") or wd.get("semlab_thumb_url"),
        "top_relations": [r["relation"] for r in it["edge_relations"][:3]],
        "network_url": it["network_url"],
        "evidence_url": it["evidence_url"],
    }


def aggregates(items):
    by_relation = defaultdict(int)
    by_relation_dir = defaultdict(lambda: defaultdict(int))
    for it in items:
        for r in it["edge_relations"]:
            by_relation[r["relation"]] += r["count"] or 0
            by_relation_dir[r["relation"]][r["direction"]] += r["count"] or 0
    by_relation_out = [
        {
            "relation": k,
            "count": v,
            "by_direction": dict(sorted(by_relation_dir[k].items(), key=lambda kv: -kv[1])),
        }
        for k, v in sorted(by_relation.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    by_comm = defaultdict(int)
    for it in items:
        by_comm[it["other"]["community"]] += 1
    by_community = []
    for cid, cnt in sorted(by_comm.items(), key=lambda kv: (-kv[1], kv[0] if kv[0] is not None else -1)):
        c = COMM.get(cid) or {}
        by_community.append(
            {
                "community": cid,
                "label": c.get("label"),
                "era": c.get("era"),
                "place": c.get("place"),
                "rank": c.get("rank"),
                "size": c.get("size"),
                "neighbours": cnt,
            }
        )

    top_by_n = [trim_neighbour(it) for it in sorted(items, key=lambda x: (-(x["n"] or 0), -(x["weight"] or 0)))[:30]]

    rvn = defaultdict(int)
    for it in items:
        rvn[it["other"]["kind"]] += 1
    reconciled_vs_not = {
        "wd": rvn.get("wd", 0),
        "nm": rvn.get("nm", 0),
        "loc": rvn.get("loc", 0),
        "reconciled": rvn.get("wd", 0),
        "unreconciled": rvn.get("nm", 0) + rvn.get("loc", 0),
        "total": sum(rvn.values()),
    }
    unexpected = set(rvn) - {"wd", "nm", "loc"}
    if unexpected:
        die(f"unexpected nodes.kind values among neighbours: {unexpected}")

    return by_relation_out, by_community, top_by_n, reconciled_vs_not


# ---------------------------------------------------------------- per-subject files

EDGES = {}
for key, sub in SUBJECTS.items():
    items = build_edges(key)
    EDGES[key] = items
    by_relation, by_community, top_by_n, rvn = aggregates(items)
    subj_node = hydrate_node(sub["node_id"])
    doc = {
        "subject": key,
        "qid": sub["qid"],
        "node_id": sub["node_id"],
        "generated_from": "linked_jazz.sqlite",
        "count": len(items),
        "subject_node": subj_node,
        "method": {
            "selection": (
                f"Every row of `edges` where a = '{sub['node_id']}' or b = '{sub['node_id']}'. "
                "For each edge the OTHER endpoint is hydrated from `nodes`, plus `wd_people` "
                f"(when the node carries a qid; wp_abstract trimmed to ~{ABSTRACT_CHARS} chars and "
                "whitespace-collapsed), its `node_collections` list, and its community label from "
                "`communities`."
            ),
            "direction_normalisation": DIRECTION_METHOD,
            "attested_by": (
                "edge_relationships -> relationships -> documents, deduplicated on doc_id. "
                "`interviewee` is documents.interviewee; `interviewees` is the full "
                "doc_interviewees list when present. n_documents = len(attested_by)."
            ),
            "urls": (
                "network deep link = " + NETWORK_NODE_URL.replace("{node_id}", "<node_id>") + " ; "
                "evidence store = " + meta["evidence_url_pattern"] + " (pair_fnv from edges)."
            ),
            "sort": "items sorted by weight desc, then n desc, then other label asc.",
            "text": "Only whitespace runs collapsed; no other text cleaning.",
        },
        "by_relation": by_relation,
        "by_community": by_community,
        "top_by_n": top_by_n,
        "reconciled_vs_not": rvn,
        "items": items,
    }
    dump(os.path.join(OUT_ROOT, key, "connections.json"), doc)


S = SUBJECTS["weston"]


# ---------------------------------------------------------------- shared/communities.json

HOME = 2
comms_out = []
for cid, c in sorted(COMM.items(), key=lambda kv: (kv[1].get("rank") if kv[1].get("rank") is not None else 9999, kv[0])):
    d = dict(c)
    d["is_subject_home"] = cid == HOME
    d["summary"] = collapse(d.get("summary"))
    d["subjects"] = ["weston"] if cid == HOME else []
    comms_out.append(d)

home_members = []
for r in cur.execute(
    "SELECT node_id, kind, label, is_interviewee, qid, semlab_id, mentions, docs, community, "
    "wd_image_url, semlab_thumb_url FROM nodes WHERE community=? ORDER BY mentions DESC, docs DESC, label",
    (HOME,),
):
    d = dict(r)
    wd = None
    if d["qid"]:
        w = cur2.execute(
            "SELECT description, birth, death, wp_title, image_url, semlab_thumb_url "
            "FROM wd_people WHERE qid=?",
            (d["qid"],),
        ).fetchone()
        if w:
            wd = dict(w)
    d["description"] = (wd or {}).get("description")
    d["birth"] = (wd or {}).get("birth")
    d["death"] = (wd or {}).get("death")
    d["wd_image_url"] = d["wd_image_url"] or (wd or {}).get("image_url")
    d["semlab_thumb_url"] = d["semlab_thumb_url"] or (wd or {}).get("semlab_thumb_url")
    d["collections"] = NODE_COLLS.get(d["node_id"], [])
    d["network_url"] = node_url(d["node_id"])
    d["is_subject"] = d["node_id"] == S["node_id"]
    home_members.append(d)
    if len(home_members) >= 60:
        break

home = COMM[HOME]
communities_doc = {
    "subject": "shared",
    "qid": S["qid"],
    "generated_from": "linked_jazz.sqlite",
    "count": len(comms_out),
    "subject_home_community": {
        "community_id": HOME,
        "label": home["label"],
        "rank": home["rank"],
        "size": home["size"],
        "era": home["era"],
        "place": home["place"],
        "scene": home["scene"],
        "summary": collapse(home["summary"]),
        "confidence": home["confidence"],
        "key_figures": home["key_figures"],
        "members_in_file": len(home_members),
        "note": "Randy Weston (wd:Q1371187) sits in this community -- the same one as John Coltrane, Miles Davis and Melba Liston, the other 1926 centennials.",
    },
    "method": {
        "communities": (
            "All rows of `communities` (seeded Louvain, labels/era/place/scene/summary are "
            "LLM-generated with a confidence score). key_figures parsed from its JSON array. "
            "Sorted by rank asc. is_subject_home flags community 2."
        ),
        "home_members": (
            "Top 60 nodes with community = 2 ordered by nodes.mentions desc (ties by docs desc, "
            "then label), enriched with wd_people description/dates/portrait and node_collections."
        ),
    },
    "communities": comms_out,
    "community_2_top_members": home_members,
    "items": comms_out,
}
dump(os.path.join(OUT_ROOT, "shared", "communities.json"), communities_doc)


# ---------------------------------------------------------------- summary

print("=" * 72)
for key in SUBJECTS:
    items = EDGES[key]
    print(f"\n{SUBJECTS[key]['name']} ({SUBJECTS[key]['node_id']}): {len(items)} edges")
    print("  top 15 neighbours by weight:")
    for it in items[:15]:
        o = it["other"]
        rels = ", ".join(f"{r['relation']}x{r['count']}({r['direction']})" for r in it["edge_relations"][:3])
        print(
            f"    {o['label']:<28} w={it['weight']:.3f} n={it['n']:<3} "
            f"docs={it['n_documents']:<3} c={o['community']:<3} {rels}"
        )
print(f"\ncommunities: {len(comms_out)} rows; home = community {HOME} '{home['label']}' "
      f"(rank {home['rank']}, size {home['size']}); top members emitted: {len(home_members)}")

print("\nfiles written:")
for p in (
    f"{OUT_ROOT}/weston/connections.json",
    f"{OUT_ROOT}/shared/communities.json",
):
    print(f"  {os.path.getsize(p):>10,} B  {p}")

con.close()
