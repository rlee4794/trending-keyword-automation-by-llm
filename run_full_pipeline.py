"""Re-fetch Instagram data with expanded seeds, then run full pipeline."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from social_pipeline.apify import fetch_platform_payloads
from social_pipeline.config import load_config, load_actor_config
from social_pipeline.fnb_filter import filter_google_fnb
from social_pipeline.normalize import normalize_records
from social_pipeline.llm_review import review_unmatched
from social_pipeline.ranking import rank_keywords

REPO = Path(__file__).resolve().parent
RUN_DIR = REPO / "runs" / "2026-06-24"
RAW_DIR = RUN_DIR / "raw"
CONFIG_PATH = REPO / "config" / "social_listening_v1.json"
ACTOR_CONFIG_PATH = REPO / "config" / "apify_actors_v1.json"
MAPPING_PATH = REPO / "data" / "mappings" / "canonical_mapping.csv"


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main():
    config = load_config(CONFIG_PATH)
    actor_config = load_actor_config(ACTOR_CONFIG_PATH)
    apify_token = os.environ["APIFY_TOKEN"]

    run_at_iso = "2026-06-24T17:30:00+08:00"
    windows = {
        "current_start": "2026-06-22T09:00:00+08:00",
        "current_end": "2026-06-24T17:30:00+08:00",
        "previous_start": "2026-06-15T09:00:00+08:00",
        "previous_end": "2026-06-22T09:00:00+08:00",
        "run_date": "2026-06-24",
    }

    seed_snapshot = {
        "snapshot_id": "seed_snapshot_2026-06-24_v2",
        "run_at": run_at_iso,
        "timezone": config.timezone,
        "broad_seed_group": "hk_food_drink_v1",
        "google_trends_seeds": config.broad_seeds.get("google", []),
        "instagram_seeds": config.broad_seeds.get("instagram", []),
        "expansion_terms": [],
    }

    print(f"[seeds] Instagram: {seed_snapshot['instagram_seeds']}")
    print(f"[seeds] Google: {seed_snapshot['google_trends_seeds']}")

    # 1. Fetch
    print("[apify] fetching platform payloads ...")
    raw_payloads = fetch_platform_payloads(
        actor_config=actor_config,
        seed_snapshot=seed_snapshot,
        windows=windows,
        apify_token=apify_token,
    )

    # Persist raw
    raw_dir = RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    for platform, payload in raw_payloads.items():
        _write_json(raw_dir / f"{platform}_raw.json", payload)
        records = payload.get("records", [])
        print(f"[raw] {platform}: {len(records)} records")

    # 2. FnB filter Google
    if "google" in raw_payloads:
        raw_payloads["google"] = filter_google_fnb(raw_payloads["google"])
        _write_json(raw_dir / "google_raw.json", raw_payloads["google"])

    # 3. Normalize
    print("[normalize] matching against canonical_mapping.csv ...")
    matched, unmatched_path = normalize_records(raw_payloads, MAPPING_PATH, RUN_DIR)
    print(f"[normalize] matched canonical keys: {len(matched)}")
    if unmatched_path:
        import csv
        with unmatched_path.open("r", encoding="utf-8", newline="") as f:
            remaining = sum(1 for _ in csv.DictReader(f))
        print(f"[normalize] unmatched queue: {remaining} terms")

    # 4. LLM review
    llm_stats = None
    if unmatched_path is not None:
        print("[llm-review] running LLM classification ...")
        llm_stats = review_unmatched(unmatched_path, MAPPING_PATH)
        print(f"[llm-review] done: {llm_stats}")
        if llm_stats.get("created", 0) + llm_stats.get("merged", 0) > 0:
            print("[normalize] re-normalizing with expanded mapping ...")
            matched, _ = normalize_records(raw_payloads, MAPPING_PATH, RUN_DIR)
            print(f"[normalize] after re-normalize: {len(matched)} canonical keys")

    # 5. Rank
    print("[ranking] scoring and ranking ...")
    keywords = rank_keywords(matched, config)
    print(f"[ranking] keywords passing threshold: {len(keywords)}")

    # 6. Write output
    output_path = RUN_DIR / "weekly_fnb_trending.json"
    output = {
        "schema_version": "1.0",
        "generated_at": run_at_iso,
        "period": {"start": windows["current_start"], "end": windows["current_end"]},
        "pipeline": {"mode": "live", "timezone": config.timezone},
        "keywords": keywords,
        "meta": {
            "total_candidates": sum(len(p.get("records", [])) for p in raw_payloads.values()),
            "total_ranked": len(keywords),
            "previous_feed_used": False,
            "llm_review": llm_stats,
        },
    }
    _write_json(output_path, output)
    print(f"[output] written to {output_path}")

    # Update symlink
    latest = REPO / "runs" / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(Path("2026-06-24"))

    # Print results
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
