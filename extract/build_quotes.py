#!/usr/bin/env python3
"""
build_quotes.py — QUOTES layer of the Randy Weston centennial extraction
(ported from the Coltrane / Davis build).

For the subject (Q1371187 Randy Weston) emit one record per
(block_id, subject): the verbatim transcript block that mentions them, who was
speaking, the mention spans, a +/-2 block context window, and full provenance.

Source: read-only /Users/m/git/ch-jazz-mashup/linked_jazz.sqlite
Output: weston/quotes.json

Two additions from extract/subject.py: blocks from his own interview are
flagged own_interview (and never count as another musician speaking about
him), and text hits the person layer missed are added as
mention_source = fts_supplement.

Run:  uv run python extract/build_quotes.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject  # noqa: E402
from collections import Counter, defaultdict

DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")  # see extract/subject.py
OUT_ROOT = "/Users/m/git/weston-centennial"
NETWORK = "https://thisismattmiller.github.io/linked-jazz-2026-network/#"

SUBJECTS = [
    ("weston", "Q1371187", "wd:Q1371187", "Randy Weston"),
]

METHOD = (
    "speaker_role heuristic: blocks.speaker is compared against the doc's interviewee side "
    "(doc_interviewees.label + documents.interviewee, split on ' and '/'&'/',') and its "
    "interviewer side (documents.interviewer + any name captured from the title pattern "
    "'interviewed by X'). Tiers, best match wins: (1) literal role tokens "
    "(INTERVIEWEE/IE/SUBJECT/RESPONDENT vs INTERVIEWER/IR/INT/Q/QUESTION/HOST); "
    "(2) exact normalized name equality; (3) surname-token overlap, or equality of the "
    "space-squashed name so OCR splits match ('MR. MC RAE' = 'Teddy McRae'); "
    "honorifics MR./MS./MRS./DR./MISS and suffixes JR/SR/II-IV stripped, tokens >=3 chars; "
    "(4) initials match (speaker of 1-3 capital letters, e.g. Hamilton's 'MR'/'SA' or Rutgers' "
    "'W', accepted when its letters are an in-order subsequence of a candidate's token "
    "initials; a single letter must be that candidate's first or last initial); "
    "(5) dialogue-partner inference - in a doc whose dialogue is dominated by two speakers, "
    "exactly one of which resolved, the other top speaker (>=5 turns, >=15% of the two) takes "
    "the opposite role. This names the voice the metadata omitted: Smithsonian/Rutgers "
    "interviewers ('Kirchner', 'Brower', 'MR. HUGHES'), and on Hamilton docs whose interviewee "
    "field kept only a surname, the interviewee behind initials like 'JJ'. A second label for "
    "that same inferred person ('Baker' beside 'DAVID BAKER') gets basis "
    "'partner_label_variant'.Blank/NULL speakers on dialogue blocks are "
    "read two ways: in Q&A-shaped documents (>=15% of dialogue blocks unlabelled and no "
    "labelled speaker resolves to the interviewee side, only a questioner such as 'Q.' - "
    "typical of Rutgers) an unlabelled turn IS the answer, so it is called 'interviewee' with "
    "basis 'unlabeled_answer_turn'; elsewhere a blank is a page-break continuation and "
    "inherits the previous dialogue speaker (speaker_inherited=true). Unlabelled prose blocks "
    "that open mid-sentence (lowercase first letter) are likewise treated as continuations of "
    "the previous turn; unlabelled prose that opens a sentence is left alone. Anything still "
    "unresolved, incl. ASR 'SPEAKER_nn' labels, archive 'note' blocks and free-standing "
    "unlabelled prose, is "
    "'unknown'. role_basis on each item names the tier that decided it. "
    "is_about_subject_quote = (speaker_role == 'interviewee')."
)

TEXT_NOTE = (
    "text is blocks.text with runs of whitespace collapsed to single spaces; when that "
    "changed the string the verbatim original is kept in text_raw. spans start/end are the "
    "DB's character offsets into the ORIGINAL block text, i.e. into text_raw when present, "
    "otherwise into text; surface is that slice, pre-computed."
)

WS = re.compile(r"\s+")
ROLE_IEE = {"INTERVIEWEE", "IE", "SUBJECT", "RESPONDENT", "ANSWER", "A"}
ROLE_IER = {"INTERVIEWER", "IR", "INT", "Q", "QUESTION", "HOST", "INTERVIEWERS"}
HONORIFIC = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "rev", "sir", "mme"}
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}
SPLIT_NAMES = re.compile(r"\s+and\s+|\s*&\s*|\s*;\s*|\s*,\s*(?=[A-Z][a-z])|\s*/\s*", re.I)
TITLE_IER = re.compile(r"interview(?:ed)?\s+by\s+([^,\n;]+)", re.I)
ASR = re.compile(r"^SPEAKER[_ ]?\d+$", re.I)


def collapse(s):
    if s is None:
        return None
    return WS.sub(" ", s).strip()


def starts_midsentence(text):
    t = (text or "").lstrip().lstrip("\"'“‘(-— ")
    return bool(t) and t[0].isalpha() and t[0].islower()


def norm(s):
    """lowercase, de-accent, punctuation -> space, collapse."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9A-Za-z]+", " ", s)
    return WS.sub(" ", s).strip().lower()


