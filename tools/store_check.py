#!/usr/bin/env python3
"""Slipstream store check.

Looks up the top 10 App Store results for each keyword using Apple's free
public search (no key needed) and prints them as JSON. Paste the output
into step 5 of Slipstream Finder.

Usage:
  python store_check.py "brown noise"
  python store_check.py -f keywords.txt --country us
(on a Mac, use python3)
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def fetch(term, country):
    query = urllib.parse.urlencode(
        {"term": term, "entity": "software", "country": country, "limit": 10}
    )
    req = urllib.request.Request(
        "https://itunes.apple.com/search?" + query,
        headers={"User-Agent": "slipstream-store-check/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def days_since(iso):
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - then).days
    except (ValueError, AttributeError):
        return None


def summarise(term, country, data):
    rows = []
    for i, app in enumerate(data.get("results", [])[:10]):
        updated = app.get("currentVersionReleaseDate", "")
        rows.append(
            {
                "rank": i + 1,
                "name": app.get("trackName", ""),
                "dev": app.get("artistName", ""),
                "ratings": app.get("userRatingCount", 0),
                "updated": updated[:10],
                "days": days_since(updated),
            }
        )
    return {
        "keyword": term,
        "country": country,
        "checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "results": rows,
    }


def main():
    ap = argparse.ArgumentParser(description="Top 10 App Store results per keyword")
    ap.add_argument("keywords", nargs="*", help="keywords to check")
    ap.add_argument("-f", "--file", help="text file with one keyword per line")
    ap.add_argument("--country", default="gb", help="two-letter store country, default gb")
    args = ap.parse_args()

    terms = list(args.keywords)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            terms += [line.strip() for line in fh if line.strip()]
    if not terms:
        ap.error("give at least one keyword, or a file with -f")

    out = []
    for n, term in enumerate(terms):
        if n:
            time.sleep(3)  # stay well under Apple's rate limit
        try:
            out.append(summarise(term, args.country, fetch(term, args.country)))
        except urllib.error.HTTPError as err:
            print(f"{term}: Apple returned {err.code}. Wait a minute and try again.", file=sys.stderr)
        except Exception as err:  # network down, bad response, and so on
            print(f"{term}: could not check ({err}).", file=sys.stderr)
        else:
            rows = out[-1]["results"]
            print(f"{term}: {len(rows)} results", file=sys.stderr)

    text = json.dumps(out, ensure_ascii=False)
    with open("store_check.json", "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print("\nAlso saved as store_check.json", file=sys.stderr)


if __name__ == "__main__":
    main()
