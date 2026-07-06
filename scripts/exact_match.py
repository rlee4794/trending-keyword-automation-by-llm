#!/usr/bin/env python3
"""Exact-match normalization: map filtered platform terms to canonical keys.

Reads filtered JSON from Step 2B and canonical_mapping.csv, performs
deterministic exact-match lookup, and outputs matched groups for ranking
plus an unmatched review queue for Step 4.

Usage:
  # Step 3: full mode (produces matched_groups.json + unmatched_review_queue.csv)
  python3 scripts/exact_match.py --date 2026-06-25

  # Step 4 re-normalize: skip unmatched queue (only update matched_groups.json)
  python3 scripts/exact_match.py --date 2026-06-25 --skip-unmatched
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────

def _clean_term(term: str) -> str:
    """Normalize a term for exact-match lookup."""
    t = term.strip()
    if t.startswith("#"):
        t = t[1:]
    return t.lower().strip()


def _load_mapping(mapping_path: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Load canonical_mapping.csv.

    Returns:
        match_to_key:  {match_value → canonical_key}
        key_to_display: {canonical_key → display_term}
        key_to_desc:    {canonical_key → enriched_description}
        key_to_category: {canonical_key → category}
        key_to_potential: {canonical_key → potential}
    """
    match_to_key: dict[str, str] = {}
    key_to_display: dict[str, str] = {}
    key_to_desc: dict[str, str] = {}
    key_to_category: dict[str, str] = {}
    key_to_potential: dict[str, str] = {}

    with mapping_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            mv = (row.get("match_value") or "").strip()
            ck = (row.get("canonical_key") or "").strip()
            dt = (row.get("display_term") or "").strip()
            desc = (row.get("enriched_description") or "").strip()
            if mv and ck:
                # Detect conflicts: same match_value, different canonical_key
                if mv in match_to_key and match_to_key[mv] != ck:
                    existing_ck = match_to_key[mv]
                    print(
                        f"  WARNING: match_value '{mv}' mapped to both "
                        f"'{existing_ck}' (earlier) and '{ck}' (later). "
                        f"First-match-wins → '{existing_ck}'.",
                        file=sys.stderr,
                    )
                    continue  # first-match-wins
                match_to_key[mv] = ck
                if ck not in key_to_display:
                    key_to_display[ck] = dt or ck
                if desc and ck not in key_to_desc:
                    key_to_desc[ck] = desc
                cat = (row.get("category") or "").strip()
                if cat and ck not in key_to_category:
                    key_to_category[ck] = cat
                pot = (row.get('potential') or '').strip()
                if pot and ck not in key_to_potential:
                    key_to_potential[ck] = pot

    return match_to_key, key_to_display, key_to_desc, key_to_category, key_to_potential


def _load_engagement_weights(config_path: Path) -> dict[str, int]:
    """Load IG engagement weights from config, with safe defaults."""
    defaults = {"likes": 1, "comments": 2, "shares": 4}
    if not config_path.exists():
        return defaults
    with config_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("engagement_weights", defaults)


def _load_popular_post_config(config_path: Path) -> dict | None:
    """Load popular post boost config, or None if disabled.

    Returns None if config is missing or popular_post.enabled is false.
    """
    if not config_path.exists():
        return None
    with config_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    pp = cfg.get("popular_post", {})
    if not pp.get("enabled", False):
        return None
    return pp


def _compute_post_engagement(
    likes: int, comments: int, shares: int, weights: dict[str, int]
) -> float:
    """Compute per-post engagement score using log-normalised weighted sum."""
    return (
        math.log(weights["likes"] * likes + 1)
        + math.log(weights["comments"] * comments + 1)
        + math.log(weights["shares"] * shares + 1)
    )


