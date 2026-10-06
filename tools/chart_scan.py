#!/usr/bin/env python3
"""
chart_scan.py

Scans Apple's public top grossing charts across many App Store categories and
lists apps that earn well but have a modest number of ratings. These are the
small, earning apps the Slipstream method starts from.

New: it also looks each app up in other big stores (US, Germany, Canada,
Australia, France by default) and works out how much of the ratings sit in the
store you are scanning. A big global app can look small in one store. The UK
share column catches that. Use --min-share to keep only apps whose ratings are
mostly in the scanned store, for example --min-share 0.6.

What it uses: only Apple's free public feeds (the top grossing RSS feed and the
iTunes lookup API). No login, no keys, no extra packages. Python 3.8 or newer.

What it cannot tell you: downloads or revenue. A high top grossing rank with few
ratings is a hint that an app earns, not proof. Check the best few in
Appfigures, then run review_check.py on them.

Limits of the share figure: it only compares the stores listed in --compare, so
an app that is big in a store not on the list can still look more local than it
is. Apple's feed stops at 100 chart positions per category.

Usage:
    python3 chart_scan.py                                  # UK, all categories except Games
    python3 chart_scan.py --min-ratings 200 --max-ratings 3000 --min-share 0.6
    python3 chart_scan.py --country us --compare gb,de,ca,au,fr
    python3 chart_scan.py --genres 6013,6017               # only some categories
    python3 chart_scan.py --compare ""                     # skip the share check
    python3 chart_scan.py --tag uk-niche                   # adds a tag to the file names

Output: chart_scan_<country>_<date>[_<tag>].csv and .md in the current folder.
"""

import argparse
import csv
import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Apple genre ids. Games (6014) is left out on purpose, add it with --genres 6014.
GENRES = {
    6000: "Business",
    6002: "Utilities",
    6003: "Travel",
    6004: "Sports",
    6005: "Social Networking",
    6006: "Reference",
    6007: "Productivity",
    6008: "Photo & Video",
    6009: "News",
    6010: "Navigation",
    6011: "Music",
    6012: "Lifestyle",
    6013: "Health & Fitness",
    6015: "Finance",
    6016: "Entertainment",
    6017: "Education",
    6018: "Books",
    6020: "Medical",
    6023: "Food & Drink",
    6024: "Shopping",
}

DEFAULT_COMPARE = "us,de,ca,au,fr"

FEED_URL = "https://itunes.apple.com/{cc}/rss/topgrossingapplications/limit={n}/genre={g}/json"
LOOKUP_URL = "https://itunes.apple.com/lookup?id={ids}&country={cc}"
HEADERS = {"User-Agent": "Mozilla/5.0 (slipstream chart_scan)"}


def fetch_json(url, retries=3):
    """Get JSON from a URL, retrying a few times with a pause."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("could not fetch {}: {}".format(url, last))


def chart_ids(country, genre, depth):
    """Return a list of (rank, app_id) for one category's top grossing chart."""
    data = fetch_json(FEED_URL.format(cc=country, n=depth, g=genre))
    entries = data.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):  # a single entry comes back as a dict
        entries = [entries]
    out = []
    for i, e in enumerate(entries, start=1):
        try:
            app_id = e["id"]["attributes"]["im:id"]
        except (KeyError, TypeError):
            continue
        out.append((i, app_id))
    return out


def lookup(country, ids):
    """Look up app details for a list of ids, in batches. Returns dict id -> info."""
    found = {}
    for start in range(0, len(ids), 150):
        batch = ids[start:start + 150]
        data = fetch_json(LOOKUP_URL.format(ids=",".join(batch), cc=country))
        for r in data.get("results", []):
            if r.get("kind") == "software" or "trackId" in r:
                found[str(r.get("trackId"))] = r
        time.sleep(1)
    return found


def build_rows(country, genres, depth, lo, hi, log=print):
    rows = []
    for gid in genres:
        gname = GENRES.get(gid, str(gid))
        try:
            chart = chart_ids(country, gid, depth)
        except RuntimeError as e:
            log("  skipped {}: {}".format(gname, e))
            continue
        info = lookup(country, [a for _, a in chart])
        kept = 0
        for rank, app_id in chart:
            r = info.get(app_id)
            if not r:
                continue
            count = r.get("userRatingCount") or 0
            if count < lo or count > hi:
                continue
            rows.append({
                "genre": gname,
                "grossing_rank": rank,
                "name": r.get("trackName", ""),
                "seller": r.get("sellerName", ""),
                "ratings": count,
                "avg_rating": round(r.get("averageUserRating") or 0, 2),
                "price": r.get("formattedPrice", ""),
                "store_id": app_id,
                "bundle_id": r.get("bundleId", ""),
                "url": r.get("trackViewUrl", "").split("?")[0],
            })
            kept += 1
        log("  {}: {} of {} in the ratings band".format(gname, kept, len(chart)))
        time.sleep(1)
    return rows


def add_shares(rows, compare, log=print):
    """
    For every row, look the app up in each comparison store and add:
      ratings_<cc>  the app's rating count in that store (0 if not sold there)
      home_share    ratings in the scanned store divided by ratings in the scanned
                    store plus all the comparison stores that could be read
    Returns the list of comparison stores that were read successfully.
    """
    ids = sorted({r["store_id"] for r in rows})
    counts = {}
    for cc in compare:
        try:
            info = lookup(cc, ids)
        except RuntimeError as e:
            log("  could not read the {} store, leaving it out: {}".format(cc.upper(), e))
            continue
        counts[cc] = {i: (info.get(i, {}).get("userRatingCount") or 0) for i in ids}
        log("  read the {} store".format(cc.upper()))
    used = list(counts)
    for r in rows:
        other = 0
        for cc in used:
            n = counts[cc][r["store_id"]]
            r["ratings_" + cc] = n
            other += n
        total = r["ratings"] + other
        r["home_share"] = round(r["ratings"] / total, 2) if total else 1.0
    return used


