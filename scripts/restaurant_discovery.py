#!/usr/bin/env python3
"""
Step R — Restaurant Discovery (on-demand)

Two subcommands:
  --prepare   Read daily_trending_{REGION}.json, format dish keywords
              into a structured prompt for concept distillation.
  --merge     Merge Agent output (restaurant discoveries) back into
              daily_trending_{REGION}.json.
"""

import argparse
import json
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = SKILL_ROOT / "runs"
CONFIG_PATH = SKILL_ROOT / "config" / "threshold.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_daily_trending(date: str, region: str) -> dict:
    """Load daily_trending_{REGION}.json for the given date."""
    region_tag = "HK" if region.lower() == "hk" else "TW"
    path = RUNS_DIR / date / f"daily_trending_{region_tag}.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run the pipeline first.", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def save_daily_trending(date: str, region: str, data: dict):
    """Save updated daily_trending_{REGION}.json."""
    region_tag = "HK" if region.lower() == "hk" else "TW"
    path = RUNS_DIR / date / f"daily_trending_{region_tag}.json"
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Updated: {path}")


def cmd_prepare(args):
    """Format dish keywords into a concept distillation prompt."""
    config = load_config()
    rd_config = config.get("restaurant_discovery", {})
    max_keywords = rd_config.get("max_keywords", 10)

    data = load_daily_trending(args.date, args.region)
    keywords = data.get("keywords", [])

    # Filter dish-only keywords, sort by total_likes desc, take top N
    dish_keywords = [kw for kw in keywords if kw.get("type") == "dish"]
    dish_keywords.sort(key=lambda kw: kw.get("total_likes", 0), reverse=True)
    dish_keywords = dish_keywords[:max_keywords]

    if not dish_keywords:
        print("ERROR: No dish keywords found in daily_trending.", file=sys.stderr)
        sys.exit(1)

    # Build prompt
    lines = []
    for i, kw in enumerate(dish_keywords, 1):
        lines.append(f"### 關鍵詞 {i}")
        lines.append(f"- 關鍵詞：{kw['term']}")
        lines.append(f"- 互動數據：{kw['post_count']} posts, {kw['total_likes']} likes")
        # Derive background from sources
        sources = kw.get("sources", [])
        bg = ", ".join(sources[:3]) if sources else "無背景資訊"
        lines.append(f"- 背景：{bg}")
        lines.append("")

    prompt = "\n".join(lines)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(prompt)

    print(f"Prepared {len(dish_keywords)} dish keywords → {output_path}")
    print(f"Keywords: {', '.join(kw['term'] for kw in dish_keywords)}")


def cmd_merge(args):
    """Merge Agent restaurant discovery output into daily_trending."""
    data = load_daily_trending(args.date, args.region)

    merge_path = Path(args.merge)
    if not merge_path.exists():
        print(f"ERROR: {merge_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(merge_path) as f:
        discoveries = json.load(f)

    if not isinstance(discoveries, list):
        print("ERROR: merge file must contain a JSON array.", file=sys.stderr)
        sys.exit(1)

    # Validate structure
    valid = []
    for d in discoveries:
        if not all(k in d for k in ("concept", "source_keyword", "restaurants")):
            print(f"WARNING: skipping malformed entry: {d.get('concept', '???')}", file=sys.stderr)
            continue
        # Validate restaurants
        valid_restaurants = []
        for r in d.get("restaurants", []):
            if not all(k in r for k in ("name", "url", "description")):
                print(f"WARNING: skipping malformed restaurant in {d['concept']}", file=sys.stderr)
                continue
            # Ensure bo_services exists
            if "bo_services" not in r:
                r["bo_services"] = {}
            valid_restaurants.append(r)
        d["restaurants"] = valid_restaurants
        if valid_restaurants:
            valid.append(d)

    data["restaurant_discoveries"] = valid
    save_daily_trending(args.date, args.region, data)

    total_restaurants = sum(len(d["restaurants"]) for d in valid)
    print(f"Merged {len(valid)} concepts, {total_restaurants} restaurants")


def main():
    parser = argparse.ArgumentParser(description="Step R — Restaurant Discovery")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--region", default="hk", choices=["hk", "tw"], help="Region")
    parser.add_argument("--prepare", action="store_true", help="Format dish keywords prompt")
    parser.add_argument("--merge", type=str, help="Path to Agent output JSON to merge")
    parser.add_argument("--output", type=str, help="Output path for --prepare")

    args = parser.parse_args()

    if args.prepare:
        if not args.output:
            print("ERROR: --output required with --prepare", file=sys.stderr)
            sys.exit(1)
        cmd_prepare(args)
    elif args.merge:
        cmd_merge(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
