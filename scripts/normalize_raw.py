#!/usr/bin/env python3
"""normalize_raw.py — Transform Apify raw JSON into pipeline-normalised format.

Reads (per region):
  HK: runs/{date}/raw/_apify/hk/google_apify_raw.json
      runs/{date}/raw/_apify/hk/ig_*_apify_raw.json
      runs/{date}/raw/_apify/hk/ig_user_*_apify_raw.json
      runs/{date}/raw/_apify/hk/threads_apify_raw.json
  TW: runs/{date}/raw/_apify/tw/google_apify_raw.json
      runs/{date}/raw/_apify/tw/ig_tw_user_*_apify_raw.json

Writes (per region):
  runs/{date}/raw/hk/google_raw.json
  runs/{date}/raw/hk/instagram_raw.json
  runs/{date}/raw/hk/threads_raw.json
  runs/{date}/raw/tw/google_raw.json
  runs/{date}/raw/tw/instagram_raw.json

Usage:
  python3 normalize_raw.py --date 2026-06-25 --run-dir runs/2026-06-25 --config config/social_listening_v1.json
  python3 normalize_raw.py --date 2026-07-09 --run-dir runs/2026-07-09 --config config/social_listening_v1.json --region tw
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
# Helpers
# ---------------------------------------------------------------------------

HKT = timezone(timedelta(hours=8))


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string, returning a timezone-aware datetime or None."""
    if not ts:
        return None
    try:
        s = ts.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _is_too_old(taken_at: datetime | None, cutoff: datetime) -> bool:
    """Return True if the post's taken_at is before the cutoff."""
    if taken_at is None:
        return False
    return taken_at < cutoff


def _load_seen_urls(run_dir: Path, region: str, lookback_days: int = 6) -> set[str]:
    """Collect all post URLs from previous N days' region-specific instagram_raw.json."""
    seen: set[str] = set()
    run_date = date.fromisoformat(run_dir.name)

    for i in range(1, lookback_days + 1):
        prev_date = run_date - timedelta(days=i)
        prev_raw = Path(f"runs/{prev_date.isoformat()}/raw/{region}/instagram_raw.json")
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


def _load_seen_threads_urls(run_dir: Path, lookback_days: int = 6) -> set[str]:
    """Collect all Threads post URLs from previous N days' hk/threads_raw.json."""
    seen: set[str] = set()
    run_date = date.fromisoformat(run_dir.name)

    for i in range(1, lookback_days + 1):
        prev_date = run_date - timedelta(days=i)
        prev_raw = Path(f"runs/{prev_date.isoformat()}/raw/hk/threads_raw.json")
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


def _normalise_timestamp(ts: Any) -> str | None:
    """Convert a timestamp to an ISO-8601 UTC string."""
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            return None
    return str(ts)


def _engagement_tier(likes: int, comments: int) -> str:
    score = likes + comments * 2
    if score > 5000:
        return "high"
    if score > 500:
        return "medium"
    return "low"


def _merge_source_kind(existing: dict[str, Any], new_kind: str) -> None:
    """Merge a new source_kind into an existing record's source_kind list.

    On first merge, converts the existing scalar source_kind into a list.
    Subsequent merges append to the list, avoiding duplicates.
    """
    old = existing.get("source_kind", "")
    if isinstance(old, list):
        kinds = old
    elif old:
        kinds = [old]
    else:
        kinds = []
    if new_kind and new_kind not in kinds:
        kinds.append(new_kind)
    existing["source_kind"] = kinds


