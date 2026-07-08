#!/usr/bin/env python3
"""Prepare keyword snapshots for Agent trend matching, then merge results.

Two modes:

1. PREPARE (default): Read today + 7-days-ago daily_trending.json keywords,
   output a JSON the Agent uses for fuzzy matching and classification.

2. MERGE (--merge): Take Agent's matching output, add trend fields to
   today's daily_trending.json keywords, write back.

Usage:
  # Step A: prepare snapshots for Agent
  python3 scripts/trend_comparison.py --date 2026-07-08

  # Step B: after Agent produces matching JSON, merge back
  python3 scripts/trend_comparison.py --date 2026-07-08 --merge /tmp/agent_trend.json
"""

from __future__ import annotations

import argparse
import json
import sys
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


def _strip_keywords(data: dict) -> list[dict]:
    """Extract a minimal keyword list for Agent consumption."""
    return [
        {
            "term": kw.get("term", ""),
            "type": kw.get("type", ""),
            "post_count": kw.get("post_count", 0),
            "total_likes": kw.get("total_likes", 0),
            "total_shares": kw.get("total_shares", 0),
            "total_comments": kw.get("total_comments", 0),
            "platforms": kw.get("platforms", []),
        }
        for kw in data.get("keywords", [])
    ]


def _build_seen_set(target_date: str, lookback: int = 7) -> set[str]:
    """Collect all keyword terms from intermediate days (target - lookback to target - 1).

    A keyword that appears in any of these days is NOT 'new' — it existed
    within the lookback window.
    """
    seen: set[str] = set()
    target_dt = date.fromisoformat(target_date)
    for i in range(1, lookback):
        ds = (target_dt - timedelta(days=i)).isoformat()
        data = _load_daily(ds)
        if not data:
            continue
        for kw in data.get("keywords", []):
            term = kw.get("term", "").strip()
            if term:
                seen.add(term)
    return seen


def prepare(date_str: str, output_path: str | None = None) -> dict:
    """Prepare today vs 7-days-ago keyword snapshots for Agent matching.

    Returns:
      - today_keywords: today's keyword list
      - prev_keywords: 7-days-ago keyword list (null if unavailable)
      - seen_in_period: set of terms that appeared in the last 7 days
        (intermediate days, exact match). A today keyword NOT in this set
        is a candidate for 'new'.
      - today_date, prev_date
    """
    today_data = _load_daily(date_str)
    if not today_data:
        print(f"ERROR: No daily_trending.json for {date_str}", file=sys.stderr)
        sys.exit(1)

    target_dt = date.fromisoformat(date_str)
    prev_date_str = (target_dt - timedelta(days=7)).isoformat()
    prev_data = _load_daily(prev_date_str)

    today_keywords = _strip_keywords(today_data)
    prev_keywords = _strip_keywords(prev_data) if prev_data else None
    seen_in_period = _build_seen_set(date_str, lookback=7)

    result = {
        "today_date": date_str,
        "prev_date": prev_date_str,
        "prev_available": prev_data is not None,
        "today_keywords": today_keywords,
        "prev_keywords": prev_keywords,
        "seen_in_period": sorted(seen_in_period),
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Snapshots → {out}", file=sys.stderr)
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    return result


def merge(date_str: str, agent_output_path: str) -> None:
    """Merge Agent trend matching results into today's daily_trending.json.

    The Agent output should be a JSON with:
      { "matches": [{ "today_term", "today_type", "classification", ... }] }

    For each match, adds a `trend` field to the corresponding keyword in
    today's daily_trending.json. Only "new" and "surging" classifications
    get trend fields.
    """
    run_dir = Path(f"runs/{date_str}")
    daily_path = run_dir / "daily_trending.json"

    if not daily_path.exists():
        print(f"ERROR: {daily_path} not found", file=sys.stderr)
        sys.exit(1)

    with daily_path.open(encoding="utf-8") as f:
        daily = json.load(f)

    with open(agent_output_path, encoding="utf-8") as f:
        agent_result = json.load(f)

    matches = agent_result.get("matches", [])
    if not matches:
        print("No trend matches to merge", file=sys.stderr)
        return

    # Build lookup: (term, type) → keyword index
    kw_index: dict[tuple[str, str], int] = {}
    for i, kw in enumerate(daily.get("keywords", [])):
        key = (kw.get("term", ""), kw.get("type", ""))
        kw_index[key] = i

    applied = 0
    for m in matches:
        classification = m.get("classification", "")
        if classification not in ("new", "surging"):
            continue

        today_term = m.get("today_term", "")
        today_type = m.get("today_type", "")
        key = (today_term, today_type)

        if key not in kw_index:
            print(
                f"⚠️  MERGE: no keyword found for '{today_term}' ({today_type}), skipping",
                file=sys.stderr,
            )
            continue

        idx = kw_index[key]
        trend = {"direction": classification}

        if classification == "surging":
            trend["matched_term"] = m.get("matched_term", "")
            trend["prev_date"] = m.get("prev_date", "")
            trend["prev_post_count"] = m.get("prev_post_count", 0)
            trend["prev_total_likes"] = m.get("prev_total_likes", 0)

        daily["keywords"][idx]["trend"] = trend
        applied += 1

    # Write back
    daily_path.write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
    # Ensure trailing newline
    content = daily_path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        daily_path.write_text(content + "\n", encoding="utf-8")

    new_count = sum(1 for m in matches if m.get("classification") == "new")
    surging_count = sum(1 for m in matches if m.get("classification") == "surging")
    print(
        f"✅ MERGE: {applied} trend(s) → {daily_path} "
        f"({new_count} new, {surging_count} surging)",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare/merge keyword trend snapshots for Agent matching"
    )
    parser.add_argument(
        "--date", required=True,
        help="Target date YYYY-MM-DD (today's data)",
    )
    parser.add_argument(
        "--merge",
        help="Path to Agent trend matching JSON. If set, merges results into daily_trending.json",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output path for prepared snapshots (default: stdout)",
    )
    args = parser.parse_args()

    if args.merge:
        merge(args.date, args.merge)
    else:
        prepare(args.date, args.output)


if __name__ == "__main__":
    main()
