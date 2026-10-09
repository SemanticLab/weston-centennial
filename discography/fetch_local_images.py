#!/usr/bin/env python
"""Download every image the site uses into the repo, so the page serves its own.

The page was pointing portraits at commons.wikimedia.org and sleeves at
coverartarchive.org. That works, but it puts ~600 cross-origin requests to two
third-party hosts on the critical path of every page load -- Commons in
particular redirects `Special:FilePath` to upload.wikimedia.org before serving a
byte, and the Cover Art Archive redirects again to whichever archive.org storage
node is live. Serving them from `img/` alongside the page removes both hops
and the two external dependencies.

Only Weston himself gets a second, larger size, for a hero image; everyone else
appears in a small avatar circle, where the 200px file is already ~4x and a
400px one is pure weight. Sleeves come
at 250px, the size the grid asks for.

Files are named by the stable id -- Wikidata QID for a person, MusicBrainz
release-group MBID for a release -- not by title, so a renamed album or a
re-cased name does not orphan its image. Anything already on disk is skipped, so
a re-run is free and a partial run resumes.

Licensing is unchanged by copying the bytes: portraits stay under whatever
Commons licence `shared/images.json` records (many require attribution), and
cover art remains copyrighted and shown for identification. `img/CREDITS.json`
is written next to the files so the terms travel with them.
"""
import json, os, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "img")
UA = ("weston-centennial/1.0 (Randy Weston centennial oral-history project; "
      "https://github.com/thisismattmiller) python-urllib")

HERO = {"Q1371187"}                  # Weston himself -- the only 400px image

_LOCK, _last, MIN_GAP = threading.Lock(), [0.0], 0.12


def _throttle():
    with _LOCK:
        w = MIN_GAP - (time.monotonic() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.monotonic()


def grab(url, path, retries=3):
    """-> True if the file is on disk afterwards."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    for a in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) < 100:                      # an error page, not an image
                return False
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            return True
        except urllib.error.HTTPError as ex:
            if ex.code in (404, 400, 403):
                return False
            time.sleep((8 if ex.code == 429 else 2) * (a + 1))
        except Exception:
            time.sleep(2 * (a + 1))
    return False


def main():
    people = json.load(open(os.path.join(ROOT, "shared", "images.json")))["people"]
    art = json.load(open(os.path.join(ROOT, "shared", "cover_art.json")))["items"]

    jobs, credits = [], {"portraits": {}, "covers": {}}
    for qid, p in people.items():
        im = p.get("image") or {}
        if not im.get("url_full"):
            continue
        base = im["url_full"]
        jobs.append((f"{base}?width=200", os.path.join(OUT, "p", f"{qid}.jpg")))
        if qid in HERO:
            jobs.append((f"{base}?width=400", os.path.join(OUT, "p", f"{qid}@2x.jpg")))
        credits["portraits"][qid] = {
            "name": p.get("name"), "file": im.get("file"),
            "commons_page": im.get("commons_page"),
            "licence": im.get("license") or im.get("licence"),
            "artist": im.get("artist") or im.get("author"),
            "attribution": im.get("attribution"),
        }
    for mb, r in art.items():
        jobs.append((r["thumb_250"], os.path.join(OUT, "a", f"{mb}.jpg")))
        credits["covers"][mb] = {"title": r.get("title"), "released": r.get("released"),
                                 "qid": r.get("qid")}

    todo = [j for j in jobs if not os.path.exists(j[1])]
    print(f"{len(jobs)} images referenced, {len(jobs)-len(todo)} already on disk, "
          f"{len(todo)} to fetch", flush=True)

    done, ok, lock, t0 = [0], [0], threading.Lock(), time.monotonic()

    def work(job):
        got = grab(*job)
        with lock:
            done[0] += 1
            ok[0] += bool(got)
            if done[0] % 50 == 0:
                el = time.monotonic() - t0
                rate = done[0] / max(el, 1)
                print(f"  [{done[0]}/{len(todo)}] {ok[0]} ok  "
                      f"{el/60:.1f}m  eta {(len(todo)-done[0])/max(rate,.01)/60:.1f}m",
                      flush=True)
        return got

    with ThreadPoolExecutor(max_workers=8) as ex:
        [f.result() for f in as_completed([ex.submit(work, j) for j in todo])]

    os.makedirs(OUT, exist_ok=True)
    credits["_note"] = (
        "Portraits are from Wikimedia Commons under the licence recorded per file; "
        "many require attribution. Album covers are from the Cover Art Archive, are "
        "under copyright, and are reproduced for identification only.")
    json.dump(credits, open(os.path.join(OUT, "CREDITS.json"), "w"),
              ensure_ascii=False, indent=1)

    np = len([f for f in os.listdir(os.path.join(OUT, "p"))]) if os.path.isdir(os.path.join(OUT, "p")) else 0
    na = len([f for f in os.listdir(os.path.join(OUT, "a"))]) if os.path.isdir(os.path.join(OUT, "a")) else 0
    mb_ = sum(os.path.getsize(os.path.join(dp, f))
              for dp, _, fs in os.walk(OUT) for f in fs) / 1e6
    print(f"\n{np} portrait files, {na} cover files, {mb_:.1f} MB in {OUT}")


if __name__ == "__main__":
    main()
