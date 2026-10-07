#!/usr/bin/env python3
"""
keyword_sweep.py

Runs many keywords through Apple's free public App Store search (the same
source as store_check.py) and shows, for each keyword, whether small apps sit
near the top. It is a quick first filter for niches, before you spend
Appfigures time on any of them.

For each keyword it reads the top 10 results and counts, among the top 5:
  small  apps with 20 to 2999 ratings in the store you chose (default limit 3000)
  stale  apps whose last update was over a year ago
  new    apps first released in the last year
A keyword with small or new apps near the top, and a leader that has not been
updated, is worth a closer look. A keyword where the top 5 are all huge,
fresh apps is probably crowded.

What it cannot tell you: revenue, downloads or how many people search the
keyword. Apple orders results by relevance, not by earnings. Check the
interesting keywords in Appfigures (Keyword Inspector for popularity, then the
app pages for revenue), then run review_check.py.

No login, no keys, no extra packages. Python 3.8 or newer.

Usage:
    python3 keyword_sweep.py                      # built-in keyword list, UK store
    python3 keyword_sweep.py -f my_keywords.txt   # your own list, one per line
    python3 keyword_sweep.py "darts scoreboard" "referee app"
    python3 keyword_sweep.py --bucket logbooks    # only one built-in group
    python3 keyword_sweep.py --small 2000         # change what counts as small

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


def fetch(term, country, retries=3):
    q = urllib.parse.urlencode(
        {"term": term, "entity": "software", "country": country, "limit": 10})
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


def summarise(term, group, data, small, today):
    apps = []
    for i, a in enumerate(data.get("results", [])[:10], start=1):
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
    stats = {
        "keyword": term,
        "group": group,
        "results": len(apps),
        "leader": apps[0]["name"] if apps else "",
        "leader_ratings": apps[0]["ratings"] if apps else 0,
        "median_top5": int(statistics.median([a["ratings"] for a in top5])) if top5 else 0,
        "small_top5": sum(1 for a in top5 if 20 <= a["ratings"] < small),
        "stale_top5": sum(1 for a in top5
                          if a["days_since_update"] is not None and a["days_since_update"] > 365),
        "new_top5": sum(1 for a in top5
                        if a["days_since_release"] is not None and a["days_since_release"] < 365),
        "sellers_top10": len({a["seller"] for a in apps}),
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


def write_outputs(stem, country, small, stats_list, all_apps, failed):
    cols = ["keyword", "group", "rank", "name", "seller", "ratings", "avg_rating", "price",
            "genre", "days_since_update", "days_since_release", "store_id", "url"]
    with open(stem + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_apps)

    lines = ["Keyword sweep, {} store, {}".format(country.upper(), datetime.date.today()), ""]
    lines.append("Top 10 App Store search results per keyword. Counts are for the top 5: "
                 "small = 20 to {} ratings, stale = not updated in over a year, "
                 "new = first released in the last year.".format(small))
    lines.append("Apple orders results by relevance, not revenue. This is a first filter only.")
    lines.append("")
    lines.append("Most promising first (small, stale and new apps near the top)")
    lines.append("")
    lines.append("| Keyword | Group | Leader | Leader ratings | Median ratings, top 5 | Small | Stale | New |")
    lines.append("|---|---|---|---|---|---|---|---|")
    ranked = sorted(stats_list,
                    key=lambda s: (-(s["small_top5"] + s["stale_top5"] + s["new_top5"]),
                                   s["median_top5"]))
    for s in ranked:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            s["keyword"], s["group"], s["leader"], s["leader_ratings"], s["median_top5"],
            s["small_top5"], s["stale_top5"], s["new_top5"]))
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
    p.add_argument("--small", type=int, default=3000, help="ratings below this count as small, default 3000")
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
        s, apps = summarise(term, group, data, args.small, today)
        stats_list.append(s)
        all_apps += apps
        print("  {}/{} {}: {} results, small {}, stale {}, new {}".format(
            n, len(kws), term, s["results"], s["small_top5"], s["stale_top5"], s["new_top5"]))
        time.sleep(1.5)
    if not stats_list:
        print("Nothing came back. If every search failed, the network is probably blocked.")
        return 1
    stem = "keyword_sweep_{}_{}".format(args.country, datetime.date.today().isoformat())
    if args.tag:
        stem += "_" + args.tag
    write_outputs(stem, args.country, args.small, stats_list, all_apps, failed)
    print("Wrote {0}.md and {0}.csv ({1} keywords, {2} apps).".format(stem, len(stats_list), len(all_apps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
