#!/usr/bin/env python3
"""Step 4b - his release groups on MusicBrainz, for the records Wikipedia has no article for.

24 of the 51 albums on his "As leader" list have no Wikipedia article (most of
the 1970s, and everything after 1998 except Khepera). No article means no
Wikidata item, so no MusicBrainz id (P436) and no sleeve from the Cover Art
Archive -- the half of his discography he actually talks about in his 2009
interview (Saga, Earth Birth, Ancient Future, Zep Tepi) would be blank squares.

MusicBrainz knows them. This lists every release group credited to his artist
entry (found through Wikidata P434, not by name search) and writes them to
discography/raw/musicbrainz_release_groups.json. build_discography.py then
gives an un-articled release a MusicBrainz id only on an exact normalised
title match with a release group of his -- never a fuzzy one -- and records
that it did so (`musicbrainz_matched_by: "title"`).

MusicBrainz asks for one request a second and a descriptive User-Agent.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_common import UA, WD_API, _cache_path, _get  # noqa: E402

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
SUBJECT_QID = "Q1371187"
MB = "https://musicbrainz.org/ws/2/"


def mb_get(path, params):
    key = path + "?" + urllib.parse.urlencode(sorted(params.items()))
    p = _cache_path("musicbrainz", key)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    time.sleep(1.1)
    req = urllib.request.Request(MB + path + "?" + urllib.parse.urlencode({**params, "fmt": "json"}),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def main():
    d = _get(WD_API, {"action": "wbgetclaims", "entity": SUBJECT_QID, "property": "P434"})
    claims = d.get("claims", {}).get("P434") or []
    if not claims:
        sys.exit(f"FATAL: {SUBJECT_QID} has no MusicBrainz artist id (P434)")
    artist = claims[0]["mainsnak"]["datavalue"]["value"]

    groups, offset = [], 0
    while True:
        page = mb_get("release-group", {"artist": artist, "limit": 100, "offset": offset})
        got = page.get("release-groups") or []
        groups += got
        offset += len(got)
        if not got or offset >= page.get("release-group-count", 0):
            break

    out = [{"mbid": g["id"], "title": g["title"],
            "first_release_date": g.get("first-release-date") or None,
            "primary_type": g.get("primary-type"),
            "secondary_types": g.get("secondary-types") or []} for g in groups]
    out.sort(key=lambda g: (g["first_release_date"] or "9999", g["title"]))
    RAW.mkdir(exist_ok=True)
    (RAW / "musicbrainz_release_groups.json").write_text(json.dumps(
        {"artist_mbid": artist, "source": f"musicbrainz.org release groups for artist {artist} "
                                           f"(Wikidata {SUBJECT_QID} P434)",
         "count": len(out), "release_groups": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"MusicBrainz artist {artist}: {len(out)} release groups "
          f"({sum(1 for g in out if g['primary_type'] == 'Album')} albums)")


if __name__ == "__main__":
    main()
