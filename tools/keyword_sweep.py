#!/usr/bin/env python3
"""
keyword_sweep.py

Runs many keywords through Apple's free public App Store search (the same
source as store_check.py) and shows, for each keyword, what the top results
look like. It is a quick first filter for niches, before you spend Appfigures
time on any of them.

Games are dropped from the results by default, because App Store search is
full of them and they bury the real tools. Use --games to keep them.

For each keyword it reads the top 10 non-game results and, among the top 5,
counts:
  real   apps with 100 to 2999 ratings (the limit is --small). Big enough to
         be a real product, small enough to be catchable.
  big    apps with 3000 or more ratings. A crowded keyword has several.
  weak   apps with 100 or more ratings that are either not updated in over a
         year or rated under 4.0 stars. These are the leaders that could be
         beaten.
  new    apps first released in the last year.
Keywords are listed with the most weak and real apps first, and big apps last.
Always read the top 5 list under each keyword. The counts only point at it.

What it cannot tell you: revenue, downloads or how many people search the
keyword. Apple orders results by relevance, not by earnings. A known earner can
be missing from a keyword's top 5 because people find it under another name.
Check the interesting keywords in Appfigures (Keyword Inspector for popularity,
then the app pages for revenue), then run review_check.py.

No login, no keys, no extra packages. Python 3.8 or newer.

Usage:
    python3 keyword_sweep.py                      # built-in keyword list, UK store
    python3 keyword_sweep.py -f my_keywords.txt   # your own list, one per line
    python3 keyword_sweep.py "life in the uk test" "british citizenship test"
    python3 keyword_sweep.py --bucket logbooks    # only one built-in group
    python3 keyword_sweep.py --games              # keep games in the results

A keywords file can have lines starting with ## to name a group, and lines
starting with # to be ignored.

Output: keyword_sweep_<country>_<date>[_<tag>].md and .csv in the current
folder. The .csv has every app from every keyword.
"""

import argparse
import csv
import datetime
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BUILTIN = {
    "sports tools": [
        "darts scoreboard", "darts practice", "darts checkout",
        "football referee", "rugby referee", "cricket umpire",
        "cricket scoring", "cricket scorer",
        "padel", "padel scoring", "pickleball", "tennis scoring",
        "squash", "badminton", "snooker scoring", "bowls scoring",
        "golf handicap", "golf society", "golf scorecard uk",
        "coarse fishing log", "fishing log",
        "running plan 10k", "couch to 5k", "parkrun", "triathlon training",
        "swim training", "climbing log", "bouldering", "boxing training",
        "martial arts", "horse riding", "dressage test", "showjumping",
        "pony club", "cycling training", "sportive",
    ],
    "logbooks": [
        "sailing logbook", "yachtmaster sea miles", "rya logbook",
        "scuba dive log", "pilot logbook", "mountain leader log",
        "coaching log", "kayak log", "climbing logbook",
    ],
    "work and rules": [
        "cscs card test", "cscs health and safety test", "driver cpc",
        "taxi knowledge", "private hire test", "sia door supervisor",
        "personal licence", "food hygiene level 2", "fire marshal",
        "first aid at work", "manual handling", "forklift test",
        "track safety rail", "adi part 1", "motorcycle theory test",
        "pcv theory test", "tachograph", "drivers hours",
        "mileage tracker", "timesheet", "holiday pay calculator",
        "overtime calculator", "redundancy pay", "gas safe",
        "18th edition", "risk assessment", "pat testing", "fire logbook",
        "police sergeant exam", "firefighter test", "prison officer test",
        "civil service test", "ilr absence",
    ],
}

SEARCH_URL = "https://itunes.apple.com/search?"
HEADERS = {"User-Agent": "Mozilla/5.0 (slipstream keyword_sweep)"}
FETCH_LIMIT = 30  # ask for more than 10 so dropping games still leaves 10


