#!/usr/bin/env python3
"""weston/biography_sources.json -- the outside record of his life, kept verbatim.

His 2009 interview is a sequel ("since the last oral history a lot has
happened"): it covers 1997-2009 and takes the first seventy years as read. So
the timeline in own_voice.json has almost nothing before the 1990s, and a
centennial page cannot be built from the transcript alone the way Liston's was.

This collects the two outside sources a page would draw the rest from, as they
stand, with nothing rewritten:

  wikipedia   the English article "Randy Weston", section by section, as plain
              paragraphs (references and navboxes removed), each with the
              years it mentions
  wikidata    the statements on Q1371187 that are facts of a life: birth,
              death, places, instruments, labels, awards (with their dates),
              education, with labels resolved

It is source material, not a finding. Nothing here has been checked against
the transcript; where the two disagree, own_voice.json -> timeline[].notes and
records[].discrepancies say so.
"""

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_common import WD_API, _cache_path, _get, parse_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QID, PAGE, KEY = "Q1371187", "Randy Weston", "weston"
YEAR = re.compile(r"\b(1[89]\d\d|20[0-2]\d)\b")
SKIP = re.compile(r"^(discography|references|external links|see also|notes|further reading|"
                  r"bibliography|filmography|sources)", re.I)
PROPS = {"P569": "date of birth", "P570": "date of death", "P19": "place of birth",
         "P20": "place of death", "P27": "country of citizenship", "P106": "occupation",
         "P1303": "instrument", "P136": "genre", "P264": "record label", "P166": "award received",
         "P69": "educated at", "P800": "notable work", "P26": "spouse", "P40": "child",
         "P463": "member of", "P1411": "nominated for", "P119": "place of burial",
         "P856": "official website", "P434": "MusicBrainz artist ID", "P1953": "Discogs artist ID",
         "P214": "VIAF ID", "P244": "Library of Congress authority ID"}


def clean(el):
    for junk in el.select("sup.reference, style, .mw-editsection, .noprint, .navbox"):
        junk.decompose()
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).replace(" ,", ",").replace(" .", ".").strip()


def wikipedia():
    doc = parse_page(PAGE)
    soup = BeautifulSoup(doc["html"], "lxml")
    root = soup.select_one(".mw-parser-output") or soup
    sections, cur = [], {"heading": "Lead", "level": 1, "paragraphs": []}
    skipping = False
    for el in root.find_all(["h2", "h3", "p", "ul", "blockquote"]):
        if el.find_parent(class_=re.compile(r"navbox|infobox|reflist|hatnote|thumb|metadata")):
            continue
        if el.name in ("h2", "h3"):
            if cur["paragraphs"]:
                sections.append(cur)
            cur = {"heading": clean(el), "level": int(el.name[1]), "paragraphs": []}
            if el.name == "h2":
                skipping = bool(SKIP.match(cur["heading"]))    # and its h3s with it
            continue
        if skipping or SKIP.match(cur["heading"]):
            continue
        if el.name == "ul":
            if el.find_parent("ul"):
                continue
            txt = [clean(li) for li in el.find_all("li", recursive=False)]
            txt = [t for t in txt if t]
            if txt:
                cur["paragraphs"].append({"kind": "list", "items": txt,
                                          "years": sorted(set(YEAR.findall(" ".join(txt))))})
            continue
        t = clean(el)
        if len(t) > 30:
            cur["paragraphs"].append({"kind": "quote" if el.name == "blockquote" else "text",
                                      "text": t, "years": sorted(set(YEAR.findall(t)))})
    if cur["paragraphs"]:
        sections.append(cur)
    sections = [s for s in sections if not SKIP.match(s["heading"])]
    return {"title": doc["title"], "pageid": doc["pageid"],
            "url": "https://en.wikipedia.org/wiki/" + doc["title"].replace(" ", "_"),
            "licence": "CC BY-SA 4.0 -- text of the English Wikipedia article, quoted verbatim",
            "sections": sections}


