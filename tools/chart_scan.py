#!/usr/bin/env python3
"""
chart_scan.py

Scans Apple's public top grossing charts across many App Store categories and
lists apps that earn well but have a modest number of ratings. These are the
small, earning apps the Slipstream method starts from.

What it uses: only Apple's free public feeds (the top grossing RSS feed and the
iTunes lookup API). No login, no keys, no extra packages. Python 3.8 or newer.

What it cannot tell you: downloads or revenue. A high top grossing rank with few
ratings is a hint that an app earns, not proof. Check any app you like in
Appfigures while the trial lasts, then run review_check.py on it.

Usage:
    python3 chart_scan.py                      # UK, all categories except Games
    python3 chart_scan.py --country us
    python3 chart_scan.py --min-ratings 500 --max-ratings 30000
    python3 chart_scan.py --genres 6013,6017   # only some categories
    python3 chart_scan.py --depth 100          # how far down each chart to look

Output: chart_scan_<country>_<date>.csv and .md in the current folder.
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


def write_outputs(rows, country, lo, hi, depth, stem):
    cols = ["genre", "grossing_rank", "name", "seller", "ratings", "avg_rating",
            "price", "store_id", "bundle_id", "url"]
    with open(stem + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    lines = []
    lines.append("Chart scan, {} store, {}".format(country.upper(), datetime.date.today()))
    lines.append("")
    lines.append("Top {} of each category's top grossing chart, kept only if ratings are {} to {}.".format(
        depth, lo, hi))
    lines.append("A high rank with few ratings suggests an app that earns for its size. "
                 "It is a hint, not proof.")
    lines.append("")
    lines.append("Best candidates (rank 40 or better, any category)")
    lines.append("")
    lines.append("| Rank | Category | App | Ratings | Avg | Price |")
    lines.append("|---|---|---|---|---|---|")
    best = sorted([r for r in rows if r["grossing_rank"] <= 40],
                  key=lambda r: (r["grossing_rank"], r["ratings"]))
    for r in best:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            r["grossing_rank"], r["genre"], r["name"], r["ratings"],
            r["avg_rating"], r["price"]))
    lines.append("")
    lines.append("Everything in the band, by category")
    for g in sorted({r["genre"] for r in rows}):
        lines.append("")
        lines.append(g)
        for r in sorted([x for x in rows if x["genre"] == g], key=lambda x: x["grossing_rank"]):
            lines.append("  {:>3}  {}  ({} ratings, {})".format(
                r["grossing_rank"], r["name"], r["ratings"], r["url"]))
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description="Scan Apple top grossing charts for small earning apps.")
    p.add_argument("--country", default="gb", help="two letter store code, default gb")
    p.add_argument("--min-ratings", type=int, default=1000)
    p.add_argument("--max-ratings", type=int, default=20000)
    p.add_argument("--depth", type=int, default=100, help="chart positions to read per category (max 200)")
    p.add_argument("--genres", default="", help="comma separated genre ids, default all except Games")
    args = p.parse_args(argv)

    genres = [int(g) for g in args.genres.split(",") if g.strip()] or list(GENRES)
    depth = max(1, min(args.depth, 200))
    print("Scanning {} categories in the {} store...".format(len(genres), args.country.upper()))
    rows = build_rows(args.country, genres, depth, args.min_ratings, args.max_ratings)
    if not rows:
        print("Nothing found. If every category was skipped, the network is probably blocked.")
        return 1
    stem = "chart_scan_{}_{}".format(args.country, datetime.date.today().isoformat())
    write_outputs(rows, args.country, args.min_ratings, args.max_ratings, depth, stem)
    print("Wrote {0}.csv and {0}.md with {1} apps.".format(stem, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