def _ensure_dir(path: Path) -> None:
    """Create parent directory if it doesn't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: object) -> None:
    """Write JSON with consistent formatting."""
    _ensure_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_term(term_raw) -> tuple[str, str] | None:
    """Parse a term entry into (text, source).

    Supports both legacy format (plain string → source="keyword")
    and new format (dict with text + source fields).

    Returns None if the term text is empty after cleaning.
    """
    if isinstance(term_raw, str):
        text = term_raw.strip()
        source = "keyword"
    elif isinstance(term_raw, dict):
        text = (term_raw.get("text") or "").strip()
        source = (term_raw.get("source") or "keyword").strip()
    else:
        return None

    if not text:
        return None
    return text, source


# ── main logic ───────────────────────────────────────────────────────────

def run(date_str: str, skip_unmatched: bool = False) -> None:
    """Run exact-match normalization for a given date."""
    run_dir = Path(f"runs/{date_str}")
    mapping_path = Path("data/mappings/canonical_mapping.csv")
    ig_config_path = Path("config/instagram_scoring.json")

    # Validate inputs
    if not mapping_path.exists():
        print(f"ERROR: {mapping_path} not found", file=sys.stderr)
        sys.exit(1)

    google_path = run_dir / "filtered" / "google_filtered.json"
    instagram_path = run_dir / "filtered" / "instagram_filtered.json"

    if not google_path.exists() and not instagram_path.exists():
        print(f"ERROR: no filtered JSON files found in {run_dir}/filtered/", file=sys.stderr)
        sys.exit(1)

    # Load mapping
    match_to_key, key_to_display, key_to_desc, key_to_category, key_to_potential = _load_mapping(mapping_path)
    print(f"Loaded {len(match_to_key)} match values from {mapping_path}", file=sys.stderr)

    # Load engagement weights
    weights = _load_engagement_weights(ig_config_path)
    print(f"Engagement weights: {weights}", file=sys.stderr)

    # Load popular post config (optional boost)
    popular_cfg = _load_popular_post_config(ig_config_path)
    if popular_cfg:
        pop_thresholds = popular_cfg.get("thresholds", {})
        pop_mult = popular_cfg.get("weight_multiplier", 1.0)
        print(f"Popular post boost: likes>{pop_thresholds.get('likes')} AND shares>{pop_thresholds.get('shares')} → ×{pop_mult}", file=sys.stderr)
    else:
        pop_thresholds = {}
        pop_mult = 1.0

    # ── data structures ──────────────────────────────────────────────

    # matched[ck][platform] = {
    #     current_volume, record_count, engagement_raw, engagement_details[]
    # }
    matched: dict = defaultdict(
        lambda: defaultdict(
            lambda: {
                "current_volume": 0,
                "record_count": 0,
                "engagement_raw": 0.0,
                "engagement_details": [],
            }
        )
    )

    # matched_terms[ck] = {term_text: {platforms: [...], is_hashtag: bool}}
    matched_terms: dict[str, dict] = defaultdict(
        lambda: defaultdict(
            lambda: {"platforms": [], "is_hashtag": False}
        )
    )

    unmatched: dict[int, dict[str, str]] = {}
    seen_unmatched: set[tuple[str, str]] = set()

    # ── process Google ───────────────────────────────────────────────

    google_file = run_dir / "filtered" / "google_filtered.json"
    if google_file.exists():
        with google_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for rec in data.get("records", []):
            rt = rec.get("raw_term", "")
            if not rt:
                continue
            ct = _clean_term(rt)
            if not ct:
                continue

            ck = match_to_key.get(ct)
            if ck:
                vol = rec.get("current_volume", 0) or 0
                matched[ck]["google"]["current_volume"] += vol
                matched[ck]["google"]["record_count"] += 1

                # Track matched_term (Google terms are never hashtags)
                mt = matched_terms[ck][rt]
                if "google" not in mt["platforms"]:
                    mt["platforms"].append("google")
                mt["is_hashtag"] = False
            else:
                key = (ct, "google")
                if key not in seen_unmatched:
                    seen_unmatched.add(key)
                    unmatched[len(unmatched)] = {
                        "raw_term": rt,
                        "platform": "google",
                        "suggested_cleanup_term": ct,
                    }

        print(f"  Google: processed {len(data.get('records', []))} records", file=sys.stderr)

    # ── process Instagram ────────────────────────────────────────────

    instagram_file = run_dir / "filtered" / "instagram_filtered.json"
    if instagram_file.exists():
        with instagram_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        records = data.get("records", [])
        for rec in records:
            terms_raw = rec.get("terms", [])
            if not terms_raw:
                continue

            # Extract engagement data from raw_payload (once per post)
            rp = rec.get("raw_payload") or {}
            likes = rp.get("likes", 0) or 0
            comments = rp.get("comments", 0) or 0
            shares = rp.get("reshare_count", 0) or 0

            # Compute per-post engagement
            post_eng = _compute_post_engagement(likes, comments, shares, weights)

            # Popular post boost: if post exceeds thresholds, apply weight multiplier
            likes_threshold = pop_thresholds.get("likes", 0)
            shares_threshold = pop_thresholds.get("shares", 0)
            is_popular = (likes > likes_threshold) and (shares > shares_threshold)
            if is_popular:
                post_eng *= pop_mult

            eng_detail = {"likes": likes, "comments": comments, "shares": shares, "popular": is_popular}

            # Track which canonical keys this post contributes to
            post_matched_keys: set[str] = set()

            for term_raw in terms_raw:
                parsed = _parse_term(term_raw)
                if parsed is None:
                    continue
                term_text, source = parsed
                ct = _clean_term(term_text)
                if not ct:
                    continue

                ck = match_to_key.get(ct)
                if ck:
                    vol = rec.get("current_volume", 0) or 0
                    matched[ck]["instagram"]["current_volume"] += vol
                    matched[ck]["instagram"]["record_count"] += 1

                    # Track matched_term
                    mt = matched_terms[ck][term_text]
                    if "instagram" not in mt["platforms"]:
                        mt["platforms"].append("instagram")
                    is_ht = source == "hashtag" or term_text.strip().startswith("#")
                    if is_ht:
                        mt["is_hashtag"] = True

                    post_matched_keys.add(ck)
                else:
                    key = (ct, "instagram")
                    if key not in seen_unmatched:
                        seen_unmatched.add(key)
                        unmatched[len(unmatched)] = {
                            "raw_term": term_text,
                            "platform": "instagram",
                            "suggested_cleanup_term": ct,
                        }

            # Accumulate engagement per canonical key (once per post, per matched key)
            for ck in post_matched_keys:
                matched[ck]["instagram"]["engagement_raw"] += post_eng
                matched[ck]["instagram"]["engagement_details"].append(eng_detail)

        print(f"  Instagram: processed {len(records)} records", file=sys.stderr)

    # ── build matched_groups.json ────────────────────────────────────

    output: dict[str, dict] = {}
    for ck, platforms in matched.items():
        # Flatten platform data
        plat_data: dict[str, dict] = {}
        for plat, pdata in platforms.items():
            entry = {
                "current_volume": pdata["current_volume"],
                "record_count": pdata["record_count"],
            }
            if plat == "instagram":
                entry["engagement_raw"] = round(pdata["engagement_raw"], 2)
                entry["engagement_details"] = pdata["engagement_details"]
            plat_data[plat] = entry

        group: dict = {
            "canonical_key": ck,
            "display_name": key_to_display.get(ck, ck),
            "platforms": plat_data,
            "matched_terms": dict(matched_terms[ck]),
        }
        if ck in key_to_desc:
            group["enriched_description"] = key_to_desc[ck]
        if ck in key_to_category:
            group["category"] = key_to_category[ck]
        output[ck] = group

    matched_path = run_dir / "matched_groups.json"
    _write_json(matched_path, output)
    print(f"  matched_groups.json: {len(output)} keys", file=sys.stderr)

    # ── write unmatched queue ────────────────────────────────────────

    if not skip_unmatched:
        unmatched_path = run_dir / "unmatched_review_queue.csv"
        if unmatched:
            _ensure_dir(unmatched_path)
            with unmatched_path.open("w", encoding="utf-8", newline="") as f:
                fieldnames = [
                    "raw_term", "platform", "suggested_cleanup_term",
                    "review_status", "review_action", "target_canonical_key", "review_note",
                ]
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for row in unmatched.values():
                    w.writerow({
                        **row,
                        "review_status": "pending",
                        "review_action": "",
                        "target_canonical_key": "",
                        "review_note": "",
                    })
            # Ensure trailing newline
            content = unmatched_path.read_text(encoding="utf-8")
            if content and not content.endswith("\n"):
                unmatched_path.write_text(content + "\n", encoding="utf-8")
            print(f"  unmatched_review_queue.csv: {len(unmatched)} terms", file=sys.stderr)
        else:
            _ensure_dir(unmatched_path)
            with unmatched_path.open("w", encoding="utf-8", newline="") as f:
                f.write("raw_term,platform,suggested_cleanup_term,review_status,review_action,target_canonical_key,review_note\n")
            print(f"  unmatched_review_queue.csv: 0 terms (all matched)", file=sys.stderr)
    else:
        print(f"  (skipped unmatched_review_queue.csv)", file=sys.stderr)

    # ── summary ──────────────────────────────────────────────────────

    total_matched = sum(
        sum(p["record_count"] for p in platforms.values())
        for platforms in matched.values()
    )
    keys_with_eng = sum(
        1 for platforms in matched.values()
        if platforms.get("instagram", {}).get("engagement_raw", 0) > 0
    )
    keys_with_mt = sum(1 for ck in output if output[ck].get("matched_terms"))
    print(
        f"Summary: {len(output)} matched keys ({total_matched} records), "
        f"{keys_with_eng} with engagement, {keys_with_mt} with matched_terms, "
        f"{len(unmatched)} unmatched terms",
        file=sys.stderr,
    )


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exact-match normalization for HK F&B trending pipeline"
    )
    parser.add_argument(
        "--date", required=True,
        help="Run date in YYYY-MM-DD format (e.g. 2026-06-25)",
    )
    parser.add_argument(
        "--skip-unmatched", action="store_true",
        help="Skip writing unmatched_review_queue.csv (for Step 4 re-normalize)",
    )
    args = parser.parse_args()
    run(args.date, args.skip_unmatched)


if __name__ == "__main__":
    main()
