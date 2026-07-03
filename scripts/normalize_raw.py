#!/usr/bin/env python3
"""normalize_raw.py — Transform Apify raw JSON into pipeline-normalised format.

Reads:
  runs/{date}/raw/_apify/google_apify_raw.json
  runs/{date}/raw/_apify/ig_*.json
  config/social_listening_v1.json (for broad_seed_group metadata)

Writes:
  runs/{date}/raw/google_raw.json
  runs/{date}/raw/instagram_raw.json

Usage:
  python3 normalize_raw.py --date 2026-06-25 --run-dir runs/2026-06-25 --config config/social_listening_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from glob import glob
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers (mirror social_pipeline.apify normalisers for standalone use)
# ---------------------------------------------------------------------------

HKT = timezone(timedelta(hours=8))


def _load_seen_urls(run_dir: Path, lookback_days: int = 6) -> set[str]:
    """Collect all post URLs from previous N days' instagram_raw.json.

    Reads raw Instagram data from previous days to build a dedup set.
    A post that appeared in a previous day's top-N scrape should not
    be counted again in today's output — it contributes no volume and
    no engagement for the current day.

    Missing or malformed files are silently skipped (fail-open).
    """
    seen: set[str] = set()
    run_date = date.fromisoformat(run_dir.name)

    for i in range(1, lookback_days + 1):
        prev_date = run_date - timedelta(days=i)
        prev_raw = Path(f"runs/{prev_date.isoformat()}/raw/instagram_raw.json")
        if not prev_raw.exists():
            continue
        try:
            with prev_raw.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for rec in data.get("records", []):
                url = (rec.get("raw_payload") or {}).get("url", "")
                if url:
                    seen.add(url)
        except (json.JSONDecodeError, OSError):
            continue

    return seen


def _engagement_tier(likes: int, comments: int) -> str:
    score = likes + comments * 2
    if score > 5000:
        return "high"
    if score > 500:
        return "medium"
    return "low"


def _compute_windows(target_date_str: str) -> dict[str, str]:
    """Compute current and previous weekly windows from target date.

    window_current = target_date ±3 days
    window_previous = 7 days before window_current
    """
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=HKT)
    current_start = target_dt - timedelta(days=3)
    current_end = target_dt + timedelta(days=3)
    current_end = current_end.replace(hour=23, minute=59, second=59)
    previous_start = current_start - timedelta(days=7)
    previous_end = current_start
    return {
        "current_start": current_start.isoformat(),
        "current_end": current_end.isoformat(),
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "run_date": target_date_str,
    }


def _normalise_google_trends(
    raw_items: list[dict[str, Any]],
    broad_seed_group: list[str],
    windows: dict[str, str],
) -> dict[str, Any]:
    """Convert Google Trends Apify dataset items into pipeline-normalised format."""
    records: list[dict[str, Any]] = []
    for item in raw_items:
        term = item.get("term") or ""
        current_volume = item.get("trend_volume_raw", 0) or 0
        records.append({
            "raw_term": term,
            "source_kind": "trending_search",
            "current_volume": current_volume,
            "previous_volume": None,
            "raw_payload": item,
        })

    return {
        "platform": "google_trends",
        "run_at": windows["current_start"],
        "window_current": {
            "start": windows["current_start"],
            "end": windows["current_end"],
        },
        "window_previous": {
            "start": windows["previous_start"],
            "end": windows["previous_end"],
        },
        "seed_context": {
            "broad_seed_group": broad_seed_group,
        },
        "records": records,
    }


def _normalise_instagram_posts(
    raw_items: list[dict[str, Any]],
    hashtag: str,
) -> list[dict[str, Any]]:
    """Convert Instagram hashtag scraper output into pipeline-normalised records."""
    records: list[dict[str, Any]] = []
    for item in raw_items:
        caption = item.get("caption") or ""
        likes = item.get("like_count", 0) or 0
        comments = item.get("comment_count", 0) or 0
        records.append({
            "raw_term": f"#{hashtag}",
            "source_kind": "hashtag",
            "current_volume": 1,
            "previous_volume": None,
            "raw_payload": {
                "engagement_hint": _engagement_tier(likes, comments),
                "geo": "HK",
                "likes": likes,
                "comments": comments,
                "taken_at_timestamp": item.get("taken_at_timestamp"),
                "hashtags": item.get("hashtags", []),
                "url": item.get("url"),
                "reshare_count": item.get("reshare_count"),
                "caption_snippet": caption[:500] if caption else "",
            },
        })
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Apify raw → pipeline format")
    parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--run-dir", required=True, help="Run directory (e.g. runs/2026-06-25)")
    parser.add_argument("--config", required=True, help="Path to social_listening_v1.json")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    config_path = Path(args.config)
    target_date = args.date

    # Load config for broad_seed_group
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)
    broad_seed_group = config.get("broad_seeds", {}).get("google", ["香港美食", "hk food"])

    # Compute windows
    windows = _compute_windows(target_date)

    apify_dir = run_dir / "raw" / "_apify"
    if not apify_dir.exists():
        print(f"ERROR: Apify raw directory not found: {apify_dir}", file=sys.stderr)
        sys.exit(1)

    # --- Google Trends ---
    google_apify_path = apify_dir / "google_apify_raw.json"
    if google_apify_path.exists() and google_apify_path.stat().st_size > 0:
        with google_apify_path.open(encoding="utf-8") as f:
            google_raw_items = json.load(f)
        if not isinstance(google_raw_items, list):
            google_raw_items = []
        google_output = _normalise_google_trends(google_raw_items, broad_seed_group, windows)
        google_out_path = run_dir / "raw" / "google_raw.json"
        google_out_path.parent.mkdir(parents=True, exist_ok=True)
        google_out_path.write_text(
            json.dumps(google_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"google: {len(google_output['records'])} records")
    else:
        print("google: SKIPPED (no _apify data)")

    # --- Instagram (merge all hashtag files, with cross-day dedup) ---
    ig_files = sorted(glob(str(apify_dir / "ig_*_apify_raw.json")))
    if ig_files:
        # Load seen URLs from previous 6 days for cross-day dedup.
        # A post that already appeared in a previous day's top-N scrape
        # is excluded from today's output — it contributes zero volume
        # and zero engagement for the current day.
        seen_urls = _load_seen_urls(run_dir, lookback_days=6)
        print(f"instagram: {len(seen_urls)} seen URLs from previous days", file=sys.stderr)

        all_records: list[dict[str, Any]] = []
        dedup_skipped = 0
        for ig_file in ig_files:
            with open(ig_file, encoding="utf-8") as f:
                ig_raw_items = json.load(f)
            if not isinstance(ig_raw_items, list):
                ig_raw_items = []
            # Extract hashtag from filename: ig_<hashtag>_apify_raw.json
            stem = Path(ig_file).stem  # ig_hkfood_apify_raw
            hashtag = stem.replace("ig_", "").replace("_apify_raw", "")
            records = _normalise_instagram_posts(ig_raw_items, hashtag)
            # Cross-day dedup: skip posts whose URL was already seen
            for rec in records:
                url = (rec.get("raw_payload") or {}).get("url", "")
                if url and url in seen_urls:
                    dedup_skipped += 1
                    continue
                all_records.append(rec)

        total_before = len(all_records) + dedup_skipped

        instagram_output = {
            "platform": "instagram",
            "run_at": windows["current_start"],
            "window_current": {
                "start": windows["current_start"],
                "end": windows["current_end"],
            },
            "window_previous": {
                "start": windows["previous_start"],
                "end": windows["previous_end"],
            },
            "seed_context": {
                "broad_seed_group": broad_seed_group,
            },
            "records": all_records,
            "_dedup": {
                "lookback_days": 6,
                "seen_urls_count": len(seen_urls),
                "skipped": dedup_skipped,
            },
        }
        ig_out_path = run_dir / "raw" / "instagram_raw.json"
        ig_out_path.parent.mkdir(parents=True, exist_ok=True)
        ig_out_path.write_text(
            json.dumps(instagram_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"instagram: {len(all_records)} records kept, {dedup_skipped} dedup-skipped (from {total_before} total)")
    else:
        print("instagram: SKIPPED (no _apify data)")


if __name__ == "__main__":
    main()
