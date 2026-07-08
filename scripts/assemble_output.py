#!/usr/bin/env python3
"""Assemble filtered posts + Agent extraction → daily_trending.json.

Reads:
  runs/{date}/filtered/threshold_filtered.json
  Agent extraction JSON (via --extraction-file or --extraction-json)

Writes:
  runs/{date}/daily_trending.json
  runs/latest → symlink to {date}

Includes post-processing guards to catch common LLM extraction errors:
  - Single-character venue/dish names
  - Common Chinese function words misidentified as venues/dishes

Usage:
  python3 scripts/assemble_output.py --date 2026-07-07 --extraction-file /tmp/ext.json
  python3 scripts/assemble_output.py --date 2026-07-07 --extraction-json '{"posts": [...], "keywords": [...]}'
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HKT = timezone(timedelta(hours=8))

# Common Chinese characters that are NEVER venue or dish names.
# These are function words, adverbs, conjunctions, pronouns, and
# generic verbs that can appear in any sentence.
COMMON_CHARS: set[str] = {
    "不", "的", "了", "是", "在", "有", "和", "都", "就", "也",
    "會", "要", "可", "好", "食", "飲", "去", "來", "我", "你",
    "他", "她", "很", "個", "種", "啲", "嘅", "咁", "仲", "未",
    "冇", "無", "係", "喺", "俾", "畀", "令", "將", "但", "只",
    "已", "更", "最", "又", "或", "與", "及",
}


def _guard_extraction(posts: list[dict]) -> tuple[int, int]:
    """Strip obviously invalid extractions from posts. Returns (venue_dropped, dish_dropped)."""
    venue_dropped = 0
    dish_dropped = 0

    for p in posts:
        ext = p.get("extracted")
        if not ext:
            continue

        venues = ext.get("venues", [])
        if venues:
            filtered = [
                v for v in venues
                if len(v) >= 2 and v not in COMMON_CHARS
            ]
            dropped = len(venues) - len(filtered)
            if dropped:
                venue_dropped += dropped
                for v in venues:
                    if v not in filtered:
                        print(
                            f"⚠️  GUARD: dropped venue='{v}' from post "
                            f"(caption: {p.get('caption_snippet', '')[:80]}...)",
                            file=sys.stderr,
                        )
            ext["venues"] = filtered

        dishes = ext.get("dishes", [])
        if dishes:
            filtered = [
                d for d in dishes
                if len(d) >= 2 and d not in COMMON_CHARS
            ]
            dropped = len(dishes) - len(filtered)
            if dropped:
                dish_dropped += dropped
                for d in dishes:
                    if d not in filtered:
                        print(
                            f"⚠️  GUARD: dropped dish='{d}' from post "
                            f"(caption: {p.get('caption_snippet', '')[:80]}...)",
                            file=sys.stderr,
                        )
            ext["dishes"] = filtered

    return venue_dropped, dish_dropped


def _guard_keywords(keywords: list[dict]) -> tuple[list[dict], int]:
    """Remove keywords with obviously invalid terms.
    Returns (filtered_keywords, count_dropped).
    """
    dropped = 0
    valid = []
    for kw in keywords:
        term = kw.get("term", "")
        if len(term) <= 1:
            print(
                f"⚠️  GUARD: dropping single-char keyword '{term}' (type={kw.get('type')})",
                file=sys.stderr,
            )
            dropped += 1
            continue
        if term in COMMON_CHARS:
            print(
                f"⚠️  GUARD: dropping common-char keyword '{term}' (type={kw.get('type')})",
                file=sys.stderr,
            )
            dropped += 1
            continue
        valid.append(kw)
    return valid, dropped


def run(date_str: str, extraction: dict) -> None:
    """Assemble final output with guardrails."""
    run_dir = Path(f"runs/{date_str}")
    filtered_path = run_dir / "filtered" / "threshold_filtered.json"

    if not filtered_path.exists():
        print(f"ERROR: {filtered_path} not found", file=sys.stderr)
        sys.exit(1)

    with filtered_path.open(encoding="utf-8") as f:
        filtered = json.load(f)

    posts = filtered["posts"]

    # ── Step 1: Merge extraction into posts ─────────────────────────
    for pe in extraction.get("posts", []):
        idx = pe["index"]
        if idx < len(posts):
            posts[idx]["extracted"] = {
                "dishes": pe.get("dishes", []),
                "venues": pe.get("venues", []),
                "cuisines": pe.get("cuisines", []),
            }

    # ── Step 2: Post-processing guards ──────────────────────────────
    venue_dropped, dish_dropped = _guard_extraction(posts)
    if venue_dropped or dish_dropped:
        print(
            f"🛡️  GUARD: stripped {venue_dropped} invalid venue(s), "
            f"{dish_dropped} invalid dish(es) from posts",
            file=sys.stderr,
        )

    # ── Step 3: Build keyword aggregates ────────────────────────────
    keywords = extraction.get("keywords", [])
    for kw in keywords:
        indices = kw.pop("post_indices", [])
        kw["post_count"] = len(indices)
        if indices:
            total_likes = sum(
                posts[i]["likes"] for i in indices if i < len(posts)
            )
            total_comments = sum(
                posts[i]["comments"] for i in indices if i < len(posts)
            )
            total_shares = sum(
                posts[i]["shares"] for i in indices if i < len(posts)
            )
            platforms = list(set(
                posts[i]["platform"] for i in indices if i < len(posts)
            ))
            sources = list(set(
                posts[i]["source"] for i in indices if i < len(posts)
            ))
        else:
            # Google-only keyword (no social posts)
            total_likes = 0
            total_comments = 0
            total_shares = 0
            platforms = ["google"]
            sources = ["google"]
        kw["total_likes"] = total_likes
        kw["total_comments"] = total_comments
        kw["total_shares"] = total_shares
        kw["platforms"] = platforms
        kw["sources"] = sources

    # ── Step 4: Guard keywords ──────────────────────────────────────
    keywords, kw_dropped = _guard_keywords(keywords)
    if kw_dropped:
        print(
            f"🛡️  GUARD: dropped {kw_dropped} invalid keyword(s)",
            file=sys.stderr,
        )

    # ── Step 5: Assemble output ─────────────────────────────────────
    google_terms = filtered.get("google_trends", [])

    output = {
        "schema_version": "1.0",
        "date": filtered["date"],
        "generated_at": datetime.now(HKT).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "threshold": filtered["threshold"],
        "posts": posts,
        "google_trends": google_terms,
        "keywords": keywords,
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "daily_trending.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    # Ensure trailing newline
    content = out_path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        out_path.write_text(content + "\n", encoding="utf-8")

    # Update symlink
    latest_link = Path("runs/latest")
    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(date_str)

    print(
        f"✅ {len(keywords)} keywords from {len(posts)} posts "
        f"+ {len(google_terms)} Google terms",
        file=sys.stderr,
    )
    print(f"Output: {out_path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble filtered posts + extraction → daily_trending.json"
    )
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--extraction-file", help="Path to Agent extraction JSON")
    group.add_argument("--extraction-json", help="Agent extraction JSON string")
    args = parser.parse_args()

    if args.extraction_file:
        with open(args.extraction_file, encoding="utf-8") as f:
            extraction = json.load(f)
    else:
        extraction = json.loads(args.extraction_json)

    run(args.date, extraction)


if __name__ == "__main__":
    main()