def fetch(term, country, retries=3):
    q = urllib.parse.urlencode(
        {"term": term, "entity": "software", "country": country, "limit": FETCH_LIMIT})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(SEARCH_URL + q, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("could not search '{}': {}".format(term, last))


def days_since(iso, today):
    try:
        then = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (today - then).days
    except (ValueError, AttributeError):
        return None


def summarise(term, group, data, small, today, games=False):
    results = [a for a in data.get("results", [])
               if games or a.get("primaryGenreName") != "Games"][:10]
    apps = []
    for i, a in enumerate(results, start=1):
        apps.append({
            "keyword": term,
            "group": group,
            "rank": i,
            "name": a.get("trackName", ""),
            "seller": a.get("sellerName") or a.get("artistName", ""),
            "ratings": a.get("userRatingCount") or 0,
            "avg_rating": round(a.get("averageUserRating") or 0, 2),
            "price": a.get("formattedPrice", ""),
            "genre": a.get("primaryGenreName", ""),
            "days_since_update": days_since(a.get("currentVersionReleaseDate", ""), today),
            "days_since_release": days_since(a.get("releaseDate", ""), today),
            "store_id": str(a.get("trackId", "")),
            "url": (a.get("trackViewUrl", "") or "").split("?")[0],
        })
    top5 = apps[:5]

    def weak(a):
        if a["ratings"] < 100:
            return False
        stale = a["days_since_update"] is not None and a["days_since_update"] > 365
        poor = 0 < a["avg_rating"] < 4.0
        return stale or poor

    stats = {
        "keyword": term,
        "group": group,
        "results": len(apps),
        "leader": apps[0]["name"] if apps else "",
        "leader_ratings": apps[0]["ratings"] if apps else 0,
        "median_top5": int(statistics.median([a["ratings"] for a in top5])) if top5 else 0,
        "real_top5": sum(1 for a in top5 if 100 <= a["ratings"] < small),
        "big_top5": sum(1 for a in top5 if a["ratings"] >= small),
        "weak_top5": sum(1 for a in top5 if weak(a)),
        "new_top5": sum(1 for a in top5
                        if a["days_since_release"] is not None and a["days_since_release"] < 365),
    }
    return stats, apps


def load_keywords(args):
    """Return a list of (group, keyword)."""
    out = []
    if args.keywords:
        out += [("typed", k) for k in args.keywords]
    if args.file:
        group = "file"
        with open(args.file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("##"):
                    group = line.lstrip("#").strip() or group
                elif line.startswith("#"):
                    continue
                else:
                    out.append((group, line))
    if not out:
        for g, kws in BUILTIN.items():
            if args.bucket and args.bucket.lower() not in g.lower():
                continue
            out += [(g, k) for k in kws]
    seen, uniq = set(), []
    for g, k in out:
        if k.lower() not in seen:
            seen.add(k.lower())
            uniq.append((g, k))
    return uniq


def write_outputs(stem, country, small, stats_list, all_apps, failed, games):
    cols = ["keyword", "group", "rank", "name", "seller", "ratings", "avg_rating", "price",
            "genre", "days_since_update", "days_since_release", "store_id", "url"]
    with open(stem + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_apps)

    lines = ["Keyword sweep, {} store, {}".format(country.upper(), datetime.date.today()), ""]
    lines.append("Top 10 App Store search results per keyword{}. Counts are for the top 5:".format(
        ", games included" if games else ", games removed"))
    lines.append("real = 100 to {} ratings, big = {} or more ratings, "
                 "weak = 100 or more ratings but not updated in a year or under 4.0 stars, "
                 "new = first released in the last year.".format(small - 1, small))
    lines.append("Apple orders results by relevance, not revenue, and a known earner can be "
                 "missing from a keyword it is not found under. This is a first filter only. "
                 "Read the top 5 under each keyword before believing a count.")
    lines.append("")
    lines.append("Keywords with weak or real apps first, crowded ones last")
    lines.append("")
    lines.append("| Keyword | Group | Leader | Leader ratings | Median ratings, top 5 | Real | Big | Weak | New |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    ranked = sorted(stats_list,
                    key=lambda s: (-s["weak_top5"], -s["real_top5"], s["big_top5"], s["median_top5"]))
    for s in ranked:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            s["keyword"], s["group"], s["leader"], s["leader_ratings"], s["median_top5"],
            s["real_top5"], s["big_top5"], s["weak_top5"], s["new_top5"]))
    lines.append("")
    lines.append("Top 5 for each keyword")
    by_kw = {}
    for a in all_apps:
        by_kw.setdefault(a["keyword"], []).append(a)
    for s in ranked:
        lines.append("")
        lines.append("{} ({})".format(s["keyword"], s["group"]))
        for a in by_kw.get(s["keyword"], [])[:5]:
            upd = "{}d".format(a["days_since_update"]) if a["days_since_update"] is not None else "?"
            lines.append("  {}. {}  ({} ratings, {} stars, {}, updated {} ago, {})".format(
                a["rank"], a["name"], a["ratings"], a["avg_rating"], a["price"], upd, a["url"]))
    if failed:
        lines.append("")
        lines.append("Keywords that could not be searched: " + ", ".join(failed))
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description="Sweep many keywords through App Store search.")
    p.add_argument("keywords", nargs="*", help="keywords typed on the command line")
    p.add_argument("-f", "--file", help="text file with one keyword per line")
    p.add_argument("--bucket", default="", help="only this built-in group: sports, logbooks, work")
    p.add_argument("--country", default="gb", help="two letter store code, default gb")
    p.add_argument("--small", type=int, default=3000,
                   help="ratings at or above this count as big, default 3000")
    p.add_argument("--games", action="store_true", help="keep games in the results")
    p.add_argument("--tag", default="", help="text added to the output file names")
    args = p.parse_args(argv)

    kws = load_keywords(args)
    if not kws:
        print("No keywords to search.")
        return 2
    today = datetime.datetime.now(datetime.timezone.utc)
    print("Searching {} keywords in the {} store...".format(len(kws), args.country.upper()))
    stats_list, all_apps, failed = [], [], []
    for n, (group, term) in enumerate(kws, start=1):
        try:
            data = fetch(term, args.country)
        except RuntimeError as e:
            print("  {}/{} skipped: {}".format(n, len(kws), e))
            failed.append(term)
            continue
        s, apps = summarise(term, group, data, args.small, today, args.games)
        stats_list.append(s)
        all_apps += apps
        print("  {}/{} {}: {} results, real {}, big {}, weak {}, new {}".format(
            n, len(kws), term, s["results"], s["real_top5"], s["big_top5"],
            s["weak_top5"], s["new_top5"]))
        time.sleep(1.5)
    if not stats_list:
        print("Nothing came back. If every search failed, the network is probably blocked.")
        return 1
    stem = "keyword_sweep_{}_{}".format(args.country, datetime.date.today().isoformat())
    if args.tag:
        stem += "_" + args.tag
    write_outputs(stem, args.country, args.small, stats_list, all_apps, failed, args.games)
    print("Wrote {0}.md and {0}.csv ({1} keywords, {2} apps).".format(stem, len(stats_list), len(all_apps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
