#!/usr/bin/env python3
"""Slipstream review check.

Pulls the latest public App Store reviews for one or more apps from Apple's
free review feed (no key, no login), keeps the low-star ones, and counts what
people complain about. This replaces reading reviews by hand in step 2.

An app can be given as its App Store id (the number in the store link, after
"id") or as a name. A name is looked up with Apple's search and the app it
picked is printed, so check it is the right one. An id is looked up with
Apple's lookup API so the report shows the app's name and seller; if that
lookup fails, the report shows the id instead.

Usage:
  python review_check.py 1530677254
  python review_check.py "MacroFactor" "LADDER Strength Training Plans"
  python review_check.py -f apps.txt --country gb,us --pages 10
  python review_check.py 1530677254 --tag golf      # saves review_check_golf.md
  python review_check.py 1530677254 --since 2025-10-01
  python review_check.py 1530677254 --csv --full
(on a Mac, use python3)

Options beyond the basics:
  --tag TEXT     add TEXT to the file names, so earlier runs are not overwritten
  --since DATE   ignore reviews older than DATE (YYYY-MM-DD)
  --csv          also save every review read (stars, date, version, title,
                 text, themes matched) to a csv beside the md
  --full         print whole reviews in the md instead of the first ~400 characters

Saves review_check.json and review_check.md next to where you run it, or
review_check_<tag>.json and .md with --tag.

In the md, each example review is printed once, under the first theme it
matches (themes in the order of the table), with any other themes it matched
in brackets. The theme counts still count a review under every theme it
matches.

Limits: Apple's feed only returns the most recent reviews for each country
(about 500 at most), so this is a sample of recent reviews, not all of them.
Counts are keyword matches, so read the example quotes before trusting a theme.
"""
import argparse
import csv
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

UA = "slipstream-review-check/1.0"
DELAY = 1.0

# Each theme is a list of regular expressions run against the lower-cased
# title plus review text. A review can match several themes.
THEMES = {
    "price, trial or paywall": [
        r"subscri", r"paywall", r"\btrial", r"expensive", r"\bprice", r"pricing",
        r"refund", r"per month", r"a month", r"not free", r"\blite\b",
        r"charged", r"\bmoney\b", r"too much to pay", r"free version",
    ],
    "support": [
        r"support", r"customer (service|care)", r"no (reply|response)",
        r"never (replied|responded|answered)", r"ai bot", r"chat ?bot", r"\brobot",
    ],
    "bugs or crashes": [
        r"crash", r"freez", r"glitch", r"\bbugs?\b", r"buggy", r"won'?t (open|load|work)",
        r"not working", r"doesn'?t work", r"stopped working", r"error",
        r"slow", r"loading",
    ],
    "out of date or abandoned": [
        r"not (been )?updated", r"no (more )?updates", r"never updated", r"abandon",
        r"out ?of ?date", r"outdated", r"no longer (works?|working|supported|maintained)",
        r"(since|after) (the )?(latest |last |new |recent )?ios", r"\bios ?\d{2}\b",
        r"old (rules|questions|version|data|info)", r"dead app", r"developer (has )?(gone|vanished|disappeared)",
    ],
    "ads": [r"\bads?\b", r"\badds\b", r"advert"],
    "sync or integrations": [
        r"\bsync", r"apple health", r"apple watch", r"garmin", r"strava",
        r"fitbit", r"google fit", r"widget",
    ],
    "offline": [
        r"offline", r"no (wifi|wi-fi|signal|internet|connection)",
        r"without (wifi|wi-fi|internet|signal)",
    ],
    "accessibility": [
        r"light mode", r"dark mode", r"font", r"too small", r"can'?t read",
        r"subtitle", r"accessib", r"contrast", r"colou?r ?blind", r"text size",
        r"vision",
    ],
    "feature request": [
        r"\bwish\b", r"please add", r"should (have|add|be able)",
        r"would (love|be nice|be great|be good)", r"\bneeds? (a|an|to have|more)\b",
        r"no way to", r"can'?t (change|select|set|turn off|switch|edit|export|add)",
        r"no option", r"option to", r"\bmissing\b", r"\bnot able to\b", r"lacks?\b",
    ],
    "sign-up or onboarding": [
        r"sign ?up", r"sign ?in", r"log ?in", r"\baccount", r"onboarding",
        r"too many questions", r"registration",
    ],
    "rating prompts": [
        r"ask(s|ing)? (me |us )?(to|for) (rate|a rating|a review|reviews|ratings)",
        r"rate (the app )?(every|each|after)", r"stop asking",
    ],
    "accuracy or content": [
        r"inaccurate", r"incorrect", r"not accurate", r"wrong (info|data|calorie)",
        r"missing (food|item|product)", r"database",
    ],
}
THEME_RES = {k: [re.compile(p) for p in v] for k, v in THEMES.items()}


def get_json(url):
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.load(resp)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as err:
            last = err
            time.sleep(2)
    raise RuntimeError("could not fetch %s (%s)" % (url, last))


