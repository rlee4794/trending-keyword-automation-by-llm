#!/usr/bin/env python3
"""Format daily_trending_{REGION}.json for LLM luxury extraction.

Usage:
  python3 scripts/luxury_extract.py --date 2026-07-12 --region hk [--output /tmp/luxury_prompt.txt]

Output is a plain text file with keywords + posts summaries,
ready to feed into an LLM for luxury signal extraction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_daily(date_str: str, region: str) -> dict:
    path = Path(f"runs/{date_str}/daily_trending_{region.upper()}.json")
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Format daily_trending for LLM luxury extraction"
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--region", default="hk")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    daily = _load_daily(args.date, args.region)
    keywords = daily.get("keywords", [])
    posts = daily.get("posts", [])

    lines = []
    lines.append(f"# Luxury Extraction Input — {args.date} ({args.region.upper()})")
    lines.append(f"Keywords: {len(keywords)}, Posts: {len(posts)}")
    lines.append("")

    # Keywords section
    lines.append("## Keywords")
    lines.append("")
    for kw in keywords:
        lines.append(
            f"- {kw['term']} | type={kw['type']} | "
            f"posts={kw['post_count']} | likes={kw['total_likes']} | "
            f"sources={', '.join(kw.get('sources', [])[:3])}"
        )

    lines.append("")
    lines.append("## Posts (with extracted dishes/venues)")
    lines.append("")
    for i, p in enumerate(posts):
        ext = p.get("extracted", {})
        dishes = ext.get("dishes", [])
        venues = ext.get("venues", [])
        snippet = (p.get("caption_snippet", "") or "")[:200]

        lines.append(f"[{i}] {p.get('likes', 0)}❤️ | {p.get('platform', '?')} | {p.get('source', '?')}")
        if dishes:
            lines.append(f"  dishes: {', '.join(dishes)}")
        if venues:
            lines.append(f"  venues: {', '.join(venues)}")
        lines.append(f"  caption: {snippet}")
        lines.append("")

    output = "\n".join(lines)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"→ {args.output} ({len(output)} chars)", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