def name_tokens(s):
    toks = [t for t in norm(s).split() if t not in SUFFIX]
    if len(toks) > 1 and toks[0] in HONORIFIC:
        toks = toks[1:]
    return toks


def initials_of(s):
    return "".join(t[0] for t in name_tokens(s))


def is_subsequence(small, big):
    it = iter(big)
    return all(c in it for c in small)


def split_people(s):
    if not s:
        return []
    out = []
    for part in SPLIT_NAMES.split(s):
        part = part.strip(" .,")
        if part and norm(part):
            out.append(part)
    return out


class DocRoles:
    """Resolve blocks.speaker -> interviewee / interviewer / unknown for one document."""

    def __init__(self, doc, itv_labels, blocks):
        self.iee = []
        for cand in [doc["interviewee"]] + list(itv_labels):
            for p in split_people(cand):
                if norm(p) not in {norm(x) for x in self.iee}:
                    self.iee.append(p)
        self.ier = []
        for cand in [doc["interviewer"]] + TITLE_IER.findall(doc["title"] or ""):
            for p in split_people(cand):
                if p.strip().upper() in ROLE_IER or p.strip().upper() in ROLE_IEE:
                    continue
                if norm(p) not in {norm(x) for x in self.ier}:
                    self.ier.append(p)
        self._cache = {}
        # dialogue turn counts, for the partner inference
        self.turns = Counter(
            b["speaker"].strip()
            for b in blocks
            if b["type"] == "dialogue" and (b["speaker"] or "").strip()
        )
        self._partner = None
        self._partner_done = False

    def _match(self, spk):
        """-> (role, basis) using tiers 1-4, or (None, None)."""
        raw = spk.strip()
        up = raw.upper().strip(" .:;-")
        if up in ROLE_IEE:
            return "interviewee", "literal_token"
        if up in ROLE_IER:
            return "interviewer", "literal_token"
        if ASR.match(raw):
            return None, None
        toks = name_tokens(raw)
        nrm = " ".join(toks)
        if nrm:
            for role, cands in (("interviewee", self.iee), ("interviewer", self.ier)):
                for c in cands:
                    if nrm and nrm == " ".join(name_tokens(c)):
                        return role, "exact_name"
            spk_sur = {t for t in toks if len(t) >= 3}
            squash = "".join(toks)
            for role, cands in (("interviewee", self.iee), ("interviewer", self.ier)):
                for c in cands:
                    ct = name_tokens(c)
                    if not ct:
                        continue
                    surnames = {t for t in ct if len(t) >= 3}
                    # squashed form catches OCR splits: "MR. MC RAE" vs "Teddy McRae"
                    if squash and squash == "".join(ct):
                        return role, "surname_token"
                    if ct[-1] in spk_sur or (spk_sur & surnames and toks[-1] in surnames):
                        return role, "surname_token"
        r = self._initials(raw, (("interviewee", self.iee), ("interviewer", self.ier)))
        return r if r[0] else (None, None)

    def _initials(self, raw, tiers, basis="initials"):
        """Hamilton-style 'MR'/'SA', Rutgers-style 'W'."""
        letters = re.sub(r"[^A-Za-z]", "", raw)
        if not (1 <= len(letters) <= 3) or not letters.isupper():
            return None, None
        low = letters.lower()
        for role, cands in tiers:
            for c in cands:
                ini = initials_of(c)
                if not ini:
                    continue
                if len(low) == 1:
                    if low == ini[0] or low == ini[-1]:
                        return role, basis
                elif low == ini or (len(ini) >= len(low) and is_subsequence(low, ini)):
                    return role, basis
        return None, None

    def partner(self):
        """In a two-voice document, name the voice the metadata never named.

        Returns (speaker_label, role) or None. If one of the two dominant dialogue
        speakers resolved to a side, the other one is the opposite side.
        """
        if self._partner_done:
            return self._partner
        self._partner_done = True
        top = self.turns.most_common(4)
        if len(top) >= 2:
            roles = [(s, n, self._match(s)[0]) for s, n in top]
            known = {r[2] for r in roles if r[2]}
            free = [r for r in roles[:2] if r[2] is None]
            if len(free) == 1 and len(known) == 1:
                other = known.pop()
                cand, n, _ = free[0]
                # require a genuine second voice, not a stray aside
                if n >= 5 and n >= 0.15 * sum(x[1] for x in roles[:2]):
                    role = "interviewer" if other == "interviewee" else "interviewee"
                    self._partner = (cand, role)
        return self._partner

    def role(self, spk):
        if spk in self._cache:
            return self._cache[spk]
        if not spk or not spk.strip():
            res = ("unknown", "no_speaker")
        else:
            r, basis = self._match(spk)
            p = self.partner()
            if r:
                res = (r, basis)
            elif p is not None and spk.strip() == p[0]:
                res = (p[1], "dialogue_partner_inference")
            elif p is not None and self._variant_of(spk, p[0]):
                # same person under a second label, e.g. "Baker" vs "DAVID BAKER"
                res = (p[1], "partner_label_variant")
            else:
                res = ("unknown", "unmatched")
        self._cache[spk] = res
        return res

    def _variant_of(self, spk, label):
        st, lt = name_tokens(spk), name_tokens(label)
        if st and lt:
            if "".join(st) == "".join(lt):
                return True
            sur = {t for t in st if len(t) >= 3} & {t for t in lt if len(t) >= 3}
            if sur:
                return True
        return self._initials(spk.strip(), (("x", [label]),))[0] is not None