def lookup_name(name, country):
    query = urllib.parse.urlencode(
        {"term": name, "entity": "software", "country": country, "limit": 1}
    )
    data = get_json("https://itunes.apple.com/search?" + query)
    results = data.get("results") or []
    if not results:
        return None, None, ""
    r = results[0]
    return str(r.get("trackId")), r.get("trackName"), r.get("sellerName") or r.get("artistName") or ""


def lookup_id(app_id, country):
    """Return (name, seller) for a store id, or (None, "") if Apple has no match."""
    query = urllib.parse.urlencode({"id": app_id, "country": country})
    data = get_json("https://itunes.apple.com/lookup?" + query)
    results = data.get("results") or []
    if not results:
        return None, ""
    r = results[0]
    return r.get("trackName"), r.get("sellerName") or r.get("artistName") or ""


def label(entry, *path):
    cur = entry
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return ""
        cur = cur[key]
    return cur.get("label", "") if isinstance(cur, dict) else str(cur)


def parse_page(data):
    """Return review dicts from one feed page. The first entry on page 1 is
    the app itself and has no rating, so it is skipped."""
    feed = data.get("feed", {})
    entries = feed.get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for e in entries:
        rating = label(e, "im:rating")
        if not rating.isdigit():
            continue
        out.append(
            {
                "stars": int(rating),
                "title": label(e, "title"),
                "text": label(e, "content"),
                "version": label(e, "im:version"),
                "date": label(e, "updated")[:10],
                "author": label(e, "author", "name"),
            }
        )
    return out


def fetch_reviews(app_id, country, pages, since=""):
    """The feed is newest first, so paging stops once a whole page is older
    than `since`."""
    reviews = []
    for page in range(1, pages + 1):
        url = (
            "https://itunes.apple.com/%s/rss/customerreviews/page=%d/id=%s/"
            "sortby=mostrecent/json" % (country, page, app_id)
        )
        try:
            batch = parse_page(get_json(url))
        except RuntimeError as err:
            print("  page %d: %s" % (page, err), file=sys.stderr)
            break
        if not batch:
            break
        for r in batch:
            r["country"] = country
        reviews.extend(batch)
        if since and all(r["date"] and r["date"] < since for r in batch):
            break
        time.sleep(DELAY)
    return reviews


def themes_for(review):
    text = (review["title"] + " " + review["text"]).lower()
    return [
        name
        for name, patterns in THEME_RES.items()
        if any(p.search(text) for p in patterns)
    ]


QUOTE_LEN = 400


def shorten(text, n=QUOTE_LEN):
    """Collapse whitespace and cut to about n characters at a word boundary.
    n=None keeps the whole text."""
    text = " ".join(text.split())
    if n is None or len(text) <= n:
        return text
    cut = text[:n]
    space = cut.rfind(" ")
    if space > n // 2:
        cut = cut[:space]
    return cut.rstrip(" ,.;:-") + "..."


def analyse(reviews, max_star, quote_len=QUOTE_LEN):
    stars = Counter(r["stars"] for r in reviews)
    low = [r for r in reviews if r["stars"] <= max_star]
    themed = {}
    for r in low:
        for t in themes_for(r):
            themed.setdefault(t, []).append(r)
    ranked = sorted(themed.items(), key=lambda kv: -len(kv[1]))
    order = [name for name, _ in ranked]
    dates = sorted(r["date"] for r in reviews if r["date"])

    def examples(name, rs):
        """Up to 3 reviews whose first theme, in table order, is this one."""
        out = []
        for r in rs:
            matched = [t for t in order if t in themes_for(r)]
            if matched[0] != name:
                continue
            out.append(
                {
                    "stars": r["stars"],
                    "country": r["country"],
                    "date": r["date"],
                    "version": r["version"],
                    "quote": shorten(r["title"] + ": " + r["text"], quote_len),
                    "also": matched[1:],
                }
            )
            if len(out) == 3:
                break
        return out

    return {
        "reviews_fetched": len(reviews),
        "date_range": [dates[0], dates[-1]] if dates else [],
        "stars": {str(k): stars.get(k, 0) for k in range(1, 6)},
        "low_star_count": len(low),
        "low_star_share_pct": round(100 * len(low) / len(reviews), 1) if reviews else 0,
        "unmatched_low": sum(1 for r in low if not themes_for(r)),
        "themes": [
            {
                "theme": name,
                "count": len(rs),
                "share_of_low_pct": round(100 * len(rs) / len(low)) if low else 0,
                "examples": examples(name, rs),
            }
            for name, rs in ranked
        ],
    }


