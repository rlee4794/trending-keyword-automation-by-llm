#!/usr/bin/env python3
"""Compare keyword trends across 7-14 days of daily_trending.json.

Reads all available daily_trending.json files from runs/YYYY-MM-DD/,
builds a per-keyword timeline with day-over-day changes, and outputs
a structured summary for the Agent to produce natural-language analysis.

Usage:
  python3 scripts/trend_comparison.py --days 14
  python3 scripts/trend_comparison.py --days 7 --output /tmp/trend_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HKT = timezone(timedelta(hours=8))


def _load_daily(date_str: str) -> dict | None:
    """Load a daily_trending.json file. Returns None if missing or malformed."""
    path = Path(f"runs/{date_str}/daily_trending.json")
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _keyword_key(kw: dict) -> str:
    """Unique key for a keyword: term + type."""
    return f"{kw.get('term', '')}|{kw.get('type', '')}"


def run(days: int, output_path: str | None = None) -> dict:
    """Build a keyword timeline from the last N days of daily_trending.json.

    Returns a dict with:
      - period: {start, end, days_available, days_expected}
      - keywords_timeline: list of per-keyword daily stats
      - summary: high-level stats (total keywords, new/active/declining counts)
    """
    today = datetime.now(HKT).date()

    # Collect all available days
    daily_data: dict[str, dict] = {}
    for i in range(days):
        d = today - timedelta(days=i + 1)  # yesterday backwards
        ds = d.isoformat()
        data = _load_daily(ds)
        if data:
            daily_data[ds] = data

    available_dates = sorted(daily_data.keys())
    if not available_dates:
        print("ERROR: No daily_trending.json files found in the last {days} days", file=sys.stderr)
        sys.exit(1)

    # Build keyword timeline: {key: {date: stats}}
    timeline: dict[str, dict[str, dict]] = defaultdict(dict)
    keyword_meta: dict[str, dict] = {}  # type, platforms, sources

    for ds in available_dates:
        data = daily_data[ds]
        for kw in data.get("keywords", []):
            key = _keyword_key(kw)
            timeline[key][ds] = {
                "post_count": kw.get("post_count", 0),
                "total_likes": kw.get("total_likes", 0),
                "total_shares": kw.get("total_shares", 0),
                "total_comments": kw.get("total_comments", 0),
            }
            if key not in keyword_meta:
                keyword_meta[key] = {
                    "term": kw.get("term", ""),
                    "type": kw.get("type", ""),
                }

    # Classify each keyword: new, surging, stable, declining, dormant
    keywords_timeline = []
    for key, daily in timeline.items():
        meta = keyword_meta[key]
        sorted_dates = sorted(daily.keys())
        first_date = sorted_dates[0]
        last_date = sorted_dates[-1]
        days_active = len(sorted_dates)

        # Compute first-half vs second-half engagement for trend direction
        mid = len(sorted_dates) // 2
        first_half_dates = sorted_dates[:max(1, mid)]
        second_half_dates = sorted_dates[mid:]

        first_half_likes = sum(daily[d]["total_likes"] for d in first_half_dates)
        second_half_likes = sum(daily[d]["total_likes"] for d in second_half_dates)
        first_half_posts = sum(daily[d]["post_count"] for d in first_half_dates)
        second_half_posts = sum(daily[d]["post_count"] for d in second_half_dates)

        # Classify
        if days_active == 1:
            classification = "new"
        elif first_half_likes == 0 and second_half_likes > 0:
            classification = "new"
        elif second_half_posts >= first_half_posts * 1.5:
            classification = "surging"
        elif second_half_posts <= first_half_posts * 0.5:
            classification = "declining"
        else:
            classification = "stable"

        keywords_timeline.append({
            "term": meta["term"],
            "type": meta["type"],
            "first_seen": first_date,
            "last_seen": last_date,
            "days_active": days_active,
            "classification": classification,
            "daily": {d: daily[d] for d in sorted_dates},
            "total_likes_period": sum(d["total_likes"] for d in daily.values()),
            "total_posts_period": sum(d["post_count"] for d in daily.values()),
        })

    # Sort: new/surging first, then by total engagement
    classification_order = {"new": 0, "surging": 1, "stable": 2, "declining": 3}
    keywords_timeline.sort(
        key=lambda k: (
            classification_order.get(k["classification"], 9),
            -k["total_likes_period"],
        )
    )

    # High-level summary
    counts = defaultdict(int)
    for kt in keywords_timeline:
        counts[kt["classification"]] += 1

    result = {
        "schema_version": "1.0",
        "generated_at": datetime.now(HKT).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "period": {
            "start": available_dates[0],
            "end": available_dates[-1],
            "days_available": len(available_dates),
            "days_requested": days,
        },
        "summary": {
            "total_keywords": len(keywords_timeline),
            "new": counts.get("new", 0),
            "surging": counts.get("surging", 0),
            "stable": counts.get("stable", 0),
            "declining": counts.get("declining", 0),
        },
        "keywords_timeline": keywords_timeline,
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        # Ensure trailing newline
        content = out.read_text(encoding="utf-8")
        if content and not content.endswith("\n"):
            out.write_text(content + "\n", encoding="utf-8")
        print(f"Trend summary → {out}", file=sys.stderr)
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare keyword trends across N days of daily_trending.json"
    )
    parser.add_argument(
        "--days", type=int, default=14,
        help="Number of days to look back (default: 14)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file path (default: stdout)",
    )
    args = parser.parse_args()
    run(args.days, args.output)


if __name__ == "__main__":
    main()
