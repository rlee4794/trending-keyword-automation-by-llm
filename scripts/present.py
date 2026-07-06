#!/usr/bin/env python3
"""Step 6 helper — read weekly_fnb_trending.json, export CSVs.

Usage:
  python3 scripts/present.py read <run_dir>   — print KW| lines for agent consumption
  python3 scripts/present.py export <run_dir>  — write CSV files
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def read_json(run_dir: str) -> dict:
    path = Path(run_dir) / "weekly_fnb_trending.json"
    with path.open() as f:
        return json.load(f)


def cmd_read(run_dir: str) -> None:
    """Print KW| lines for agent to format into presentation."""
    data = read_json(run_dir)
    keywords = data.get("keywords", [])
    period = data.get("period", {})
    cw = period.get("current_week", {})

    print(f"TOTAL_KEYWORDS={len(keywords)}")
    print(f"SCHEMA_VERSION={data.get('schema_version')}")
    print(f"GENERATED_AT={data.get('generated_at')}")
    print(f"PERIOD_CW_START={cw.get('start')}")
    print(f"PERIOD_CW_END={cw.get('end')}")
    print(f"PERIOD_CW_DAYS={cw.get('days_with_data')}")
    print(f"PERIOD_PW_DAYS={period.get('previous_week', {}).get('days_with_data')}")
    print(f"MODE={data.get('pipeline', {}).get('mode')}")

    for kw in keywords:
        ig = kw.get("platforms", {}).get("instagram", {})
        goog = kw.get("platforms", {}).get("google", {})
        print(
            f"KW|{kw.get('rank')}|{kw.get('display_term')}|"
            f"{kw.get('social_composite_score')}|{kw.get('trend_direction')}|"
            f"{ig.get('engagement_raw')}|{goog.get('volume')}|"
            f"{kw.get('category', '')}|{kw.get('potential', '')}"
        )


def cmd_export(run_dir: str) -> None:
    """Write weekly_fnb_trending.csv and weekly_fnb_trending_high_potential.csv."""
    data = read_json(run_dir)
    keywords = data.get("keywords", [])

    fieldnames = [
        "rank", "canonical_key", "display_term", "raw_representative",
        "category", "potential", "social_composite_score", "trend_direction",
        "platform_hits", "ig_score", "ig_engagement_raw", "ig_post_count",
        "ig_previous_score", "goog_score", "goog_volume", "goog_previous_score",
    ]

    def build_row(kw):
        ig = kw.get("platforms", {}).get("instagram", {})
        goog = kw.get("platforms", {}).get("google", {})
        return {
            "rank": kw.get("rank"),
            "canonical_key": kw.get("canonical_key"),
            "display_term": kw.get("display_term"),
            "raw_representative": kw.get("raw_representative"),
            "category": kw.get("category"),
            "potential": kw.get("potential"),
            "social_composite_score": kw.get("social_composite_score"),
            "trend_direction": kw.get("trend_direction"),
            "platform_hits": kw.get("platform_hits"),
            "ig_score": ig.get("platform_score"),
            "ig_engagement_raw": ig.get("engagement_raw"),
            "ig_post_count": ig.get("post_count"),
            "ig_previous_score": ig.get("previous_score"),
            "goog_score": goog.get("platform_score"),
            "goog_volume": goog.get("volume"),
            "goog_previous_score": goog.get("previous_score"),
        }

    # All keywords
    out_all = Path(run_dir) / "weekly_fnb_trending.csv"
    with out_all.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for kw in keywords:
            w.writerow(build_row(kw))

    # High-potential only
    high = [kw for kw in keywords if kw.get("potential") == "high"]
    out_high = Path(run_dir) / "weekly_fnb_trending_high_potential.csv"
    with out_high.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for kw in high:
            w.writerow(build_row(kw))

    print(f"CSV all: {len(keywords)} rows", file=sys.stderr)
    print(f"CSV high-potential: {len(high)} rows", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 6: Present helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("read")
    p.add_argument("run_dir")

    p = sub.add_parser("export")
    p.add_argument("run_dir")

    args = parser.parse_args()

    if args.cmd == "read":
        cmd_read(args.run_dir)
    elif args.cmd == "export":
        cmd_export(args.run_dir)


if __name__ == "__main__":
    main()