def fetch_docs(con, doc_ids):
    q = ",".join("?" * len(doc_ids))
    docs = {}
    for r in con.execute(f"SELECT * FROM documents WHERE doc_id IN ({q})", doc_ids):
        docs[r["doc_id"]] = dict(r)
    itv = defaultdict(list)
    for r in con.execute(
        f"SELECT doc_id,label FROM doc_interviewees WHERE doc_id IN ({q}) ORDER BY ord", doc_ids
    ):
        if r["label"]:
            itv[r["doc_id"]].append(r["label"])
    return docs, itv


def build(con, key, qid, node_id, label, stats):
    targets = subject.target_blocks(con)
    if not targets:
        sys.exit(f"FATAL: no person_mentions for {qid}")
    by_block = {bid: ms for bid, (ms, _) in targets.items()}
    source_of = {bid: src for bid, (_, src) in targets.items()}
    rows = [m for ms in by_block.values() for m in ms]
    doc_ids = sorted({r["doc_id"] for r in rows})
    docs, itv = fetch_docs(con, doc_ids)
    missing = [d for d in doc_ids if d not in docs]
    if missing:
        sys.exit(f"FATAL: {len(missing)} doc_ids missing from documents: {missing[:5]}")

    blocks_by_doc = {}
    roles = {}
    for did in doc_ids:
        bl = [
            dict(b)
            for b in con.execute(
                "SELECT block_id,doc_id,page,block,type,speaker,text FROM blocks "
                "WHERE doc_id=? ORDER BY page,block",
                (did,),
            )
        ]
        dr = DocRoles(docs[did], itv.get(did, []), bl)
        roles[did] = dr

        # Q&A-style transcripts (mostly Rutgers) label only the questioner; the answer
        # turns carry no speaker at all. Detect that shape so blanks are not treated as
        # continuations of the interviewer.
        labeled = {s: dr.role(s)[0] for s in dr.turns}
        n_dlg = sum(1 for b in bl if b["type"] == "dialogue")
        n_blank = sum(
            1 for b in bl if b["type"] == "dialogue" and not (b["speaker"] or "").strip()
        )
        qa_mode = (
            n_dlg > 0
            and n_blank >= 0.15 * n_dlg
            and "interviewee" not in labeled.values()
            and "interviewer" in labeled.values()
        )
        if qa_mode:
            stats["qa_mode_docs"] += 1

        # blank dialogue speakers = page-break continuations -> inherit previous voice
        last = None  # (speaker_label, forced_role) of the current voice
        for b in bl:
            spk = (b["speaker"] or "").strip()
            b["forced_role"] = None
            if b["type"] == "dialogue":
                if spk:
                    last = (spk, None)
                    b["speaker_eff"], b["inherited"] = spk, False
                elif qa_mode:
                    last = (None, "interviewee")
                    b["speaker_eff"], b["inherited"] = None, False
                    b["forced_role"] = "interviewee"
                else:
                    b["speaker_eff"] = last[0] if last else None
                    b["forced_role"] = last[1] if last else None
                    b["inherited"] = last is not None
            elif b["type"] == "prose" and not spk and last and starts_midsentence(b["text"]):
                # unlabelled prose that opens mid-sentence continues the previous turn
                b["speaker_eff"], b["forced_role"], b["inherited"] = last[0], last[1], True
            else:
                b["speaker_eff"], b["inherited"] = (spk or None), False
                if spk:
                    last = (spk, None)
        blocks_by_doc[did] = bl

    index = {}  # block_id -> (doc_id, i)
    for did, bl in blocks_by_doc.items():
        for i, b in enumerate(bl):
            index[b["block_id"]] = (did, i)

    def ctx(b):
        return {
            "speaker": collapse(b["speaker"]) or None,
            "text": collapse(b["text"]) or "",
            "page": b["page"],
            "block": b["block"],
            "type": b["type"],
        }

    items = []
    for block_id, ms in by_block.items():
        if block_id not in index:
            sys.exit(f"FATAL: block_id {block_id} not in blocks")
        did, i = index[block_id]
        bl = blocks_by_doc[did]
        b = bl[i]
        d = docs[did]
        raw = b["text"] or ""
        text = collapse(raw)

        spans = []
        seen = set()
        for m in sorted(ms, key=lambda x: (x["start"], x["end"])):
            k = (m["start"], m["end"])
            if k in seen:
                continue
            seen.add(k)
            surf = raw[m["start"] : m["end"]]
            spans.append({"start": m["start"], "end": m["end"], "surface": surf})
            stats["spans"] += 1
            if surf.strip() == "":
                stats["empty_surface"] += 1
            forms_here = json.loads(m["surface_forms"] or "[]")
            if surf not in forms_here:
                stats["surface_not_exact_form"] += 1
                if surf.lower() in {f.lower() for f in forms_here}:
                    stats["surface_case_only_diff"] += 1

        forms, pids = [], []
        for m in ms:
            if m["person_id"] not in pids:
                pids.append(m["person_id"])
                for f in json.loads(m["surface_forms"] or "[]"):
                    if f not in forms:
                        forms.append(f)
        # sanity: does the block text actually contain one of the surface forms?
        low = text.lower()
        if not any(f.lower() in low for f in forms) and not any(
            s["surface"].strip().lower() in low for s in spans
        ):
            stats["no_surface_in_text"] += 1

        spk_eff = b["speaker_eff"]
        if b["forced_role"]:
            role, basis = b["forced_role"], "unlabeled_answer_turn"
            if b["inherited"]:
                basis += "+inherited_speaker"
        else:
            role, basis = roles[did].role(spk_eff or "")
            if b["inherited"] and role != "unknown":
                basis += "+inherited_speaker"

        turl = d["transcript_url"]
        items.append(
            {
                "block_id": block_id,
                "text": text,
                **({"text_raw": raw} if raw != text else {}),
                "chars": len(text),
                "speaker": collapse(b["speaker"]) or None,
                "speaker_effective": collapse(spk_eff) or None,
                "speaker_inherited": bool(b["inherited"]),
                "speaker_role": role,
                "role_basis": basis,
                "is_about_subject_quote": role == "interviewee" and did != subject.OWN_DOC,
                "own_interview": did == subject.OWN_DOC,
                "speaker_is_subject": did == subject.OWN_DOC and role == "interviewee",
                "mention_source": source_of[block_id],
                "block_type": b["type"],
                "n_mentions_in_block": len(spans),
                "spans": spans,
                "surface_forms": forms,
                "person": {
                    "person_ids": [p for p in pids if p is not None],
                    "canonical": ms[0]["canonical"],
                    "confidence": ms[0]["confidence"],
                    "mentions_in_doc": sum(
                        m["person_count"] for m in {p["person_id"]: p for p in ms}.values()
                    ),
                },
                "context": {
                    "before": [ctx(x) for x in bl[max(0, i - 2) : i]],
                    "after": [ctx(x) for x in bl[i + 1 : i + 3]],
                },
                "src": {
                    "doc_id": did,
                    "block_id": block_id,
                    "page": b["page"],
                    "block": b["block"],
                    "collection": d["collection"],
                    "title": d["title"],
                    "interviewee": d["interviewee"],
                    "interviewer": d["interviewer"] or None,
                    "year": d["year"],
                    "transcript_url": (
                        f"{turl}#b{b['page']}-{b['block']}" if turl else None
                    ),
                    "source_url": d["source_url"] or None,
                },
            }
        )

    items.sort(key=lambda r: (not r["is_about_subject_quote"], -r["chars"], r["block_id"]))

    per_doc = Counter(r["src"]["doc_id"] for r in items)
    by_document = sorted(
        (
            {
                "doc_id": did,
                "title": docs[did]["title"],
                "interviewee": docs[did]["interviewee"],
                "collection": docs[did]["collection"],
                "year": docs[did]["year"],
                "n_blocks": n,
                "transcript_url": docs[did]["transcript_url"],
            }
            for did, n in per_doc.items()
        ),
        key=lambda r: (-r["n_blocks"], r["doc_id"]),
    )
    by_collection = Counter(r["src"]["collection"] for r in items)
    spk = Counter((r["speaker_effective"], r["src"]["doc_id"]) for r in items)
    by_speaker = sorted(
        ({"speaker": s, "doc_id": d, "n_blocks": n} for (s, d), n in spk.items()),
        key=lambda r: (-r["n_blocks"], str(r["speaker"]), r["doc_id"]),
    )

    out = {
        "subject": key,
        "qid": qid,
        "generated_from": "linked_jazz.sqlite",
        "count": len(items),
        "person_label": label,
        "node_id": node_id,
        "network_url": NETWORK + node_id,
        "n_documents": len(by_document),
        "n_mentions": sum(r["n_mentions_in_block"] for r in items),
        "n_interviewee_blocks": sum(1 for r in items if r["is_about_subject_quote"]),
        "own_interview_doc": subject.OWN_DOC,
        "n_own_interview_blocks": sum(1 for r in items if r["own_interview"]),
        "n_other_doc_blocks": sum(1 for r in items if not r["own_interview"]),
        "mention_source_counts": dict(Counter(r["mention_source"] for r in items)),
        "own_interview_note": (
            "Randy Weston is an interviewee in this corpus. Blocks from his own interview "
            "(own_interview=true) are kept, but is_about_subject_quote is false for all of them: "
            "there the 'interviewee' is Weston himself (speaker_is_subject=true) and the other voice "
            "is his interviewer, the journalist Willard Jenkins (Q15449804), who is not counted as "
            "a witness. mention_source='fts_supplement' "
            "marks blocks the QID-reconciled person layer missed and a text search recovered "
            "('Randy Weston' unlinked, 'Randy Western', 'Randy [Weston]', and a bare 'Randy' in an "
            "interview that names him in full elsewhere); their spans are regex offsets and "
            "their identity is unverified until evaluated."
        ),
        "role_counts": dict(Counter(r["speaker_role"] for r in items)),
        "role_basis_counts": dict(Counter(r["role_basis"] for r in items)),
        "method": METHOD,
        "text_note": TEXT_NOTE,
        "by_document": by_document,
        "by_collection": {
            c: by_collection.get(c, 0) for c in ("tulane", "hamilton", "si", "rutgers")
        },
        "by_speaker": by_speaker,
        "items": items,
    }
    for c in by_collection:
        if c not in out["by_collection"]:
            sys.exit(f"FATAL: unexpected collection {c!r}")

    path = os.path.join(OUT_ROOT, key, "quotes.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    return out, path


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    stats = Counter()
    summary = []
    for key, qid, node_id, label in SUBJECTS:
        out, path = build(con, key, qid, node_id, label, stats)
        size = os.path.getsize(path)
        summary.append((key, path, out, size))
        print(f"\n=== {key} ({qid}) -> {path}  {size/1e6:.2f} MB")
        print(
            f"  items(blocks)={out['count']}  mentions={out['n_mentions']}  "
            f"docs={out['n_documents']}  interviewee_blocks={out['n_interviewee_blocks']}"
        )
        print(f"  roles={out['role_counts']}")
        print(f"  role_basis={out['role_basis_counts']}")
        print(f"  by_collection={out['by_collection']}")
        print(f"  top docs: {[(d['interviewee'], d['n_blocks']) for d in out['by_document'][:5]]}")

    print(f"\nspan checks: total_spans={stats['spans']} empty_surface={stats['empty_surface']} "
          f"blocks_where_no_surface_found_in_text={stats['no_surface_in_text']} "
          f"surface_not_an_exact_surface_form={stats['surface_not_exact_form']} "
          f"(of which case-only={stats['surface_case_only_diff']}) "
          f"qa_style_docs={stats['qa_mode_docs']}")

    # ---- invariants, re-read from disk
    for key, path, _, _ in summary:
        with open(path, encoding="utf-8") as fh:
            o = json.load(fh)
        assert o["count"] == len(o["items"]), key
        assert len({i["block_id"] for i in o["items"]}) == o["count"], f"{key}: dup block_id"
        assert sum(o["by_collection"].values()) == o["count"], key
        assert sum(d["n_blocks"] for d in o["by_document"]) == o["count"], key
        assert sum(s["n_blocks"] for s in o["by_speaker"]) == o["count"], key
        assert o["n_mentions"] == sum(i["n_mentions_in_block"] for i in o["items"]), key
        for i in o["items"]:
            base = i.get("text_raw", i["text"])
            for s in i["spans"]:
                assert base[s["start"] : s["end"]] == s["surface"], (key, i["block_id"])
            u = i["src"]["transcript_url"]
            assert u is None or u.endswith(f"#b{i['src']['page']}-{i['src']['block']}")
            assert i["is_about_subject_quote"] == (
                i["speaker_role"] == "interviewee" and not i["own_interview"])
            assert i["chars"] == len(i["text"])
        con2 = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        for i in o["items"][:50] + o["items"][-50:]:
            row = con2.execute(
                "SELECT doc_id,page,block,text FROM blocks WHERE block_id=?", (i["block_id"],)
            ).fetchone()
            assert row[0] == i["src"]["doc_id"] and row[1] == i["src"]["page"], i["block_id"]
            assert row[3] == i.get("text_raw", i["text"]), i["block_id"]
        con2.close()
        print(f"invariants OK: {path}")

    # ---- spot checks: 3 records per subject
    for key, path, out, _ in summary:
        print(f"\n########## SPOT CHECK: {key} ##########")
        richest = max(out["items"], key=lambda r: r["n_mentions_in_block"])
        interviewee = next(r for r in out["items"] if r["is_about_subject_quote"])
        other = next(r for r in out["items"] if not r["is_about_subject_quote"])
        picks = [richest, interviewee, other]
        for it in picks:
            print(f"\n--- block_id={it['block_id']} role={it['speaker_role']} "
                  f"({it['role_basis']}) speaker={it['speaker_effective']!r} "
                  f"chars={it['chars']} mentions={it['n_mentions_in_block']}")
            print(f"  doc: {it['src']['title']} [{it['src']['collection']} {it['src']['year']}]")
            print(f"  url: {it['src']['transcript_url']}")
            print(f"  spans: {it['spans']}")
            print(f"  surface_forms: {it['surface_forms']}")
            for c in it["context"]["before"]:
                print(f"  [before {c['speaker']}] {c['text'][:120]}")
            print(f"  >>> TEXT: {it['text'][:700]}")
            for c in it["context"]["after"]:
                print(f"  [after {c['speaker']}] {c['text'][:120]}")


if __name__ == "__main__":
    main()
