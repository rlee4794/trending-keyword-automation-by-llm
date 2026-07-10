#!/usr/bin/env python3
"""Assemble filtered posts + Agent extraction → daily_trending_{REGION}.json.

Reads:
  runs/{date}/filtered/{region}/threshold_filtered.json
  Agent extraction JSON (via --extraction-file or --extraction-json)

Writes:
  runs/{date}/daily_trending_{REGION}.json  (e.g. daily_trending_HK.json)

Usage:
  python3 scripts/assemble_output.py --date 2026-07-07 --region hk --extraction-file /tmp/ext.json
  python3 scripts/assemble_output.py --date 2026-07-07 --region tw --extraction-json '{"posts": [...], "keywords": [...]}'
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HKT = timezone(timedelta(hours=8))

REGION_LABEL: dict[str, str] = {"hk": "HK", "tw": "TW"}

# Common Chinese characters that are almost never venue or dish names.
COMMON_CHARS: set[str] = {
    "不", "的", "了", "是", "在", "有", "和", "都", "就", "也",
    "會", "要", "可", "好", "食", "飲", "去", "來", "我", "你",
    "他", "她", "很", "個", "種", "啲", "嘅", "咁", "仲", "未",
    "冇", "無", "係", "喺", "俾", "畀", "令", "將", "但", "只",
    "已", "更", "最", "又", "或", "與", "及",
}

LOCATION_MARKERS: list[str] = [
    "📍", "🗺️", "地址", "位置", "地舖", "地下",
    "號地舖", "號地下", "號鋪",
]

VENUE_PRECEDING_WORDS: list[str] = [
    "餐廳", "食店", "串燒店", "小店", "店", "鋪", "舖",
    "咖啡店", "茶餐廳", "酒樓", "名店", "大排檔", "冰室",
    "麵店", "麵檔", "燒味店", "甜品店", "糖水鋪",
    "居酒屋", "酒吧", "cafe", "bistro", "bar",
]

QUOTE_PAIRS: list[tuple[str, str]] = [
    ("「", "」"),
    ("『", "』"),
    ('"', '"'),
]


def _is_in_location_context(term: str, caption: str) -> bool:
    if not term or not caption:
        return False

    for marker in LOCATION_MARKERS:
        marker_pos = caption.find(marker)
        if marker_pos == -1:
            continue
        after_start = marker_pos + len(marker)
        after_end = min(len(caption), after_start + 20)
        if term in caption[after_start:after_end]:
            return True

    for open_q, close_q in QUOTE_PAIRS:
        pattern = f"{open_q}{term}{close_q}"
        if pattern in caption:
            return True
        idx = 0
        while True:
            pos = caption.find(open_q, idx)
            if pos == -1:
                break
            after_open = pos + len(open_q)
            if caption[after_open:after_open + len(term)] == term:
                return True
            idx = pos + 1

    for vw in VENUE_PRECEDING_WORDS:
        for open_q, _ in QUOTE_PAIRS:
            combo = f"{vw}{open_q}{term}"
            if combo in caption:
                return True
        vw_pos = caption.find(vw)
        if vw_pos == -1:
            continue
        after_vw = vw_pos + len(vw)
        if after_vw < len(caption) and caption[after_vw] in ('「', '『', '"'):
            after_vw += 1
        if caption[after_vw:after_vw + len(term)] == term:
            after_term = after_vw + len(term)
            if after_term >= len(caption) or not caption[after_term].isalpha():
                return True

    return False


def _guard_extraction(posts: list[dict]) -> tuple[int, int]:
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
                        filtered.append(v)
                    else:
                        venue_dropped += 1
                        print(f"⚠️  GUARD: dropped venue='{v}' (caption: {caption[:80]}...)", file=sys.stderr)
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
                        print(f"⚠️  GUARD: dropped dish='{d}' (caption: {caption[:80]}...)", file=sys.stderr)
                else:
                    filtered.append(d)
            ext["dishes"] = filtered

    return venue_dropped, dish_dropped


def _guard_keywords(keywords: list[dict], posts: list[dict]) -> tuple[list[dict], int]:
    dropped = 0
    valid = []
    for kw in keywords:
        term = kw.get("term", "")
        if term in COMMON_CHARS:
            in_context = False
            for i in kw.get("post_indices", []):
                if i < len(posts):
                    caption = posts[i].get("caption_snippet", "")
                    if _is_in_location_context(term, caption):
                        in_context = True
                        break
            if not in_context:
                print(f"⚠️  GUARD: dropping common-char keyword '{term}' (type={kw.get('type')})", file=sys.stderr)
                dropped += 1
                continue
        valid.append(kw)
    return valid, dropped


def _load_filtered(date_str: str, region: str) -> tuple[list[dict], list[dict], dict]:
    """Load filtered data for one region.

    Returns (posts, google_trends, thresholds).
    """
    run_dir = Path(f"runs/{date_str}")
    fp = run_dir / "filtered" / region / "threshold_filtered.json"
    if not fp.exists():
        print(f"ERROR: {fp} not found", file=sys.stderr)
        sys.exit(1)

    with fp.open(encoding="utf-8") as f:
        data = json.load(f)

    posts = data.get("posts", [])
    google_terms = data.get("google_trends", [])
    thresholds = data.get("threshold", {})

    return posts, google_terms, thresholds


def run(date_str: str, region: str, extraction: dict) -> None:
    """Assemble final output for one region with guardrails."""
    region_label = REGION_LABEL.get(region, region.upper())
    posts, google_terms, thresholds = _load_filtered(date_str, region)

    if not posts and not google_terms:
        print(f"ERROR: no filtered data for region '{region}'", file=sys.stderr)
        sys.exit(1)

    # ── Step 1: Merge extraction into posts ─────────────────────────
    for pe in extraction.get("posts", []):
        idx = pe["index"]
        if idx < len(posts):
            posts[idx]["extracted"] = {
                "dishes": pe.get("dishes", []),
                "venues": pe.get("venues", []),
                "cuisines": pe.get("cuisines", []),
            }
            if pe.get("geo_by_content") is not None:
                posts[idx]["geo_by_content"] = pe["geo_by_content"]

    # ── Step 1.5: Filter geo_mismatch posts ─────────────────────────
    expected_geo = region.upper()  # "HK" or "TW"
    geo_filtered: list[dict] = []
    geo_dropped = 0
    for p in posts:
        gbc = p.get("geo_by_content")
        if gbc is not None and gbc != expected_geo:
            p["_filtered_reason"] = f"geo_mismatch: expected={expected_geo}, content={gbc}"
            geo_filtered.append(p)
            geo_dropped += 1
    if geo_dropped > 0:
        print(f"🌍  GEO FILTER: {geo_dropped} post(s) filtered (geo_by_content != {expected_geo})", file=sys.stderr)
        for p in geo_filtered:
            cap = (p.get("caption_snippet", "") or "")[:80]
            print(f"   ↳ geo_by_content={p.get('geo_by_content')} | {cap}...", file=sys.stderr)
    posts = [p for p in posts if not p.get("_filtered_reason")]

    # ── Step 2: Post-processing guards ──────────────────────────────
    venue_dropped, dish_dropped = _guard_extraction(posts)
    if venue_dropped or dish_dropped:
        print(f"🛡️  GUARD: stripped {venue_dropped} invalid venue(s), {dish_dropped} invalid dish(es)", file=sys.stderr)

    # ── Step 3: Rebuild keyword post_indices from cleaned posts ─────
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
            print(f"🔧  REBUILD: keyword '{term}' post_indices {old_count} → {len(new_indices)}", file=sys.stderr)
        kw["post_indices"] = new_indices

    # ── Step 4: Guard keywords ──────────────────────────────────────
    keywords = extraction.get("keywords", [])
    keywords, kw_dropped = _guard_keywords(keywords, posts)
    if kw_dropped:
        print(f"🛡️  GUARD: dropped {kw_dropped} invalid keyword(s)", file=sys.stderr)

    # ── Step 5: Build keyword aggregates ────────────────────────────
    for kw in keywords:
        indices = kw.pop("post_indices", [])
        kw["post_count"] = len(indices)
        if indices:
            kw["total_likes"] = sum(posts[i]["likes"] for i in indices if i < len(posts))
            kw["total_comments"] = sum(posts[i]["comments"] for i in indices if i < len(posts))
            kw["total_shares"] = sum(posts[i]["shares"] for i in indices if i < len(posts))
            kw["platforms"] = list(set(posts[i]["platform"] for i in indices if i < len(posts)))
            kw["sources"] = list(set(posts[i]["source"] for i in indices if i < len(posts)))
        else:
            kw["total_likes"] = 0
            kw["total_comments"] = 0
            kw["total_shares"] = 0
            kw["platforms"] = ["google"]
            kw["sources"] = ["google"]

    # ── Step 6: Assemble output ─────────────────────────────────────
    output = {
        "schema_version": "1.0",
        "date": date_str,
        "region": region,
        "generated_at": datetime.now(HKT).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "threshold": thresholds,
        "posts": posts,
        "google_trends": google_terms,
        "keywords": keywords,
    }

    run_dir = Path(f"runs/{date_str}")
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / f"daily_trending_{region_label}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    content = out_path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        out_path.write_text(content + "\n", encoding="utf-8")

    print(
        f"✅ [{region_label}] {len(keywords)} keywords from {len(posts)} posts "
        f"+ {len(google_terms)} Google terms",
        file=sys.stderr,
    )
    print(f"Output: {out_path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble filtered posts + extraction → daily_trending_{REGION}.json"
    )
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--region", required=True, choices=["hk", "tw"], help="Region to process")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--extraction-file", help="Path to Agent extraction JSON")
    group.add_argument("--extraction-json", help="Agent extraction JSON string")
    args = parser.parse_args()

    if args.extraction_file:
        with open(args.extraction_file, encoding="utf-8") as f:
            extraction = json.load(f)
    else:
        extraction = json.loads(args.extraction_json)

    run(args.date, args.region, extraction)


if __name__ == "__main__":
    main()