def write_outputs(rows, country, lo, hi, depth, stem, used, min_share, top_rank):
    cols = ["genre", "grossing_rank", "name", "seller", "ratings"]
    if used:
        cols += ["home_share"] + ["ratings_" + cc for cc in used]
    cols += ["avg_rating", "price", "store_id", "bundle_id", "url"]
    with open(stem + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    cc_up = country.upper()
    lines = []
    lines.append("Chart scan, {} store, {}".format(cc_up, datetime.date.today()))
    lines.append("")
    lines.append("Top {} of each category's top grossing chart, kept only if {} ratings are {} to {}.".format(
        depth, cc_up, lo, hi))
    if used and min_share > 0:
        lines.append("Also kept only if the {} store holds at least {}% of the ratings across {}.".format(
            cc_up, int(round(min_share * 100)), ", ".join([cc_up] + [c.upper() for c in used])))
    elif used:
        lines.append("Share column: the {} store's part of the ratings across {}.".format(
            cc_up, ", ".join([cc_up] + [c.upper() for c in used])))
    lines.append("A high rank with few ratings suggests an app that earns for its size. "
                 "It is a hint, not proof.")
    lines.append("")
    lines.append("Best candidates (rank {} or better, any category)".format(top_rank))
    lines.append("")
    if used:
        lines.append("| Rank | Category | App | Ratings | {} share | Avg | Price |".format(cc_up))
        lines.append("|---|---|---|---|---|---|---|")
    else:
        lines.append("| Rank | Category | App | Ratings | Avg | Price |")
        lines.append("|---|---|---|---|---|---|")
    best = sorted([r for r in rows if r["grossing_rank"] <= top_rank],
                  key=lambda r: (r["grossing_rank"], r["ratings"]))
    for r in best:
        if used:
            lines.append("| {} | {} | {} | {} | {}% | {} | {} |".format(
                r["grossing_rank"], r["genre"], r["name"], r["ratings"],
                int(round(r["home_share"] * 100)), r["avg_rating"], r["price"]))
        else:
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                r["grossing_rank"], r["genre"], r["name"], r["ratings"],
                r["avg_rating"], r["price"]))
    lines.append("")
    lines.append("Everything kept, by category")
    for g in sorted({r["genre"] for r in rows}):
        lines.append("")
        lines.append(g)
        for r in sorted([x for x in rows if x["genre"] == g], key=lambda x: x["grossing_rank"]):
            share = "  {}% {}".format(int(round(r["home_share"] * 100)), cc_up) if used else ""
            lines.append("  {:>3}  {}  ({} ratings{}, {})".format(
                r["grossing_rank"], r["name"], r["ratings"], share, r["url"]))
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description="Scan Apple top grossing charts for small earning apps.")
    p.add_argument("--country", default="gb", help="two letter store code, default gb")
    p.add_argument("--min-ratings", type=int, default=1000)
    p.add_argument("--max-ratings", type=int, default=20000)
    p.add_argument("--depth", type=int, default=100,
                   help="chart positions to read per category (max 100, Apple's feed stops there)")
    p.add_argument("--genres", default="", help="comma separated genre ids, default all except Games")
    p.add_argument("--compare", default=DEFAULT_COMPARE,
                   help="other stores to compare ratings with, default {}. Use \"\" to skip.".format(DEFAULT_COMPARE))
    p.add_argument("--min-share", type=float, default=0.0,
                   help="keep only apps where the scanned store holds at least this share of the ratings "
                        "(0 to 1, for example 0.6). Default 0 keeps everything.")
    p.add_argument("--top-rank", type=int, default=40,
                   help="rank cut-off for the candidates table in the .md file, default 40")
    p.add_argument("--tag", default="", help="text added to the output file names so earlier scans are not overwritten")
    args = p.parse_args(argv)

    if not 0 <= args.min_share <= 1:
        print("--min-share must be between 0 and 1, for example 0.6")
        return 2
    genres = [int(g) for g in args.genres.split(",") if g.strip()] or list(GENRES)
    depth = max(1, min(args.depth, 100))
    compare = []
    for c in args.compare.split(","):
        c = c.strip().lower()
        if c and c != args.country.lower() and c not in compare:
            compare.append(c)

    print("Scanning {} categories in the {} store...".format(len(genres), args.country.upper()))
    rows = build_rows(args.country, genres, depth, args.min_ratings, args.max_ratings)
    if not rows:
        print("Nothing found. If every category was skipped, the network is probably blocked.")
        return 1

    used = []
    if compare:
        print("Comparing ratings in other stores ({} apps)...".format(len(rows)))
        used = add_shares(rows, compare)
    if args.min_share > 0:
        if not used:
            print("--min-share needs at least one comparison store to be readable. Nothing was written.")
            return 1
        before = len(rows)
        rows = [r for r in rows if r["home_share"] >= args.min_share]
        print("Kept {} of {} apps where the {} store holds at least {}% of the ratings.".format(
            len(rows), before, args.country.upper(), int(round(args.min_share * 100))))
        if not rows:
            print("Nothing left after the share filter. Try a lower --min-share.")
            return 1

    stem = "chart_scan_{}_{}".format(args.country, datetime.date.today().isoformat())
    if args.tag:
        stem += "_" + args.tag
    write_outputs(rows, args.country, args.min_ratings, args.max_ratings, depth, stem,
                  used, args.min_share, args.top_rank)
    print("Wrote {0}.csv and {0}.md with {1} apps.".format(stem, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