def _compute_windows(target_date_str: str) -> dict[str, str]:
    """Compute current and previous weekly windows from target date."""
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

    if raw_items and any("trending_searches" in item for item in raw_items):
        for item in raw_items:
            geo = item.get("geo", "")
            language = item.get("language", "")
            for s in item.get("trending_searches", []):
                term = s.get("term") or ""
                current_volume = s.get("trend_volume_formatted", 0) or 0
                records.append({
                    "raw_representative": term,
                    "source_kind": "trending_search",
                    "current_volume": current_volume,
                    "previous_volume": None,
                    "related_terms": s.get("related_terms", []),
                    "raw_payload": {**s, "geo": geo, "language": language},
                })
    else:
        for item in raw_items:
            term = item.get("term") or ""
            current_volume = item.get("trend_volume_raw", 0) or 0
            records.append({
                "raw_representative": term,
                "source_kind": "trending_search",
                "current_volume": current_volume,
                "previous_volume": None,
                "related_terms": item.get("related_terms", []),
                "raw_payload": item,
            })

    return {
        "platform": "google_trends",
        "run_at": windows["current_start"],
        "window_current": {"start": windows["current_start"], "end": windows["current_end"]},
        "window_previous": {"start": windows["previous_start"], "end": windows["previous_end"]},
        "seed_context": {"broad_seed_group": broad_seed_group},
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
            "raw_representative": f"#{hashtag}",
            "source_kind": "hashtag",
            "current_volume": 1,
            "previous_volume": None,
            "raw_payload": {
                "engagement_hint": _engagement_tier(likes, comments),
                "geo": "HK",
                "likes": likes,
                "comments": comments,
                "taken_at_timestamp": _normalise_timestamp(
                    item.get("taken_at_timestamp") or item.get("taken_at")
                ),
                "hashtags": item.get("hashtags", []),
                "url": item.get("url"),
                "reshare_count": item.get("reshare_count"),
                "caption": caption or "",
            },
        })
    return records


def _normalise_instagram_user_posts(
    raw_items: list[dict[str, Any]],
    username: str,
    geo: str = "HK",
) -> list[dict[str, Any]]:
    """Convert Instagram user-posts scraper output into pipeline-normalised records.

    Args:
        geo: Geo tag for the source ("HK" for Hong Kong, "TW" for Taiwan).
    """
    records: list[dict[str, Any]] = []
    for item in raw_items:
        caption = item.get("caption") or ""
        likes = item.get("like_count", 0) or 0
        comments = item.get("comment_count", 0) or 0
        records.append({
            "raw_term": f"@{username}",
            "source_kind": "user_post",
            "current_volume": 1,
            "previous_volume": None,
            "raw_payload": {
                "engagement_hint": _engagement_tier(likes, comments),
                "geo": geo,
                "likes": likes,
                "comments": comments,
                "taken_at_timestamp": _normalise_timestamp(
                    item.get("taken_at_timestamp") or item.get("taken_at")
                ),
                "hashtags": item.get("hashtags", []),
                "url": item.get("url"),
                "reshare_count": item.get("reshare_count"),
                "caption": caption or "",
                "source_username": username,
            },
        })
    return records


