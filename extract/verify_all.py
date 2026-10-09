#!/usr/bin/env python3
"""Independent integrity check over every published quote in the repo.

Each merge script verifies the quotes it merges. This re-does all of it from
scratch against the DATABASE (not against the intermediate JSON), so a bug in a
merge script cannot vouch for itself. Exit status is non-zero on any failure.

Checks
  1. every quote field in every output file is an exact substring of the
     whitespace-collapsed text of the block it names, in linked_jazz.sqlite
     (a quote flagged spans_page_break: of two consecutive blocks joined by
     one space, and it must cross the join)
  2. quotes attributed to Weston come from blocks he speaks in his own
     interview; quotes attributed to Willard Jenkins from Jenkins's blocks
  3. no quote of Weston's contains a transcriber's bracket; no quote from the
     Liston interview overlaps one of its transcriber's bracketed summaries
  4. no witness's lead or second quote comes from a block the evaluation pass
     labelled as the interviewer speaking, and none comes from Weston's own
     interview
  5. the file-to-file joins hold (shortlist ⊆ enriched = quotes outside his own
     interview, etc.)
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
WS = re.compile(r"\s+")
BRACKET = re.compile(r"\[[^\]]{26,}\]")

con = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
_cache = {}


def block(bid):
    if bid not in _cache:
        r = con.execute("SELECT doc_id, speaker, text FROM blocks WHERE block_id=?", (bid,)).fetchone()
        _cache[bid] = None if r is None else (r[0], (r[1] or "").strip(), WS.sub(" ", r[2] or "").strip())
    return _cache[bid]


fails, checked = [], 0
by_file = {}
# roles in his own interview: blank-speaker continuation blocks inherit the
# previous voice, and three blocks are assigned by hand (build_own_interview.py)
own = json.loads((D / "own_interview.json").read_text(encoding="utf-8"))["items"]
own_roles = {b["block_id"]: b["speaker_role"] for b in own}
own_next = {a["block_id"]: b for a, b in zip(own, own[1:])}


def check(where, quote, bid, voice=None, no_bracket=False, plain=False):
    """voice: None | 'subject' | 'interviewer' (roles inside his own interview).
    no_bracket: must not overlap a long transcriber summary. plain: no '[' at all."""
    global checked
    if not quote:
        return
    checked += 1
    by_file[where.split(".")[0]] = by_file.get(where.split(".")[0], 0) + 1
    b = block(bid)
    if b is None:
        fails.append(f"{where}: block {bid} not in DB")
        return
    if quote not in b[2]:
        fails.append(f"{where}: block {bid}: not verbatim: {quote[:70]!r}")
        return
    if voice and own_roles.get(bid) != voice:
        fails.append(f"{where}: block {bid}: speaker role is {own_roles.get(bid)!r}, wanted {voice}")
    if plain and "[" in quote:
        fails.append(f"{where}: block {bid}: quote contains a transcriber bracket")
    if no_bracket:
        i = b[2].index(quote)
        for m in BRACKET.finditer(b[2]):
            if m.start() < i + len(quote) and m.end() > i:
                fails.append(f"{where}: block {bid}: overlaps transcriber bracket")


def check_joined(where, quote, bids):
    global checked
    checked += 1
    by_file[where.split(".")[0]] = by_file.get(where.split(".")[0], 0) + 1
    a, b = block(bids[0]), block(bids[1])
    nxt = own_next.get(bids[0])
    if a is None or b is None or nxt is None or nxt["block_id"] != bids[1]:
        fails.append(f"{where}: blocks {bids} are not consecutive blocks of his interview")
        return
    if own_roles.get(bids[0]) != "subject" or own_roles.get(bids[1]) != "subject":
        fails.append(f"{where}: blocks {bids}: not both spoken by Weston")
    joined = a[2] + " " + b[2]
    if quote not in joined or "[" in quote:
        fails.append(f"{where}: blocks {bids}: not verbatim: {quote[:70]!r}")
        return
    s = joined.index(quote)
    if not (s < len(a[2]) and s + len(quote) > len(a[2]) + 1):
        fails.append(f"{where}: blocks {bids}: quote does not cross the page break")


def load(name):
    return json.loads((D / name).read_text(encoding="utf-8"))


# ---- what others said
enr = load("enriched.json")["items"]
role_of = {i["block_id"]: i["speaker_role"] for i in enr}
for i in enr:
    check("enriched.pull_quote", i["pull_quote"], i["block_id"], no_bracket=True)
    if block(i["block_id"])[2] != i["text"]:
        fails.append(f"enriched: block {i['block_id']} text differs from DB")
    if block(i["block_id"])[0] == SUBJ.OWN_DOC:
        fails.append(f"enriched: block {i['block_id']} is from his own interview")
for i in load("best_quotes.json")["items"]:
    check("best_quotes.pull_quote", i["pull_quote"], i["block_id"], no_bracket=True)
for i in load("recovered_evaluated.json")["items"]:
    check("recovered.pull_quote", i["pull_quote"], i["block_id"], no_bracket=True)

wp = D / "witnesses.json"
if wp.exists():
    for r in load("witnesses.json")["items"]:
        for what, q, bid in (("lead_quote", r["lead_quote"], r["lead_block_id"]),
                             ("second_quote", r["second_quote"], r["second_block_id"])):
            check(f"witnesses.{what}", q, bid, no_bracket=True)
            if q and role_of.get(bid) == "interviewer":
                fails.append(f"witnesses.{what}: block {bid} was labelled as the interviewer speaking")
            if q and block(bid) and block(bid)[0] == SUBJ.OWN_DOC:
                fails.append(f"witnesses.{what}: block {bid} is from his own interview")
        for m in r["more_quotes"]:
            check("witnesses.more_quotes", m["quote"], m["block_id"], no_bracket=True)

# ---- what he said
for p in load("his_words.json")["items"]:
    check("his_words.his_quote", p["his_quote"], p["his_quote_block_id"], "subject", plain=True)
    check("his_words.interviewer_quote", p["interviewer_quote"], p["interviewer_quote_block_id"],
          "interviewer", plain=True)
    for m in p["more_his_quotes"]:
        check("his_words.more_his_quotes", m["quote"], m["block_id"], "subject", plain=True)

ov = load("own_voice.json")
ids = set()
for i in ov["self"]["items"]:
    if i["id"] in ids:
        fails.append(f"own_voice.self: duplicate id {i['id']}")
    ids.add(i["id"])
    if i["spans_page_break"]:
        check_joined("own_voice.self_joined", i["pull_quote"], i["block_ids"])
    else:
        check("own_voice.self", i["pull_quote"], i["block_id"], "subject", plain=True)
for key in ("records", "journeys"):
    for i in ov[key]["items"]:
        check(f"own_voice.{key}", i["pull_quote"], i["pull_quote_block_id"], "subject", plain=True)
        for m in i["more_quotes"]:
            check(f"own_voice.{key}_more", m["quote"], m["block_id"], "subject", plain=True)
for t in ov["timeline"]["items"]:
    for bid in t["block_ids"]:
        if bid not in own_roles:
            fails.append(f"own_voice.timeline: block {bid} is not in his interview")

# ---- the joins that carry quotes into other files
for m in load("discography_personnel.json")["people"]:
    for q in m["quotes"]:
        check("roster.quotes", q["quote"], q["block_id"], no_bracket=True)
    if m["he_said"] and m["he_said"]["his_quote"]:
        check("roster.he_said", m["he_said"]["his_quote"], m["he_said"]["his_quote_block_id"],
              "subject", plain=True)
for r in load("discography.json")["releases"]:
    h = r.get("he_said_of_this_record")
    if h:
        check("discography.he_said_of_this_record", h["pull_quote"], h["pull_quote_block_id"],
              "subject", plain=True)
cp = ROOT / "shared" / "class_of_1926.json"
if cp.exists():
    she = json.loads(cp.read_text(encoding="utf-8"))["others"]["liston"].get("they_said") or {}
    # her words, from her interview, as her build verified them
    for m in [{"quote": she.get("her_quote"), "url": she.get("her_quote_url")}] + list(she.get("more_her_quotes") or []):
        if m.get("quote") and m.get("block_id"):
            check("class_of_1926.liston_they_said", m["quote"], m["block_id"], no_bracket=True)

# ---- joins
q_all = load("quotes.json")["items"]
q_ids = {i["block_id"] for i in q_all if not i["own_interview"]}
e_ids = {i["block_id"] for i in enr}
b_ids = {i["block_id"] for i in load("best_quotes.json")["items"]}
if e_ids != q_ids:
    fails.append(f"join: enriched ({len(e_ids)}) != quotes outside his own interview ({len(q_ids)})")
if not b_ids <= e_ids:
    fails.append("join: best_quotes not a subset of enriched")
doc_ids = {d["doc_id"] for d in load("documents.json")["items"]} | {
    d["doc_id"] for d in load("documents.json")["text_hit_only_documents"]}
missing = {i["doc_id"] for i in enr} - doc_ids
if missing:
    fails.append(f"join: enriched docs missing from documents.json: {sorted(missing)}")
rec_keys = {r["key"] for r in ov["records"]["items"]}
for j in ov["journeys"]["items"]:
    if j["related_record_key"] and j["related_record_key"] not in rec_keys:
        fails.append(f"join: journey {j['key']} points at unknown record {j['related_record_key']}")

print(f"{checked} quotes checked against linked_jazz.sqlite, {len(fails)} failures")
print("  " + ", ".join(f"{k} {v}" for k, v in sorted(by_file.items())))
for f in fails[:40]:
    print("  FAIL", f)
sys.exit(1 if fails else 0)
