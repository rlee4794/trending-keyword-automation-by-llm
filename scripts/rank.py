#!/usr/bin/env python3
"""Step 5 — Ranking: accumulate 14 days, score, compare windows, rank.

Usage:
  python3 scripts/rank.py --date 2026-07-05
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

HKT = timezone(timedelta(hours=8))


def load_config(name: str) -> dict:
    with open(f"config/{name}.json") as f:
        return json.load(f)


def determine_windows(target_date_str: str) -> dict:
    """Compute current/previous week date ranges."""
    T = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    current_week = [(T - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    previous_week = [(T - timedelta(days=i)).isoformat() for i in range(13, 6, -1)]
    return {
        "target_date": target_date_str,
        "current_week_start": current_week[0],
        "current_week_end": current_week[-1],
        "previous_week_start": previous_week[0],
        "previous_week_end": previous_week[-1],
        "all_dates": previous_week + current_week,
    }


def accumulate(all_dates: list[str]) -> dict:
    """Scan 14 days of matched_groups.json, aggregate per window."""
    windows = {
        "current_week": {"days_with_data": 0, "keys": defaultdict(lambda: defaultdict(dict))},
        "previous_week": {"days_with_data": 0, "keys": defaultdict(lambda: defaultdict(dict))},
    }

    for i, date_str in enumerate(all_dates):
        path = f"runs/{date_str}/matched_groups.json"
        if not os.path.exists(path):
            continue

        window = "current_week" if i >= 7 else "previous_week"
        windows[window]["days_with_data"] += 1

        with open(path) as f:
            data = json.load(f)

        for ck, v in data.items():
            wk = windows[window]["keys"][ck]
            wk["display_name"] = v.get("display_name", ck)
            wk["enriched_description"] = v.get("enriched_description", "")
            wk["category"] = v.get("category", "")
            wk["potential"] = v.get("potential", "")

            # Merge matched_terms
            if "matched_terms" not in wk:
                wk["matched_terms"] = {}
            for term, tinfo in v.get("matched_terms", {}).items():
                if term not in wk["matched_terms"]:
                    wk["matched_terms"][term] = {
                        "platforms": [],
                        "is_hashtag": tinfo.get("is_hashtag", False),
                    }
                for p in tinfo.get("platforms", []):
                    if p not in wk["matched_terms"][term]["platforms"]:
                        wk["matched_terms"][term]["platforms"].append(p)

            # Aggregate Instagram
            ig = v.get("platforms", {}).get("instagram", {})
            if ig:
                if "instagram" not in wk:
                    wk["instagram"] = {
                        "current_volume": 0,
                        "record_count": 0,
                        "engagement_raw": 0,
                        "engagement_details": [],
                    }
                wk["instagram"]["current_volume"] += ig.get("current_volume", 0) or 0
                wk["instagram"]["record_count"] += ig.get("record_count", 0) or 0
                wk["instagram"]["engagement_raw"] += ig.get("engagement_raw", 0) or 0
                wk["instagram"]["engagement_details"].extend(ig.get("engagement_details", []))

            # Aggregate Google
            goog = v.get("platforms", {}).get("google", {})
            if goog:
                if "google" not in wk:
                    wk["google"] = {"current_volume": 0, "record_count": 0}
                wk["google"]["current_volume"] += goog.get("current_volume", 0) or 0
                wk["google"]["record_count"] += goog.get("record_count", 0) or 0

    return windows


def score_windows(windows: dict) -> dict:
    """Compute per-window platform scores independently."""
    ranking_cfg = load_config("ranking")
    google_cfg = load_config("google_scoring")
    min_vol_floor = google_cfg.get("min_volume_floor", 50)
    ig_w = ranking_cfg["platform_weights"]["instagram"]
    goog_w = ranking_cfg["platform_weights"]["google"]
    bonus = ranking_cfg["dual_platform_bonus"]
    threshold = ranking_cfg.get("composite_score_threshold", 0.10)

    scores = {}
    for wname in ["current_week", "previous_week"]:
        w = windows[wname]
        days = w["days_with_data"]
        scores[wname] = {}

        if days == 0:
            continue

        # Find global maxes
        max_avg_eng = 0.0
        max_vol = 0.0
        for ck, wk in w["keys"].items():
            ig = wk.get("instagram", {})
            goog = wk.get("google", {})
            posts = ig.get("record_count", 0) or 0
            total_eng = ig.get("engagement_raw", 0) or 0
            avg_eng = total_eng / posts if posts > 0 else 0
            vol = (goog.get("current_volume", 0) or 0) / days
            if avg_eng > max_avg_eng:
                max_avg_eng = avg_eng
            if vol > max_vol:
                max_vol = vol

        # Score each key
        for ck, wk in w["keys"].items():
            ig = wk.get("instagram", {})
            goog = wk.get("google", {})
            posts = ig.get("record_count", 0) or 0
            total_eng = ig.get("engagement_raw", 0) or 0
            avg_eng = total_eng / posts if posts > 0 else 0
            ig_score = (
                math.log(avg_eng + 1) / math.log(max_avg_eng + 1)
                if max_avg_eng > 0 and avg_eng > 0
                else 0
            )

            vol = (goog.get("current_volume", 0) or 0) / days
            if vol < min_vol_floor or max_vol == 0:
                goog_score = 0
            else:
                goog_score = math.log(vol + 1) / math.log(max_vol + 1)

            scores[wname][ck] = {
                "display_name": wk.get("display_name", ck),
                "category": wk.get("category", ""),
                "potential": wk.get("potential", ""),
                "ig_score": round(ig_score, 4),
                "goog_score": round(goog_score, 4),
                "ig_eng_raw": round(avg_eng, 1),
                "goog_vol": round(vol, 1),
                "ig_post_count": posts,
                "matched_terms": wk.get("matched_terms", {}),
                "platforms_with_data": (1 if ig_score > 0 else 0) + (1 if goog_score > 0 else 0),
            }

    return scores


def compute_direction(scores: dict, windows: dict) -> list[dict]:
    """Compare current vs previous week, compute trend direction."""
    ranking_cfg = load_config("ranking")
    surging_abs = ranking_cfg["trend_direction"]["surging"]["min_absolute_delta"]
    surging_rel = ranking_cfg["trend_direction"]["surging"]["min_relative_delta"]
    decl_abs = ranking_cfg["trend_direction"]["declining"]["min_absolute_delta"]
    decl_rel = ranking_cfg["trend_direction"]["declining"]["min_relative_delta"]

    ig_w = ranking_cfg["platform_weights"]["instagram"]
    goog_w = ranking_cfg["platform_weights"]["google"]
    bonus = ranking_cfg["dual_platform_bonus"]

    cw = scores.get("current_week", {})
    pw = scores.get("previous_week", {})
    cw_days = windows["current_week"]["days_with_data"]
    pw_days = windows["previous_week"]["days_with_data"]

    DIR_PRIORITY = {
        "surging": 6, "new": 5, "active": 4,
        "declining": 3, "stable": 2, "insufficient_data": 1,
    }

    def platform_dir(this_s, prev_s):
        if prev_s is None or prev_s == 0:
            return "new"
        delta = this_s - prev_s
        if delta >= surging_abs and delta / prev_s >= surging_rel:
            return "surging"
        elif delta > 0:
            return "active"
        elif delta <= -decl_abs and abs(delta) / prev_s >= decl_rel:
            return "declining"
        else:
            return "stable"

    def select_raw_term(matched_terms, display_name):
        """Select best surface term: most platforms > non-hashtag > display_name."""
        if not matched_terms:
            return display_name
        best = max(
            matched_terms.items(),
            key=lambda t: (
                len(t[1].get("platforms", [])),
                not t[1].get("is_hashtag", False),
            ),
        )
        return best[0]

    results = []
    all_keys = set(cw.keys()) | set(pw.keys())

    for ck in sorted(all_keys):
        cw_score = cw.get(ck, {})
        pw_score = pw.get(ck, {})

        if cw_days < 2 or pw_days < 2:
            direction = ig_dir = goog_dir = "insufficient_data"
        elif not pw_score:
            direction = ig_dir = goog_dir = "new"
        else:
            ig_dir = platform_dir(cw_score.get("ig_score", 0), pw_score.get("ig_score"))
            goog_dir = platform_dir(cw_score.get("goog_score", 0), pw_score.get("goog_score"))
            direction = max(ig_dir, goog_dir, key=lambda d: DIR_PRIORITY[d])

        ig_s = cw_score.get("ig_score", 0)
        goog_s = cw_score.get("goog_score", 0)
        platforms_hit = cw_score.get("platforms_with_data", 0)
        extra = max(0, platforms_hit - 1)
        composite = round(ig_w * ig_s + goog_w * goog_s + bonus * extra, 4)

        display = cw_score.get("display_name", ck) or pw_score.get("display_name", ck)
        raw_term = select_raw_term(cw_score.get("matched_terms", {}), display)

        results.append({
            "canonical_key": ck,
            "display_name": display,
            "raw_representative": raw_term,
            "category": cw_score.get("category", pw_score.get("category", "")),
            "potential": cw_score.get("potential", pw_score.get("potential", "")),
            "social_composite_score": composite,
            "trend_direction": direction,
            "platform_hits": platforms_hit,
            "ig_score": ig_s,
            "goog_score": goog_s,
            "ig_eng_raw": cw_score.get("ig_eng_raw", 0),
            "goog_vol": cw_score.get("goog_vol", 0),
            "ig_post_count": cw_score.get("ig_post_count", 0),
            "prev_ig_score": pw_score.get("ig_score", 0),
            "prev_goog_score": pw_score.get("goog_score", 0),
        })

    return results


def filter_and_rank(results: list[dict], threshold: float = 0.10) -> list[dict]:
    """Filter by composite score, sort, assign rank."""
    filtered = [r for r in results if r["social_composite_score"] >= threshold]
    filtered.sort(key=lambda r: (-r["social_composite_score"], r["display_name"]))
    for i, r in enumerate(filtered):
        r["rank"] = i + 1
    return filtered


def assemble_output(
    ranked: list[dict],
    windows_info: dict,
    generated_at: str,
    run_dir: str,
) -> dict:
    """Build final weekly_fnb_trending.json structure."""
    keywords = []
    for r in ranked:
        keywords.append({
            "canonical_key": r["canonical_key"],
            "display_name": r["display_name"],
            "raw_representative": r["raw_representative"],
            "category": r["category"],
            "potential": r["potential"],
            "social_composite_score": r["social_composite_score"],
            "trend_direction": r["trend_direction"],
            "platform_hits": r["platform_hits"],
            "rank": r["rank"],
            "platforms": {
                "instagram": {
                    "platform_score": r["ig_score"],
                    "engagement_raw": r["ig_eng_raw"],
                    "post_count": r["ig_post_count"],
                    "previous_score": r["prev_ig_score"],
                },
                "google": {
                    "platform_score": r["goog_score"],
                    "volume": r["goog_vol"],
                    "previous_score": r["prev_goog_score"],
                },
            },
        })

    return {
        "schema_version": "3.0",
        "generated_at": generated_at,
        "period": {
            "current_week": {
                "start": f"{windows_info['current_week_start']}T00:00:00+08:00",
                "end": f"{windows_info['current_week_end']}T23:59:59+08:00",
                "days_with_data": windows_info["cw_days"],
            },
            "previous_week": {
                "start": f"{windows_info['previous_week_start']}T00:00:00+08:00",
                "end": f"{windows_info['previous_week_end']}T23:59:59+08:00",
                "days_with_data": windows_info["pw_days"],
            },
        },
        "pipeline": {"mode": "live", "timezone": "Asia/Hong_Kong"},
        "keywords": keywords,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 5: Weekly ranking")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    run_dir = f"runs/{args.date}"
    os.makedirs(run_dir, exist_ok=True)

    # Step 1: Determine windows
    win = determine_windows(args.date)
    print(f"Target: {win['target_date']}", file=sys.stderr)
    print(f"CW: {win['current_week_start']} → {win['current_week_end']}", file=sys.stderr)
    print(f"PW: {win['previous_week_start']} → {win['previous_week_end']}", file=sys.stderr)

    # Step 2: Accumulate
    windows = accumulate(win["all_dates"])
    cw_days = windows["current_week"]["days_with_data"]
    pw_days = windows["previous_week"]["days_with_data"]
    print(f"Accumulated: CW={cw_days} days, {len(windows['current_week']['keys'])} keys; "
          f"PW={pw_days} days, {len(windows['previous_week']['keys'])} keys", file=sys.stderr)

    if cw_days == 0 and pw_days == 0:
        print("ERROR: No matched_groups.json files found in 14-day window", file=sys.stderr)
        sys.exit(1)

    # Step 3: Score
    scores = score_windows(windows)
    for wname in ["current_week", "previous_week"]:
        if scores.get(wname):
            print(f"{wname}: {len(scores[wname])} scored", file=sys.stderr)

    # Step 4: Direction
    results = compute_direction(scores, windows)

    # Step 5: Filter + rank
    ranking_cfg = load_config("ranking")
    threshold = ranking_cfg.get("composite_score_threshold", 0.10)
    ranked = filter_and_rank(results, threshold)

    # Step 6: Assemble
    generated_at = datetime.now(HKT).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    output = assemble_output(
        ranked,
        {
            "current_week_start": win["current_week_start"],
            "current_week_end": win["current_week_end"],
            "previous_week_start": win["previous_week_start"],
            "previous_week_end": win["previous_week_end"],
            "cw_days": cw_days,
            "pw_days": pw_days,
        },
        generated_at,
        run_dir,
    )

    out_path = f"{run_dir}/weekly_fnb_trending.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    # Ensure trailing newline
    content = open(out_path).read()
    if content and not content.endswith("\n"):
        open(out_path, "w").write(content + "\n")

    # Summary
    directions = Counter(r["trend_direction"] for r in ranked)
    if ranked:
        score_range = f"{ranked[-1]['social_composite_score']:.4f} – {ranked[0]['social_composite_score']:.4f}"
    else:
        score_range = "N/A"

    print(f"Wrote {len(ranked)} keywords to {out_path}", file=sys.stderr)
    print(f"Score range: {score_range}, directions: {dict(directions)}", file=sys.stderr)


if __name__ == "__main__":
    main()
