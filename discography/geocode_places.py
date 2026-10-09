#!/usr/bin/env python3
"""Put the places of Weston's interview on a map.

Weston's 2009 interview is a string of journeys -- Tangier, Jajouka, Kyoto,
Canterbury, Alexandria, Aswan, the Mississippi Delta -- and the reading pass
(extract/OWN_VOICE_SPEC.md, Part C) recorded each with a corrected `place` and
a `country`. This step turns those strings into coordinates, from Wikidata.

It is deliberately dumb, so that it can be checked:

  1. search Wikidata for the whole place string ("Kamigamo Shrine, Kyoto"),
     then for each comma-separated part from the most specific to the least;
  2. take the first hit that HAS coordinates (P625) and whose country (P17)
     is the one the reader gave -- a hit in the wrong country is skipped, never
     taken (there is a Tangier in Indiana and an Alexandria in Virginia);
  3. check a specific hit against the broader part of the same string: a
     "Temple of Isis" 780 km from Aswan, or an "Evergreen Cemetery" that is in
     Los Angeles when the string says Brooklyn, is the wrong one and is
     skipped (more than 250 km from the place it is said to be in);
  4. record what was matched and how specific it is:
        site     the whole string, or its first part, matched (a building, a venue)
        town     only a later, broader part matched (the city it is in)
        country  the place IS the country ("Saint Lucia")
     and leave lat/lon null when nothing passes.

Only the journeys are geocoded. Timeline entries carry a free-text `place`
too, but without a country to check against, and every one of them points (by
block) at a journey that has been placed.

Nothing is guessed: an unresolved place stays unresolved and is listed at the
end for a human. Results are cached under discography/cache/geo/.

Output: shared/places.json
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_common import WD_API, _cache_path, _get  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "weston"

# country names as a reader writes them -> Wikidata country item
COUNTRY_QID = {
    "united states": "Q30", "usa": "Q30", "us": "Q30", "united states of america": "Q30",
    "morocco": "Q1028", "egypt": "Q79", "japan": "Q17", "france": "Q142",
    "united kingdom": "Q145", "england": "Q145", "uk": "Q145",
    "canada": "Q16", "switzerland": "Q39", "saint lucia": "Q760", "st. lucia": "Q760",
    "st lucia": "Q760", "senegal": "Q1041", "ghana": "Q117", "nigeria": "Q1033",
    "belgium": "Q31", "italy": "Q38", "germany": "Q183", "spain": "Q29",
    "china": "Q148", "jamaica": "Q766", "cuba": "Q241", "brazil": "Q155",
    "mali": "Q912", "tunisia": "Q948", "algeria": "Q262", "lebanon": "Q822",
    "netherlands": "Q55", "sweden": "Q34", "norway": "Q20", "denmark": "Q35",
}
# P31 values that are never a place on a map, however well the label matches
NOT_A_PLACE = {"Q5", "Q4167410", "Q13442814", "Q482994", "Q11424", "Q7725634", "Q134556",
               "Q215380", "Q4830453", "Q101352", "Q202444"}


def search(text):
    p = _cache_path("geo", "search::" + text)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    d = _get(WD_API, {"action": "wbsearchentities", "search": text, "language": "en",
                      "type": "item", "limit": 7})
    out = [{"qid": h["id"], "label": h.get("label"), "description": h.get("description")}
           for h in d.get("search", [])]
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def entity(qid):
    p = _cache_path("geo", "ent::" + qid)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    d = _get(WD_API, {"action": "wbgetentities", "ids": qid, "props": "claims|labels|descriptions",
                      "languages": "en"})
    e = (d.get("entities") or {}).get(qid) or {}
    claims = e.get("claims") or {}

    def ids(prop):
        return [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id")
                for c in claims.get(prop, [])
                if isinstance(((c.get("mainsnak") or {}).get("datavalue") or {}).get("value"), dict)]

    coord = None
    for c in claims.get("P625", []):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and "latitude" in v:
            coord = (round(v["latitude"], 5), round(v["longitude"], 5))
            break
    out = {"qid": qid, "label": (e.get("labels", {}).get("en") or {}).get("value"),
           "description": (e.get("descriptions", {}).get("en") or {}).get("value"),
           "coord": coord, "country": ids("P17"), "instance_of": ids("P31")}
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def candidates(place):
    """Search strings, most specific first: the whole thing, then each part."""
    place = re.sub(r"\s+", " ", place).strip()
    parts = [x.strip() for x in place.split(",") if x.strip()]
    out = [(place, "site")]
    for n, part in enumerate(parts):
        if part != place:
            out.append((part, "site" if n == 0 else "town"))
        # "Kamigamo Shrine, Kyoto" -> also "Kyoto" alone is already covered; try
        # the part with the next one for ambiguous town names ("Tangier, Morocco")
        if n + 1 < len(parts):
            out.append((f"{part}, {parts[n + 1]}", "site" if n == 0 else "town"))
    seen, uniq = set(), []
    for s, prec in out:
        if s.lower() not in seen:
            seen.add(s.lower())
            uniq.append((s, prec))
    return uniq


def km(a, b):
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


MAX_KM = 250


def first_hit(text, want):
    for hit in search(text):
        e = entity(hit["qid"])
        if e["coord"] and not set(e["instance_of"]) & NOT_A_PLACE and (not want or want in e["country"]):
            return e
    return None


def geocode(place, country):
    want = COUNTRY_QID.get((country or "").strip().lower())
    tried = []
    if place.strip().lower() in COUNTRY_QID and COUNTRY_QID[place.strip().lower()] == want:
        e = entity(want)
        if e["coord"]:
            return {"lat": e["coord"][0], "lon": e["coord"][1], "qid": e["qid"],
                    "label": e["label"], "description": e["description"],
                    "matched_on": place, "precision": "country", "rejected": tried}
    # the broadest named part (not the country) anchors the more specific ones
    parts = [x.strip() for x in place.split(",") if x.strip() and x.strip().lower() not in COUNTRY_QID]
    anchor = first_hit(parts[-1], want) if len(parts) > 1 else None
    for text, precision in candidates(place):
        # a part that is just the country name is not a place to pin
        if text.strip().lower() in COUNTRY_QID:
            continue
        for hit in search(text):
            e = entity(hit["qid"])
            if not e["coord"] or set(e["instance_of"]) & NOT_A_PLACE:
                continue
            if want and want not in e["country"]:
                tried.append(f"{text!r} -> {hit['qid']} {e['label']} (wrong country)")
                continue
            if not want and country:
                tried.append(f"{text!r} -> {hit['qid']} (country {country!r} not in table)")
                continue
            # a U.S. state's coordinate is its centroid: Brooklyn is 275 km from "New York"
            limit = 350 if anchor and "Q35657" in anchor["instance_of"] else MAX_KM
            if anchor and anchor["qid"] != e["qid"] and km(anchor["coord"], e["coord"]) > limit:
                tried.append(f"{text!r} -> {hit['qid']} {e['label']} "
                             f"({km(anchor['coord'], e['coord']):.0f} km from {anchor['label']})")
                continue
            return {"lat": e["coord"][0], "lon": e["coord"][1], "qid": e["qid"],
                    "label": e["label"], "description": e["description"],
                    "matched_on": text, "precision": precision, "rejected": tried}
    return {"lat": None, "lon": None, "qid": None, "label": None, "description": None,
            "matched_on": None, "precision": None, "rejected": tried}


def main():
    ov = ROOT / SUBJECT / "own_voice_output"
    items = []
    jp = ov / "journeys.json"
    if jp.exists():
        for j in json.loads(jp.read_text(encoding="utf-8"))["items"]:
            if j.get("place"):
                items.append({"key": j["key"], "source": "journeys", "title": j.get("title"),
                              "place": j["place"], "country": j.get("country") or "",
                              "year": j.get("year")})
    out = []
    for it in items:
        g = geocode(it["place"], it["country"])
        out.append({**it, **g})

    (ROOT / "shared").mkdir(exist_ok=True)
    ok = [o for o in out if o["lat"] is not None]
    (ROOT / "shared" / "places.json").write_text(json.dumps({
        "subject": SUBJECT, "generated_from": "own_voice_output/journeys.json, "
                                              "geocoded against Wikidata (P625, checked against P17)",
        "count": len(out), "with_coordinates": len(ok),
        "method": __doc__.split("Output:")[0].strip(),
        "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"places.json: {len(out)} places, {len(ok)} with coordinates "
          f"({sum(1 for o in ok if o['precision'] == 'site')} site, "
          f"{sum(1 for o in ok if o['precision'] == 'town')} town, "
          f"{sum(1 for o in ok if o['precision'] == 'country')} country)")
    for o in out:
        tag = f"{o['lat']:8.3f},{o['lon']:9.3f} {o['precision']:7} {o['label']}" if o["lat"] is not None \
            else "    --  UNRESOLVED"
        if o["rejected"]:
            tag += f"   (skipped: {'; '.join(o['rejected'])[:110]})"
        print(f"  {o['key'][:28]:28} {o['place'][:38]:38} {o['country'][:14]:14} {tag}")


if __name__ == "__main__":
    main()