def _normalise_threads_posts(
    raw_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert Threads search scraper output into pipeline-normalised records."""
    records: list[dict[str, Any]] = []
    for item in raw_items:
        text = item.get("text_content") or ""
        likes = item.get("like_count", 0) or 0
        replies = item.get("reply_count", 0) or 0
        reposts = item.get("repost_count", 0) or 0
        shares = item.get("share_count", 0) or 0
        records.append({
            "raw_term": item.get("search_keyword", "threads"),
            "raw_representative": item.get("search_keyword", "threads"),
            "source_kind": "search",
            "current_volume": 1,
            "previous_volume": None,
            "raw_payload": {
                "engagement_hint": _engagement_tier(likes, replies),
                "geo": "HK",
                "likes": likes,
                "comments": replies,
                "reposts": reposts,
                "reshare_count": shares,
                "taken_at_timestamp": _normalise_timestamp(item.get("created_at")),
                "hashtags": item.get("hashtags", []),
                "url": item.get("post_url", ""),
                "caption": text or "",
                "search_keyword": item.get("search_keyword"),
                "search_filter": item.get("search_filter"),
                "username": item.get("username"),
                "display_name": item.get("display_name"),
                "view_count": item.get("view_count"),
            },
        })
    return records


# ---------------------------------------------------------------------------
# Region processing
# ---------------------------------------------------------------------------

def _process_region(
    region: str,
    run_dir: Path,
    config: dict[str, Any],
    windows: dict[str, str],
    max_age_days: int,
    crossday_dedup: bool = True,
) -> None:
    """Process one region's Apify data → normalized raw JSON.

    Region "hk": Google Trends + IG hashtags + IG users + Threads
    Region "tw": Google Trends + IG TW users
    """
    apify_dir = run_dir / "raw" / "_apify" / region
    raw_out_dir = run_dir / "raw" / region

    if not apify_dir.exists():
        print(f"{region}: SKIPPED (no _apify/{region} data)", file=sys.stderr)
        return

    broad_seeds_key = "google_taiwan" if region == "tw" else "google"
    broad_seed_group = config.get("broad_seeds", {}).get(broad_seeds_key, [])

    # ── Google Trends ──────────────────────────────────────────────
    google_apify_path = apify_dir / "google_apify_raw.json"
    if google_apify_path.exists() and google_apify_path.stat().st_size > 0:
        with google_apify_path.open(encoding="utf-8") as f:
            google_raw_items = json.load(f)
        if not isinstance(google_raw_items, list):
            google_raw_items = []
        google_output = _normalise_google_trends(google_raw_items, broad_seed_group, windows)
        # Tag TW geo on records
        if region == "tw":
            for rec in google_output["records"]:
                rp = rec.get("raw_payload", {})
                rp["geo"] = "TW"
                rec["raw_payload"] = rp
        google_out_path = raw_out_dir / "google_raw.json"
        google_out_path.parent.mkdir(parents=True, exist_ok=True)
        google_out_path.write_text(
            json.dumps(google_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{region} google: {len(google_output['records'])} records")
    else:
        print(f"{region} google: SKIPPED (no _apify data)")

    # ── Instagram ───────────────────────────────────────────────────
    if region == "hk":
        all_ig_files = sorted(glob(str(apify_dir / "ig_*_apify_raw.json")))
        # ig_* also matches ig_user_* — exclude user files from hashtag processing
        ig_hashtag_files = [f for f in all_ig_files if "ig_user_" not in Path(f).stem]
        ig_user_files = sorted(glob(str(apify_dir / "ig_user_*_apify_raw.json")))
    else:
        ig_hashtag_files = []
        ig_user_files = []
    ig_tw_user_files = sorted(glob(str(apify_dir / "ig_tw_user_*_apify_raw.json"))) if region == "tw" else []

    if ig_hashtag_files or ig_user_files or ig_tw_user_files:
        age_cutoff = None
        if max_age_days > 0:
            scrape_dt = datetime.strptime(windows["run_date"], "%Y-%m-%d").replace(tzinfo=HKT)
            age_cutoff = scrape_dt - timedelta(days=max_age_days)
            print(f"{region} instagram: age filter enabled, discarding posts older than {age_cutoff.isoformat()}", file=sys.stderr)

        if crossday_dedup:
            seen_urls = _load_seen_urls(run_dir, region, lookback_days=6)
            print(f"{region} instagram: {len(seen_urls)} seen URLs from previous days", file=sys.stderr)
        else:
            seen_urls = set()
            print(f"{region} instagram: cross-day dedup DISABLED", file=sys.stderr)

        all_records: list[dict[str, Any]] = []
        dedup_skipped = 0
        dedup_merged = 0
        age_skipped = 0
        url_index: dict[str, int] = {}  # URL -> index in all_records for in-run source_kind merge

        # HK hashtag posts
        for ig_file in ig_hashtag_files:
            with open(ig_file, encoding="utf-8") as f:
                ig_raw_items = json.load(f)
            if not isinstance(ig_raw_items, list):
                ig_raw_items = []
            stem = Path(ig_file).stem
            hashtag = stem.replace("ig_", "").replace("_apify_raw", "")
            records = _normalise_instagram_posts(ig_raw_items, hashtag)
            for rec in records:
                if age_cutoff is not None:
                    taken_at = _parse_timestamp((rec.get("raw_payload") or {}).get("taken_at_timestamp"))
                    if _is_too_old(taken_at, age_cutoff):
                        age_skipped += 1
                        continue
                url = (rec.get("raw_payload") or {}).get("url", "")
                if url and url in seen_urls:
                    dedup_skipped += 1
                    continue
                if url and url in url_index:
                    _merge_source_kind(all_records[url_index[url]], rec.get("source_kind", ""))
                    dedup_merged += 1
                    continue
                all_records.append(rec)
                if url:
                    url_index[url] = len(all_records) - 1

        # HK user posts
        for ig_file in ig_user_files:
            with open(ig_file, encoding="utf-8") as f:
                ig_raw_items = json.load(f)
            if not isinstance(ig_raw_items, list):
                ig_raw_items = []
            stem = Path(ig_file).stem
            username = stem.replace("ig_user_", "").replace("_apify_raw", "")
            records = _normalise_instagram_user_posts(ig_raw_items, username, geo="HK")
            for rec in records:
                if age_cutoff is not None:
                    taken_at = _parse_timestamp((rec.get("raw_payload") or {}).get("taken_at_timestamp"))
                    if _is_too_old(taken_at, age_cutoff):
                        age_skipped += 1
                        continue
                url = (rec.get("raw_payload") or {}).get("url", "")
                if url and url in seen_urls:
                    dedup_skipped += 1
                    continue
                if url and url in url_index:
                    _merge_source_kind(all_records[url_index[url]], rec.get("source_kind", ""))
                    dedup_merged += 1
                    continue
                all_records.append(rec)
                if url:
                    url_index[url] = len(all_records) - 1

        # TW user posts
        tw_user_count = 0
        for ig_file in ig_tw_user_files:
            with open(ig_file, encoding="utf-8") as f:
                ig_raw_items = json.load(f)
            if not isinstance(ig_raw_items, list):
                ig_raw_items = []
            stem = Path(ig_file).stem
            username = stem.replace("ig_tw_user_", "").replace("_apify_raw", "")
            records = _normalise_instagram_user_posts(ig_raw_items, username, geo="TW")
            for rec in records:
                if age_cutoff is not None:
                    taken_at = _parse_timestamp((rec.get("raw_payload") or {}).get("taken_at_timestamp"))
                    if _is_too_old(taken_at, age_cutoff):
                        age_skipped += 1
                        continue
                url = (rec.get("raw_payload") or {}).get("url", "")
                if url and url in seen_urls:
                    dedup_skipped += 1
                    continue
                if url and url in url_index:
                    _merge_source_kind(all_records[url_index[url]], rec.get("source_kind", ""))
                    dedup_merged += 1
                    continue
                all_records.append(rec)
                if url:
                    url_index[url] = len(all_records) - 1
                tw_user_count += 1

        total_before = len(all_records) + dedup_skipped + dedup_merged + age_skipped

        instagram_output = {
            "platform": "instagram",
            "region": region,
            "run_at": windows["current_start"],
            "window_current": {"start": windows["current_start"], "end": windows["current_end"]},
            "window_previous": {"start": windows["previous_start"], "end": windows["previous_end"]},
            "seed_context": {"broad_seed_group": broad_seed_group},
            "records": all_records,
            "_dedup": {"lookback_days": 6, "seen_urls_count": len(seen_urls), "skipped": dedup_skipped},
        }
        if max_age_days > 0:
            instagram_output["_age_filter"] = {
                "max_age_days": max_age_days,
                "cutoff": age_cutoff.isoformat() if age_cutoff else None,
                "skipped": age_skipped,
            }
        ig_out_path = raw_out_dir / "instagram_raw.json"
        ig_out_path.parent.mkdir(parents=True, exist_ok=True)
        ig_out_path.write_text(
            json.dumps(instagram_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        age_msg = f", {age_skipped} age-skipped" if age_skipped > 0 else ""
        tw_msg = f", {tw_user_count} from TW users" if tw_user_count > 0 else ""
        dedup_merge_msg = f", {dedup_merged} dedup-merged" if dedup_merged > 0 else ""
        print(f"{region} instagram: {len(all_records)} records kept, {dedup_skipped} dedup-skipped{dedup_merge_msg}{age_msg}{tw_msg} (from {total_before} total)")
    else:
        print(f"{region} instagram: SKIPPED (no _apify data)")

    # ── Threads (HK only) ───────────────────────────────────────────
    if region != "hk":
        return

    threads_apify_path = apify_dir / "threads_apify_raw.json"
    if threads_apify_path.exists() and threads_apify_path.stat().st_size > 0:
        with threads_apify_path.open(encoding="utf-8") as f:
            threads_raw_items = json.load(f)
        if not isinstance(threads_raw_items, list):
            threads_raw_items = []

        threads_age_cutoff = None
        if max_age_days > 0:
            scrape_dt = datetime.strptime(windows["run_date"], "%Y-%m-%d").replace(tzinfo=HKT)
            threads_age_cutoff = scrape_dt - timedelta(days=max_age_days)
            print(f"threads: age filter enabled, discarding posts older than {threads_age_cutoff.isoformat()}", file=sys.stderr)

        if crossday_dedup:
            seen_threads_urls = _load_seen_threads_urls(run_dir, lookback_days=6)
            print(f"threads: {len(seen_threads_urls)} seen URLs from previous days", file=sys.stderr)
        else:
            seen_threads_urls = set()
            print(f"threads: cross-day dedup DISABLED", file=sys.stderr)

        all_threads: list[dict[str, Any]] = []
        threads_age_skipped = 0
        threads_dedup_skipped = 0
        records = _normalise_threads_posts(threads_raw_items)
        for rec in records:
            if threads_age_cutoff is not None:
                taken_at = _parse_timestamp((rec.get("raw_payload") or {}).get("taken_at_timestamp"))
                if _is_too_old(taken_at, threads_age_cutoff):
                    threads_age_skipped += 1
                    continue
            url = (rec.get("raw_payload") or {}).get("url", "")
            if url and url in seen_threads_urls:
                threads_dedup_skipped += 1
                continue
            all_threads.append(rec)

        threads_total_before = len(all_threads) + threads_dedup_skipped + threads_age_skipped

        threads_output = {
            "platform": "threads",
            "region": "hk",
            "run_at": windows["current_start"],
            "window_current": {"start": windows["current_start"], "end": windows["current_end"]},
            "window_previous": {"start": windows["previous_start"], "end": windows["previous_end"]},
            "seed_context": {"broad_seed_group": broad_seed_group},
            "records": all_threads,
            "_dedup": {"lookback_days": 6, "seen_urls_count": len(seen_threads_urls), "skipped": threads_dedup_skipped},
        }
        if max_age_days > 0:
            threads_output["_age_filter"] = {
                "max_age_days": max_age_days,
                "cutoff": threads_age_cutoff.isoformat() if threads_age_cutoff else None,
                "skipped": threads_age_skipped,
            }
        threads_out_path = raw_out_dir / "threads_raw.json"
        threads_out_path.parent.mkdir(parents=True, exist_ok=True)
        threads_out_path.write_text(
            json.dumps(threads_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        threads_age_msg = f", {threads_age_skipped} age-skipped" if threads_age_skipped > 0 else ""
        print(f"threads: {len(all_threads)} records kept, {threads_dedup_skipped} dedup-skipped{threads_age_msg} (from {threads_total_before} total)")
    else:
        print("threads: SKIPPED (no _apify data)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Apify raw → pipeline format")
    parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--run-dir", required=True, help="Run directory (e.g. runs/2026-06-25)")
    parser.add_argument("--config", required=True, help="Path to social_listening_v1.json")
    parser.add_argument("--region", choices=["hk", "tw"], help="Process only this region (default: both)")
    parser.add_argument("--max-age-days", type=int, default=30,
                        help="Discard Instagram posts older than N days (default: 30, 0 = disable)")
    parser.add_argument("--no-crossday-dedup", action="store_true",
                        help="Disable cross-day URL dedup (in-run source_kind merge still active)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    config_path = Path(args.config)
    target_date = args.date
    max_age_days = args.max_age_days
    crossday_dedup = not args.no_crossday_dedup

    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)

    windows = _compute_windows(target_date)

    regions_to_process = [args.region] if args.region else ["hk", "tw"]

    for region in regions_to_process:
        _process_region(region, run_dir, config, windows, max_age_days, crossday_dedup)


if __name__ == "__main__":
    main()
