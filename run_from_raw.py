"""Run the pipeline from existing raw data (skip Apify fetch).

Usage: python run_from_raw.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from social_pipeline.config import load_config
from social_pipeline.normalize import normalize_records
from social_pipeline.llm_review import review_unmatched
from social_pipeline.ranking import rank_keywords

REPO = Path(__file__).resolve().parent
RUN_DIR = REPO / "runs" / "2026-06-24"
RAW_DIR = RUN_DIR / "raw"
CONFIG_PATH = REPO / "config" / "social_listening_v1.json"
MAPPING_PATH = REPO / "data" / "mappings" / "canonical_mapping.csv"
OUTPUT_DIR = RUN_DIR  # write into same dated dir


def main():
    # 1. Load raw payloads
    raw_payloads = {}
    for platform in ("google", "instagram"):
        raw_path = RAW_DIR / f"{platform}_raw.json"
        if not raw_path.exists():
            print(f"[ERROR] missing raw data: {raw_path}", file=sys.stderr)
            sys.exit(1)
        raw_payloads[platform] = json.loads(raw_path.read_text(encoding="utf-8"))
        records = raw_payloads[platform].get("records", [])
        print(f"[load] {platform}: {len(records)} records")

    config = load_config(CONFIG_PATH)
    print(f"[config] platforms={list(config.platforms.keys())}")

    # 2. Normalize
    print("[normalize] matching against canonical_mapping.csv ...")
    matched, unmatched_path = normalize_records(raw_payloads, MAPPING_PATH, OUTPUT_DIR)
    print(f"[normalize] matched canonical keys: {len(matched)}")
    if unmatched_path:
        print(f"[normalize] unmatched queue: {unmatched_path}")

    # 3. LLM review
    llm_stats = None
    if unmatched_path is not None:
        print("[llm-review] running LLM classification on unmatched terms ...")
        llm_stats = review_unmatched(unmatched_path, MAPPING_PATH)
        print(f"[llm-review] done: {llm_stats}")

        # Re-normalize if mapping was expanded
        if llm_stats.get("created", 0) + llm_stats.get("merged", 0) > 0:
            print("[normalize] re-normalizing with expanded mapping ...")
            matched, _ = normalize_records(raw_payloads, MAPPING_PATH, OUTPUT_DIR)
            print(f"[normalize] after re-normalize: {len(matched)} canonical keys")

    # 4. Rank
    print("[ranking] scoring and ranking ...")
    keywords = rank_keywords(matched, config)
    print(f"[ranking] keywords passing threshold: {len(keywords)}")

    # 5. Write output
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
            "llm_review": llm_stats,
        },
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[output] written to {output_path}")

    # Also update runs/latest symlink
    latest = REPO / "runs" / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(Path("2026-06-24"))
    print("[output] runs/latest → 2026-06-24")

    # Print top keywords
    print("\n=== TOP KEYWORDS ===")
    for kw in keywords[:20]:
        print(
            f"  #{kw['rank']:2d} {kw['display_name']:<25s} "
            f"score={kw['social_composite_score']:.4f}  "
            f"dir={kw['trend_direction']:<6s}  "
            f"hits={kw['platform_hits']}"
        )


if __name__ == "__main__":
    main()
