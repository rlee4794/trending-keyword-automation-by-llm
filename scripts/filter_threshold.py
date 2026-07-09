#!/usr/bin/env python3
"""Filter normalized raw data by engagement threshold.

Reads google_raw.json and instagram_raw.json, keeps high-engagement
posts (like>threshold AND share>threshold), outputs filtered JSON.

Usage:
  python3 scripts/filter_threshold.py --date 2026-07-07
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def load_thresholds() -> dict:
    with open("config/threshold.json") as f:
        return json.load(f)


def filter_records(
    records: list[dict],
    min_likes: int,
    min_shares: int,
) -> tuple[list[dict], int, int]:
    """Filter records by engagement threshold. Returns (kept, total, skipped)."""
    kept = []
    for r in records:
        rp = r.get("raw_payload") or {}
        likes = rp.get("likes", 0) or 0
        shares = rp.get("reshare_count", 0) or 0

        if min_likes == 0 and min_shares == 0:
            kept.append(r)
        elif likes >= min_likes and shares >= min_shares:
            kept.append(r)

    return kept, len(records), len(records) - len(kept)


def run(date_str: str) -> None:
    """Filter raw data by threshold, write filtered JSON for agent consumption."""
    thresholds = load_thresholds()
    run_dir = Path(f"runs/{date_str}")
    raw_dir = run_dir / "raw"
    filtered_dir = run_dir / "filtered"
    filtered_dir.mkdir(parents=True, exist_ok=True)

    # ── Instagram ──────────────────────────────────────────────────
    ig_path = raw_dir / "instagram_raw.json"
    ig_posts = []
    ig_total = ig_skipped = 0

    if ig_path.exists():
        with ig_path.open() as f:
            ig_data = json.load(f)
        ig_cfg = thresholds.get("instagram", {})
        ig_posts, ig_total, ig_skipped = filter_records(
            ig_data.get("records", []),
            ig_cfg.get("min_likes", 1000),
            ig_cfg.get("min_shares", 500),
        )
        print(f"Instagram: {len(ig_posts)}/{ig_total} posts passed threshold "
              f"(like≥{ig_cfg.get('min_likes')}, share≥{ig_cfg.get('min_shares')})",
              file=sys.stderr)

    # ── Threads ─────────────────────────────────────────────────────
    # Threads raw data follows same schema as Instagram (normalize_raw.py handles it)
    threads_path = raw_dir / "threads_raw.json"
    threads_posts = []
    threads_total = threads_skipped = 0

    if threads_path.exists():
        with threads_path.open() as f:
            threads_data = json.load(f)
        th_cfg = thresholds.get("threads", {})
        threads_posts, threads_total, threads_skipped = filter_records(
            threads_data.get("records", []),
            th_cfg.get("min_likes", 1000),
            th_cfg.get("min_shares", 500),
        )
        print(f"Threads: {len(threads_posts)}/{threads_total} posts passed threshold",
              file=sys.stderr)

    # ── Google ──────────────────────────────────────────────────────
    google_path = raw_dir / "google_raw.json"
    google_terms = []

    if google_path.exists():
        with google_path.open() as f:
            google_data = json.load(f)
        min_vol = thresholds.get("google", {}).get("min_volume", 0)
        for r in google_data.get("records", []):
            vol = r.get("current_volume", 0) or 0
            if vol >= min_vol:
                google_terms.append({
                    "term": r.get("raw_representative", ""),
                    "volume": vol,
                    "related_terms": r.get("related_terms", []),
                })
        print(f"Google: {len(google_terms)} terms", file=sys.stderr)

    # ── Google Trends Taiwan ─────────────────────────────────────────
    google_tw_path = raw_dir / "google_tw_raw.json"
    google_tw_terms = []

    if google_tw_path.exists():
        with google_tw_path.open() as f:
            google_tw_data = json.load(f)
        min_vol = thresholds.get("google", {}).get("min_volume", 0)
        for r in google_tw_data.get("records", []):
            vol = r.get("current_volume", 0) or 0
            if vol >= min_vol:
                google_tw_terms.append({
                    "term": r.get("raw_representative", ""),
                    "volume": vol,
                    "related_terms": r.get("related_terms", []),
                })
        print(f"Google TW: {len(google_tw_terms)} terms", file=sys.stderr)

    # ── Assemble filtered output ────────────────────────────────────
    posts = []
    for r in ig_posts:
        rp = r.get("raw_payload") or {}
        posts.append({
            "platform": "instagram",
            "source": r.get("raw_term", ""),
            "source_kind": r.get("source_kind", ""),
            "geo": rp.get("geo", ""),
            "url": rp.get("url", ""),
            "likes": rp.get("likes", 0) or 0,
            "comments": rp.get("comments", 0) or 0,
            "shares": rp.get("reshare_count", 0) or 0,
            "taken_at": rp.get("taken_at_timestamp", ""),
            "caption_snippet": rp.get("caption_snippet", "")[:500],
            "hashtags": rp.get("hashtags", []),
        })

    for r in threads_posts:
        rp = r.get("raw_payload") or {}
        posts.append({
            "platform": "threads",
            "source": r.get("raw_term", ""),
            "source_kind": r.get("source_kind", ""),
            "geo": rp.get("geo", ""),
            "url": rp.get("url", ""),
            "likes": rp.get("likes", 0) or 0,
            "comments": rp.get("comments", 0) or 0,
            "shares": rp.get("reshare_count", 0) or 0,
            "taken_at": rp.get("taken_at_timestamp", ""),
            "caption_snippet": rp.get("caption_snippet", "")[:500],
            "hashtags": rp.get("hashtags", []),
        })

    output = {
        "date": date_str,
        "threshold": {
            "instagram": thresholds.get("instagram", {}),
            "threads": thresholds.get("threads", {}),
            "google": thresholds.get("google", {}),
        },
        "posts": posts,
        "google_trends": google_terms,
        "google_tw_trends": google_tw_terms,
        "_stats": {
            "instagram_total": ig_total,
            "instagram_passed": len(ig_posts),
            "threads_total": threads_total,
            "threads_passed": len(threads_posts),
            "google_tw_total": len(google_tw_terms),
        },
    }

    out_path = filtered_dir / "threshold_filtered.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    # Ensure trailing newline
    content = out_path.read_text()
    if content and not content.endswith("\n"):
        out_path.write_text(content + "\n")

    total_posts = len(posts)
    print(f"Output: {total_posts} posts + {len(google_terms)} Google terms + {len(google_tw_terms)} Google TW terms → {out_path}",
          file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter raw data by engagement threshold")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    args = parser.parse_args()
    run(args.date)


if __name__ == "__main__":
    main()