def wikidata():
    p = _cache_path("wd_full", QID)
    if p.exists():
        ent = json.loads(p.read_text(encoding="utf-8"))
    else:
        ent = _get(WD_API, {"action": "wbgetentities", "ids": QID, "languages": "en",
                            "props": "labels|descriptions|aliases|claims|sitelinks"})["entities"][QID]
        p.write_text(json.dumps(ent, ensure_ascii=False), encoding="utf-8")

    def val(snak):
        v = (snak.get("datavalue") or {}).get("value")
        if isinstance(v, dict) and "id" in v:
            return {"qid": v["id"]}
        if isinstance(v, dict) and "time" in v:
            return {"time": v["time"].lstrip("+")[:10], "precision": v.get("precision")}
        if isinstance(v, dict) and "text" in v:
            return {"text": v["text"]}
        return {"value": v}

    stmts, need = [], set()
    for prop, name in PROPS.items():
        for c in ent.get("claims", {}).get(prop, []):
            v = val(c["mainsnak"])
            quals = {}
            for qp, qs in (c.get("qualifiers") or {}).items():
                quals[qp] = [val(q) for q in qs]
            stmts.append({"property": prop, "property_label": name, **v, "qualifiers": quals,
                          "rank": c.get("rank")})
            for x in [v] + [q for qs in quals.values() for q in qs]:
                if "qid" in x:
                    need.add(x["qid"])
    labels = {}
    need = sorted(need)
    for i in range(0, len(need), 50):
        d = _get(WD_API, {"action": "wbgetentities", "ids": "|".join(need[i:i + 50]),
                          "props": "labels", "languages": "en"})
        for q, e in (d.get("entities") or {}).items():
            labels[q] = (e.get("labels", {}).get("en") or {}).get("value")
    for s in stmts:
        if "qid" in s:
            s["label"] = labels.get(s["qid"])
        for qs in s["qualifiers"].values():
            for q in qs:
                if "qid" in q:
                    q["label"] = labels.get(q["qid"])
    return {"qid": QID, "url": f"https://www.wikidata.org/wiki/{QID}",
            "label": (ent.get("labels", {}).get("en") or {}).get("value"),
            "description": (ent.get("descriptions", {}).get("en") or {}).get("value"),
            "aliases": [a["value"] for a in ent.get("aliases", {}).get("en", [])],
            "licence": "CC0",
            "sitelinks": len(ent.get("sitelinks") or {}),
            "statements": stmts}


def main():
    wp, wd = wikipedia(), wikidata()
    out = {"subject": KEY, "qid": QID,
           "generated_from": "en.wikipedia.org 'Randy Weston' + wikidata.org Q1371187 (cached)",
           "status": "SOURCE MATERIAL, UNJUDGED. Not checked against the transcript.",
           "why": "His interview covers 1997-2009 only; this is the outside record of the rest.",
           "wikipedia": wp, "wikidata": wd}
    (ROOT / KEY / "biography_sources.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(len(s["paragraphs"]) for s in wp["sections"])
    print(f"biography_sources.json: Wikipedia {len(wp['sections'])} sections, {n} paragraphs; "
          f"Wikidata {len(wd['statements'])} statements")
    for s in wp["sections"]:
        yrs = sorted({y for p in s["paragraphs"] for y in p["years"]})
        print(f"   {'  ' * (s['level'] - 2 if s['level'] > 1 else 0)}{s['heading'][:44]:46} "
              f"{len(s['paragraphs']):2} paras  {yrs[0] if yrs else ''}-{yrs[-1] if yrs else ''}")
    for prop in ("P569", "P19", "P570", "P20", "P166"):
        for s in wd["statements"]:
            if s["property"] == prop:
                when = [q.get("time") for q in s["qualifiers"].get("P585", [])]
                print(f"   {s['property_label']:18} {s.get('label') or s.get('time') or s.get('value')} {when or ''}")


if __name__ == "__main__":
    main()
