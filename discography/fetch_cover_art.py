#!/usr/bin/env python
"""Resolve album cover thumbnails from the Cover Art Archive.

Commons has almost no cover art, because album covers are not freely licensed
and Commons only hosts free media. Most releases do carry a MusicBrainz
release-group ID (Wikidata P436), and the Cover Art Archive serves art keyed on
exactly that. The art is copyrighted; MusicBrainz supplies it for
identification, which is what a discography thumbnail is. Using it was an
explicit editorial call in the Coltrane / Davis build this is ported from, and
is carried over here on the same terms -- revisit it before publishing.

Two things this checks rather than assumes:

- Not every release group has art. `/front-250` 404s when none exists, so every
  ID is probed and only confirmed hits are written. Emitting the URL pattern for
  all 247 would put broken images on the page.
- A release-group ID can 404 while the release itself has art, and vice versa.
  Only the release-group endpoint is used here -- it is the one keyed to what
  Wikidata gave us, and falling back to a guessed release ID would attach the
  wrong pressing's artwork to the record.

Responses are cached on disk so a re-run costs nothing, matching the rest of the
discography pipeline.
"""
import json, os, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "discography", "cache", "coverart")
OUT = os.path.join(ROOT, "shared", "cover_art.json")
CAA = "https://coverartarchive.org/release-group/{}/front-{}"
UA = ("weston-centennial/1.0 (Randy Weston centennial oral-history project; "
      "https://github.com/thisismattmiller) python-urllib")

_LOCK, _last, MIN_GAP = threading.Lock(), [0.0], 0.25


def _throttle():
    with _LOCK:
        w = MIN_GAP - (time.monotonic() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.monotonic()


def probe(mbid, size=250, retries=3):
    """-> resolved image URL, or None when the release group has no front cover."""
    cp = os.path.join(CACHE, f"{mbid}-{size}.json")
    if os.path.exists(cp):
        return json.load(open(cp)).get("url")
    url = CAA.format(mbid, size)
    got = None
    for a in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
            with urllib.request.urlopen(req, timeout=45) as r:
                # urllib follows the 307 to the archive.org bucket; keep the
                # resolved location so the page never pays for the redirect.
                got = r.geturl()
                r.read(1)
            break
        except urllib.error.HTTPError as ex:
            if ex.code in (404, 400):
                break                      # no art for this release group
            time.sleep((8 if ex.code == 429 else 2) * (a + 1))
        except Exception:
            time.sleep(2 * (a + 1))
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"url": got}, open(cp, "w"))
    return got


def main():
    rel = {}
    for s in ("weston",):
        for r in json.load(open(os.path.join(ROOT, s, "discography.json")))["releases"]:
            if r.get("musicbrainz"):
                rel.setdefault(r["musicbrainz"], {
                    "title": r["title"], "kind": r["kind"], "released": r.get("released"),
                    "qid": r.get("qid"), "subjects": []})
                rel[r["musicbrainz"]]["subjects"].append(s)
    print(f"{len(rel)} release groups with a MusicBrainz id", flush=True)

    done, lock, t0 = [0], threading.Lock(), time.monotonic()

    def work(mb):
        u = probe(mb)
        with lock:
            done[0] += 1
            if done[0] % 40 == 0:
                el = time.monotonic() - t0
                print(f"  [{done[0]}/{len(rel)}] {el/60:.1f}m", flush=True)
        return mb, u

    with ThreadPoolExecutor(max_workers=4) as ex:
        for mb, u in [f.result() for f in as_completed([ex.submit(work, m) for m in rel])]:
            if u:
                # Ship the canonical coverartarchive.org URL, not the resolved
                # one. The probe lands on a specific archive.org storage node
                # (dn710203.ca.archive.org/...), which is load-balancer assigned
                # and goes stale; the /release-group/<id>/front-250 form is the
                # documented stable entry point and redirects to whichever node
                # is live. `resolved` is kept only as evidence the art exists.
                rel[mb]["thumb_250"] = CAA.format(mb, 250)
                rel[mb]["thumb_500"] = CAA.format(mb, 500)
                rel[mb]["resolved"] = u

    hit = {m: v for m, v in rel.items() if v.get("thumb_250")}
    json.dump({
        "source": "Cover Art Archive, keyed on the MusicBrainz release-group id "
                  "carried in Wikidata P436",
        "licence": "Cover art is copyrighted and supplied by MusicBrainz for "
                   "identification. Not freely licensed — unlike shared/images.json, "
                   "these must not be treated as reusable media.",
        "release_groups_probed": len(rel),
        "with_cover": len(hit),
        "items": hit,
    }, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\n{len(hit)}/{len(rel)} release groups have front cover art -> {OUT}")


if __name__ == "__main__":
    main()
