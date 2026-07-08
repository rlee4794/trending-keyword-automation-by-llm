#!/usr/bin/env python3
"""Assemble filtered posts + Agent extraction → daily_trending.json.

Reads:
  runs/{date}/filtered/threshold_filtered.json
  Agent extraction JSON (via --extraction-file or --extraction-json)

Writes:
  runs/{date}/daily_trending.json
  runs/latest → symlink to {date}

Includes post-processing guards to catch common LLM extraction errors:
  - Common Chinese function words misidentified as venues/dishes
    (unless the term appears in a location context: 📍, 🗺️, 地址, etc.)

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

# Common Chinese characters that are almost never venue or dish names.
# These are function words, adverbs, conjunctions, pronouns, and
# generic verbs that can appear in any sentence.
#
# Exception: a term in this set may still be a legitimate venue/dish
# if it appears in a location context in the caption (e.g. "📍不" for
# the restaurant named 不 at 北角錦屏街33A號). The guard checks context
# before dropping.
COMMON_CHARS: set[str] = {
    "不", "的", "了", "是", "在", "有", "和", "都", "就", "也",
    "會", "要", "可", "好", "食", "飲", "去", "來", "我", "你",
    "他", "她", "很", "個", "種", "啲", "嘅", "咁", "仲", "未",
    "冇", "無", "係", "喺", "俾", "畀", "令", "將", "但", "只",
    "已", "更", "最", "又", "或", "與", "及",
}

# Location/address markers that indicate a term is being used as a
# venue name rather than a common word.
LOCATION_MARKERS: list[str] = [
    "📍", "🗺️", "地址", "位置", "地舖", "地下",
    "號地舖", "號地下", "號鋪",
]


def _is_in_location_context(term: str, caption: str) -> bool:
    """Check if a term appears near a location/address marker in the caption.

    A single character like '不' could be a real restaurant name
    (北角錦屏街33A號, 📍不) or a common word (不太記得).
    This function checks if the term is used in an address/location context.

    Heuristic: the term must appear within 20 characters AFTER a location
    marker. Real venue usage follows the pattern '📍不，🗺️地址...'
    where the venue name directly follows the marker. False positives
    like '捨不得' in a post that also happens to contain '📍' elsewhere
    are rejected because the term precedes the marker.
    """
    if not term or not caption:
        return False

    for marker in LOCATION_MARKERS:
        marker_pos = caption.find(marker)
        if marker_pos == -1:
            continue
        # Check if term appears within 20 chars after the marker
        after_start = marker_pos + len(marker)
        after_end = min(len(caption), after_start + 20)
        after_text = caption[after_start:after_end]
        if term in after_text:
            return True

    return False


def _guard_extraction(posts: list[dict]) -> tuple[int, int]:
    """Strip invalid extractions from posts.

    A term in COMMON_CHARS is dropped UNLESS it appears in a location
    context in the caption (e.g. '📍不' for a real restaurant).
    Returns (venue_dropped, dish_dropped).
    """
    venue_dropped = 0
    dish_dropped = 0

    for p in posts:
        ext = p.get("extracted")
        if not ext:
            continue

        caption = p.get("caption_snippet", "")

        venues = ext.get("venues", [])
        if venues:
            filtered = []
            for v in venues:
                if v in COMMON_CHARS:
                    if _is_in_location_context(v, caption):
                        # Term appears near a location marker — could be a
                        # real restaurant name (e.g. '📍不')
                        filtered.append(v)
                    else:
                        venue_dropped += 1
                        print(
                            f"⚠️  GUARD: dropped venue='{v}' from post "
                            f"(caption: {caption[:80]}...)",
                            file=sys.stderr,
                        )
                else:
                    filtered.append(v)
            ext["venues"] = filtered

        dishes = ext.get("dishes", [])
        if dishes:
            filtered = []
            for d in dishes:
                if d in COMMON_CHARS:
                    if _is_in_location_context(d, caption):
                        filtered.append(d)
                    else:
                        dish_dropped += 1
                        print(
                            f"⚠️  GUARD: dropped dish='{d}' from post "
                            f"(caption: {caption[:80]}...)",
                            file=sys.stderr,
                        )
                else:
                    filtered.append(d)
            ext["dishes"] = filtered

    return venue_dropped, dish_dropped


def _guard_keywords(keywords: list[dict], posts: list[dict]) -> tuple[list[dict], int]:
    """Remove keywords with invalid terms.

    A keyword in COMMON_CHARS is dropped UNLESS it appears in a
    location context in at least one associated post's caption.
    Returns (filtered_keywords, count_dropped).
    """
    dropped = 0
    valid = []
    for kw in keywords:
        term = kw.get("term", "")
        if term in COMMON_CHARS:
            # Check if this term appears in a location context in any
            # associated post's caption
            in_context = False
            for i in kw.get("post_indices", []):
                if i < len(posts):
                    caption = posts[i].get("caption_snippet", "")
                    if _is_in_location_context(term, caption):
                        in_context = True
                        break
            if not in_context:
                print(
                    f"⚠️  GUARD: dropping common-char keyword '{term}' "
                    f"(type={kw.get('type')}, not in location context)",
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

    # ── Step 2b: Rebuild keyword post_indices from cleaned posts ───
    # After post-level guard removed invalid venues/dishes, the
    # keyword post_indices may be stale. Rebuild them by checking
    # which posts still contain each keyword term in their extracted fields.
    for kw in extraction.get("keywords", []):
        term = kw["term"]
        kw_type = kw.get("type", "")
        new_indices = []
        for i, p in enumerate(posts):
            ext = p.get("extracted", {})
            field = {"dish": "dishes", "venue": "venues", "cuisine": "cuisines"}.get(kw_type, "")
            if field and term in ext.get(field, []):
                new_indices.append(i)
        old_count = len(kw.get("post_indices", []))
        if old_count > 0 and len(new_indices) < old_count:
            print(
                f"🔧  REBUILD: keyword '{term}' post_indices "
                f"{old_count} → {len(new_indices)} (post-level guard cleaned some)",
                file=sys.stderr,
            )
        kw["post_indices"] = new_indices

    # ── Step 3: Guard keywords (needs post_indices, must run BEFORE build) ─
    keywords = extraction.get("keywords", [])
    keywords, kw_dropped = _guard_keywords(keywords, posts)
    if kw_dropped:
        print(
            f"🛡️  GUARD: dropped {kw_dropped} invalid keyword(s)",
            file=sys.stderr,
        )

    # ── Step 4: Build keyword aggregates ────────────────────────────
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
