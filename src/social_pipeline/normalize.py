"""Normalize raw social platform records into canonical keys.

Reads raw platform payloads and the canonical mapping CSV, applies
deterministic cleanup and exact matching, then emits:

- matched records grouped by canonical_key (for the ranking step)
- unmatched_review_queue.csv (for manual review)
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def load_canonical_mapping(mapping_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Load canonical mapping CSV.

    Returns:
        match_to_key: {match_value → canonical_key}
        key_to_display: {canonical_key → display_term}
    """
    match_to_key: dict[str, str] = {}
    key_to_display: dict[str, str] = {}
    with mapping_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            match_value = (row.get("match_value") or "").strip()
            canonical_key = (row.get("canonical_key") or "").strip()
            display_term = (row.get("display_term") or "").strip()
            if match_value and canonical_key:
                match_to_key[match_value] = canonical_key
                if canonical_key not in key_to_display:
                    key_to_display[canonical_key] = display_term or canonical_key
                elif display_term and key_to_display[canonical_key] == canonical_key:
                    key_to_display[canonical_key] = display_term
    return match_to_key, key_to_display


def _clean_term(raw: str) -> str:
    """Deterministic cleanup: strip leading #, lowercase, trim whitespace."""
    t = raw.strip()
    if t.startswith("#"):
        t = t[1:]
    return t.lower().strip()


def _extract_candidate_terms(record: dict[str, Any], platform: str) -> list[str]:
    """Extract candidate terms from a raw record for canonical matching."""
    if platform == "google":
        # Prefer raw_term; fall back to raw_payload.term (the actual trending query)
        raw_term = record.get("raw_term", "")
        payload_term = (record.get("raw_payload") or {}).get("term", "")
        terms: list[str] = []
        if raw_term:
            terms.append(raw_term)
        if payload_term and payload_term != raw_term:
            terms.append(payload_term)
        return terms

    if platform == "instagram":
        # Each post carries multiple hashtags — all are candidates
        hashtags: list[str] = (record.get("raw_payload") or {}).get("hashtags", [])
        return list(hashtags)

    return []


def normalize_records(
    raw_payloads: dict[str, dict[str, Any]],
    mapping_path: Path,
    output_dir: Path,
) -> tuple[dict[str, dict[str, Any]], Path | None]:
    """Normalize raw platform records into canonical keys.

    For each record across all platforms, extracts candidate terms,
    cleans them, and attempts an exact match against the canonical mapping.

    Args:
        raw_payloads: {platform_name → {records: [...]}} from apify.fetch_platform_payloads
        mapping_path: path to canonical_mapping.csv
        output_dir: directory to write unmatched_review_queue.csv into

    Returns:
        matched: {canonical_key → {display_name, platforms: {platform → {current_volume, records}}}}
        unmatched_path: path to review queue CSV, or None if no unmatched terms
    """
    match_to_key, key_to_display = load_canonical_mapping(mapping_path)

    # matched: canonical_key → {platform → [records]}
    matched_by_key: dict[str, dict[str, list[dict[str, Any]]]] = {}
    # Track which surface terms matched each canonical key, with platform counts
    # matched_terms: canonical_key → {cleaned_term → {"platforms": set, "is_hashtag": bool, "original": str}}
    matched_terms: dict[str, dict[str, dict[str, Any]]] = {}
    unmatched_rows: list[dict[str, str]] = []
    seen_unmatched: set[tuple[str, str]] = set()  # (cleaned_term, platform)

    for platform, payload in raw_payloads.items():
        records = payload.get("records", [])
        for record in records:
            candidate_terms = _extract_candidate_terms(record, platform)
            matched_any = False

            for term in candidate_terms:
                cleaned = _clean_term(term)
                if not cleaned:
                    continue
                canonical_key = match_to_key.get(cleaned)
                if canonical_key:
                    matched_any = True
                    matched_by_key.setdefault(canonical_key, {}).setdefault(
                        platform, []
                    ).append(record)
                    # Track which surface term matched for representative term selection
                    term_info = matched_terms.setdefault(canonical_key, {}).setdefault(
                        cleaned, {"platforms": set(), "is_hashtag": term.startswith("#"), "original": term}
                    )
                    term_info["platforms"].add(platform)

            # Collect unmatched terms (deduplicated per platform)
            if not matched_any:
                for term in candidate_terms:
                    cleaned = _clean_term(term)
                    if not cleaned:
                        continue
                    key = (cleaned, platform)
                    if key not in seen_unmatched:
                        seen_unmatched.add(key)
                        unmatched_rows.append({
                            "raw_term": term,
                            "platform": platform,
                            "suggested_cleanup_term": cleaned,
                            "review_status": "pending",
                            "review_action": "",
                            "target_canonical_key": "",
                            "review_note": "",
                        })

    # Build the matched output: aggregate current_volume per canonical_key per platform
    matched: dict[str, dict[str, Any]] = {}
    for canonical_key, platform_records in matched_by_key.items():
        platforms: dict[str, dict[str, Any]] = {}
        for platform, recs in platform_records.items():
            total_volume = sum(r.get("current_volume", 0) or 0 for r in recs)
            platforms[platform] = {
                "current_volume": total_volume,
                "previous_volume": None,  # filled by ranking step if previous feed available
                "record_count": len(recs),
            }
        matched[canonical_key] = {
            "canonical_key": canonical_key,
            "display_name": key_to_display.get(canonical_key, canonical_key),
            "platforms": platforms,
            "matched_terms": matched_terms.get(canonical_key, {}),
        }

    # Write unmatched review queue
    output_dir.mkdir(parents=True, exist_ok=True)
    unmatched_path: Path | None = None
    if unmatched_rows:
        unmatched_path = output_dir / "unmatched_review_queue.csv"
        fieldnames = [
            "raw_term", "platform", "suggested_cleanup_term",
            "review_status", "review_action", "target_canonical_key", "review_note",
        ]
        with unmatched_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unmatched_rows)

    return matched, unmatched_path