def to_markdown(apps, since=""):
    lines = ["# Review check", ""]
    if since:
        lines += ["Only reviews dated %s or later." % since, ""]
    for a in apps:
        if a.get("seller"):
            lines.append("## %s, by %s (id %s)" % (a["name"], a["seller"], a["id"]))
        else:
            lines.append("## %s (id %s)" % (a["name"], a["id"]))
        s = a["summary"]
        if not s["reviews_fetched"]:
            if since:
                lines += ["No reviews dated %s or later came back. Check the id, "
                          "country and date." % since, ""]
            else:
                lines += ["No reviews came back. Check the id and country.", ""]
            continue
        lines.append(
            "%d recent reviews, %s to %s. Stars 1 to 5: %s. Low-star: %d (%s%%)."
            % (
                s["reviews_fetched"], s["date_range"][0], s["date_range"][1],
                ", ".join(str(s["stars"][str(i)]) for i in range(1, 6)),
                s["low_star_count"], s["low_star_share_pct"],
            )
        )
        lines.append("")
        lines.append("| Theme | Low-star reviews | Share of low-star |")
        lines.append("|---|---|---|")
        for t in s["themes"]:
            lines.append("| %s | %d | %d%% |" % (t["theme"], t["count"], t["share_of_low_pct"]))
        if s["unmatched_low"]:
            lines.append("")
            lines.append("%d low-star reviews matched no theme." % s["unmatched_low"])
        lines.append("")
        for t in s["themes"][:4]:
            lines.append("%s:" % t["theme"])
            if not t["examples"]:
                lines.append("- every review in this theme is shown under an earlier theme")
            for ex in t["examples"]:
                also = " [also: %s]" % ", ".join(ex["also"]) if ex["also"] else ""
                lines.append(
                    "- %d stars, %s, %s, v%s%s: %s"
                    % (ex["stars"], ex["country"], ex["date"], ex["version"], also, ex["quote"])
                )
            lines.append("")
    return "\n".join(lines)


def write_csv(path, apps, reviews_by_app):
    cols = ["app_id", "app_name", "country", "stars", "date", "version",
            "title", "text", "themes"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for a in apps:
            for r in reviews_by_app[a["id"]]:
                w.writerow([a["id"], a["name"], r["country"], r["stars"], r["date"],
                            r["version"], r["title"], r["text"], "; ".join(themes_for(r))])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Count complaints in recent App Store reviews.")
    ap.add_argument("apps", nargs="*", help="App Store ids or app names")
    ap.add_argument("-f", "--file", help="text file with one id or name per line")
    ap.add_argument("--country", default="gb", help="comma separated, default gb")
    ap.add_argument("--pages", type=int, default=10, help="feed pages per country, max 10")
    ap.add_argument("--max-star", type=int, default=2, help="keep reviews at or below this")
    ap.add_argument("--tag", default="", help="text added to the output file names")
    ap.add_argument("--since", default="", help="ignore reviews older than this date, YYYY-MM-DD")
    ap.add_argument("--csv", action="store_true", help="also save every review read to a csv")
    ap.add_argument("--full", action="store_true", help="print whole reviews instead of ~400 characters")
    args = ap.parse_args(argv)

    if args.since:
        try:
            datetime.date.fromisoformat(args.since)
        except ValueError:
            ap.error("--since must be a date like 2025-10-01")

    wanted = list(args.apps)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            wanted += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    if not wanted:
        ap.error("give at least one app id or name")

    countries = [c.strip().lower() for c in args.country.split(",") if c.strip()]
    pages = max(1, min(args.pages, 10))
    quote_len = None if args.full else QUOTE_LEN
    apps = []
    reviews_by_app = {}
    for w in wanted:
        if w.isdigit():
            app_id, name, seller = w, None, ""
            try:
                name, seller = lookup_id(w, countries[0])
            except RuntimeError as err:
                print("%s: name lookup failed, using the id (%s)" % (w, err), file=sys.stderr)
            if not name:
                name = "app " + w
            time.sleep(DELAY)
        else:
            try:
                app_id, name, seller = lookup_name(w, countries[0])
            except RuntimeError as err:
                print("%s: %s" % (w, err), file=sys.stderr)
                continue
            if not app_id:
                print("%s: no app found" % w, file=sys.stderr)
                continue
            print("%r -> %s (id %s)" % (w, name, app_id), file=sys.stderr)
            time.sleep(DELAY)
        reviews = []
        for c in countries:
            print("fetching %s, %s" % (name, c), file=sys.stderr)
            reviews += fetch_reviews(app_id, c, pages, args.since)
        if args.since:
            reviews = [r for r in reviews if not r["date"] or r["date"] >= args.since]
        reviews_by_app[app_id] = reviews
        apps.append(
            {"id": app_id, "name": name, "seller": seller, "countries": countries,
             "summary": analyse(reviews, args.max_star, quote_len)}
        )

    stem = "review_check" + ("_" + args.tag if args.tag else "")
    with open(stem + ".json", "w", encoding="utf-8") as fh:
        json.dump(apps, fh, indent=2)
    md = to_markdown(apps, args.since)
    with open(stem + ".md", "w", encoding="utf-8") as fh:
        fh.write(md)
    saved = [stem + ".json", stem + ".md"]
    if args.csv:
        write_csv(stem + ".csv", apps, reviews_by_app)
        saved.append(stem + ".csv")
    print(md)
    print("Saved " + ", ".join(saved), file=sys.stderr)


if __name__ == "__main__":
    main()
