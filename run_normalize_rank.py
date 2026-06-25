"""Run normalize + ranking only (skip Apify + LLM review)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from social_pipeline.config import load_config
from social_pipeline.normalize import normalize_records
from social_pipeline.ranking import rank_keywords

REPO = Path(__file__).resolve().parent
RUN_DIR = REPO / "runs" / "2026-06-24"
RAW_DIR = RUN_DIR / "raw"
CONFIG_PATH = REPO / "config" / "social_listening_v1.json"
MAPPING_PATH = REPO / "data" / "mappings" / "canonical_mapping.csv"
OUTPUT_DIR = RUN_DIR


def main():
    # Load raw payloads
    raw_payloads = {}
    for platform in ("google", "instagram"):
        raw_path = RAW_DIR / f"{platform}_raw.json"
        raw_payloads[platform] = json.loads(raw_path.read_text(encoding="utf-8"))
        print(f"[load] {platform}: {len(raw_payloads[platform].get('records', []))} records")

    config = load_config(CONFIG_PATH)

    # Normalize with expanded mapping
    print("[normalize] matching against canonical_mapping.csv ...")
    matched, unmatched_path = normalize_records(raw_payloads, MAPPING_PATH, OUTPUT_DIR)
    print(f"[normalize] matched canonical keys: {len(matched)}")
    if unmatched_path:
        # Count remaining unmatched
        import csv
        with unmatched_path.open("r", encoding="utf-8", newline="") as f:
            remaining = sum(1 for _ in csv.DictReader(f))
        print(f"[normalize] remaining unmatched: {remaining}")

    # Rank
    print("[ranking] scoring and ranking ...")
    keywords = rank_keywords(matched, config)
    print(f"[ranking] keywords passing threshold: {len(keywords)}")

    # Write output
    output_path = OUTPUT_DIR / "weekly_fnb_trending.json"
    output = {
        "schema_version": "1.0",
        "generated_at": "2026-06-24T16:30:00+08:00",
        "period": {
            "start": "2026-06-22T09:00:00+08:00",
            "end": "2026-06-24T16:30:00+08:00",
        },
        "pipeline": {
            "mode": "live",
            "timezone": "Asia/Hong_Kong",
        },
        "keywords": keywords,
        "meta": {
            "total_candidates": sum(
                len(p.get("records", [])) for p in raw_payloads.values()
            ),
            "total_ranked": len(keywords),
            "previous_feed_used": False,
            "llm_review": {"note": "partial — 13/22 batches completed before OOM, 218 mapping rows"},
        },
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[output] written to {output_path}")

    # Update symlink
    latest = REPO / "runs" / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(Path("2026-06-24"))

    # Print all keywords
    print(f"\n=== RANKED KEYWORDS ({len(keywords)}) ===")
    for kw in keywords:
        ig = kw["platforms"].get("instagram", {})
        goog = kw["platforms"].get("google", {})
        print(
            f"  #{kw['rank']:2d} {kw['display_name']:<30s} "
            f"score={kw['social_composite_score']:.4f}  "
            f"dir={kw['trend_direction']:<6s}  "
            f"hits={kw['platform_hits']}  "
            f"IG={ig.get('current_volume',0):>4d}(v={ig.get('velocity')})  "
            f"G={goog.get('current_volume',0):>4d}(v={goog.get('velocity')})"
        )


if __name__ == "__main__":
    main()
