from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from social_pipeline.apify import fetch_platform_payloads
from social_pipeline.config import load_actor_config, load_config, PipelineConfig
from social_pipeline.fnb_filter import filter_google_fnb
from social_pipeline.llm_review import review_unmatched
from social_pipeline.normalize import normalize_records
from social_pipeline.ranking import rank_keywords


def _require_existing_path(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def _coerce_csv_value(value: str | None) -> object:
    if value is None:
        return None
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value == "":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_fixture_ranked_rows(fixture_dir: Path) -> list[dict[str, object]]:
    ranked_csv = _require_existing_path(
        fixture_dir / "social_trending_2026_06_22.csv",
        "fixture_ranked_csv",
    )
    with ranked_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {key: _coerce_csv_value(value) for key, value in row.items()}
            for row in reader
        ]


def _normalise_keyword_row(
    row: dict[str, object],
    platform_names: list[str],
) -> dict[str, object]:
    """Convert a raw CSV row into the v1 schema keyword object."""
    platforms: dict[str, dict[str, object]] = {}
    for pname in platform_names:
        cur = row.get(f"{pname}_current_volume")
        prev = row.get(f"{pname}_prev_volume")
        vel = row.get(f"{pname}_velocity")
        passed = row.get(f"{pname}_pass_trending")
        is_new = row.get(f"{pname}_pass_new")
        platforms[pname] = {
            "current_volume": cur if cur != "" else None,
            "previous_volume": prev if prev != "" else None,
            "velocity": vel if vel != "" else None,
            "passed_trending": bool(passed) if passed not in (None, "") else False,
            "is_new": bool(is_new) if is_new not in (None, "") else False,
        }

    score = row.get("social_composite_score", 0)
    raw_rank = row.get("social_rank", 0)
    try:
        rank = int(raw_rank) if raw_rank not in (None, "") else 0
    except (ValueError, TypeError):
        rank = 0

    # Derive trend_direction from velocity signs across platforms
    velocities = [
        v
        for pname in platform_names
        if (v := platforms[pname].get("velocity")) is not None
    ]
    all_new = all(platforms[pname].get("is_new") for pname in platform_names)
    if all_new:
        direction = "new"
    elif velocities:
        avg_vel = sum(velocities) / len(velocities)
        if avg_vel > 0.15:
            direction = "up"
        elif avg_vel < -0.10:
            direction = "down"
        else:
            direction = "stable"
    else:
        direction = "stable"

    return {
        "rank": rank,
        "canonical_key": row.get("canonical_key", ""),
        "display_name": row.get("canonical_key", ""),
        "representative_term": row.get("representative_social_term"),
        "category": None,
        "social_composite_score": float(score) if score else 0.0,
        "trend_direction": direction,
        "platform_hits": int(row.get("social_platform_hits", 0)),
        "platforms": platforms,
    }


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _generate_seed_snapshot(
    config: PipelineConfig,
    run_at_iso: str,
    previous_feed_path: Path | None = None,
) -> dict[str, object]:
    """Build a seed snapshot from config for live runs.

    Broad seeds always come from config.  Expansion terms are pulled from
    the previous week's top-N ranked keywords (by social_rank) so that
    previously successful terms get re-scanned without replacing the
    broad discovery surface.
    """
    expansion_terms: list[str] = []
    if previous_feed_path is not None and previous_feed_path.exists():
        try:
            prev_feed = json.loads(previous_feed_path.read_text(encoding="utf-8"))
            prev_keywords: list[dict[str, object]] = prev_feed.get("keywords", [])
            # Sort by rank ascending, take top config.expansion_top_n
            sorted_kw = sorted(
                prev_keywords,
                key=lambda kw: int(kw.get("rank", 999)),
            )
            for kw in sorted_kw[: config.expansion_top_n]:
                rt = kw.get("representative_term") or kw.get("display_name", "")
                if rt:
                    expansion_terms.append(str(rt))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Merge expansion terms into Instagram seeds (add # prefix if missing)
    ig_seeds: list[str] = list(config.broad_seeds.get("instagram", []))
    for term in expansion_terms:
        hashtag = f"#{term}" if not term.startswith("#") else term
        if hashtag not in ig_seeds:
            ig_seeds.append(hashtag)

    return {
        "snapshot_id": f"seed_snapshot_{run_at_iso[:10]}",
        "run_at": run_at_iso,
        "timezone": config.timezone,
        "broad_seed_group": "hk_food_drink_v1",
        "google_trends_seeds": config.broad_seeds.get("google", []),
        "instagram_seeds": ig_seeds,
        "expansion_terms": expansion_terms,
    }


def _compute_windows(run_at_iso: str, tz_name: str) -> dict[str, str]:
    """Compute current and previous weekly windows from run_at."""
    tz = timezone(timedelta(hours=8))  # HKT fixed for now
    run_dt = datetime.fromisoformat(run_at_iso)
    if run_dt.tzinfo is None:
        run_dt = run_dt.replace(tzinfo=tz)
    # Current window: Monday 09:00 of this week → run_at
    days_since_monday = run_dt.weekday()
    current_start = run_dt - timedelta(days=days_since_monday)
    current_start = current_start.replace(hour=9, minute=0, second=0, microsecond=0)
    current_end = run_dt
    # Previous window: prior Monday 09:00 → current_start
    previous_start = current_start - timedelta(days=7)
    previous_end = current_start
    return {
        "current_start": current_start.isoformat(),
        "current_end": current_end.isoformat(),
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "run_date": run_at_iso[:10],  # "2026-06-22"
        "previous_run_date": previous_start.strftime("%Y-%m-%d"),
    }


def _resolve_dated_output_dir(base_dir: Path, run_date: str) -> Path:
    """Return base_dir/YYYY-MM-DD, creating it if needed."""
    dated = base_dir / run_date
    dated.mkdir(parents=True, exist_ok=True)
    return dated


def _update_latest_symlink(base_dir: Path, run_date: str) -> None:
    """Point base_dir/latest → base_dir/YYYY-MM-DD."""
    latest = base_dir / "latest"
    target = Path(run_date)
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(target)


def run_pipeline(
    config_path: Path,
    actor_config_path: Path,
    mapping_path: Path,
    previous_feed_path: Path | None,
    mode: str,
    fixture_dir: Path | None,
    output_dir: Path,
    run_at_iso: str,
) -> dict[str, Path]:
    config_path = _require_existing_path(config_path, "config_path")
    actor_config_path = _require_existing_path(actor_config_path, "actor_config_path")
    mapping_path = _require_existing_path(mapping_path, "mapping_path")

    config = load_config(config_path)
    actor_config = load_actor_config(actor_config_path)
    windows = _compute_windows(run_at_iso, config.timezone)
    run_date = windows["run_date"]
    previous_run_date = windows["previous_run_date"]

    # Resolve output to a dated subdirectory: runs/ → runs/2026-06-22/
    dated_output_dir = _resolve_dated_output_dir(output_dir, run_date)

    # Auto-resolve previous feed from prior week's dated directory
    previous_feed_resolved: Path | None = None
    if previous_feed_path is not None:
        previous_feed_resolved = _require_existing_path(previous_feed_path, "previous_feed_path")
    else:
        # Try runs/YYYY-MM-DD/weekly_fnb_trending.json for the previous Monday
        candidate = output_dir / previous_run_date / "weekly_fnb_trending.json"
        if candidate.exists():
            previous_feed_resolved = candidate

    fixture_dir_resolved = None
    apify_token_present = False
    if mode == "fixture":
        if fixture_dir is None:
            raise ValueError("fixture_dir required when mode='fixture'")
        fixture_dir_resolved = _require_existing_path(fixture_dir, "fixture_dir")
    elif mode == "live":
        apify_token_present = bool(os.environ.get("APIFY_TOKEN"))
        if not apify_token_present:
            raise ValueError("APIFY_TOKEN required when mode='live'")
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    job_request_path = dated_output_dir / "openclaw_job_request.json"
    payload = {
        "mode": mode,
        "run_at": run_at_iso,
        "run_date": run_date,
        "config": {
            "timezone": config.timezone,
            "expansion_top_n": config.expansion_top_n,
            "dual_platform_bonus": config.dual_platform_bonus,
        },
        "actors": {
            platform: spec.actor_id
            for platform, spec in actor_config.platforms.items()
        },
        "paths": {
            "config": str(config_path.resolve()),
            "actor_config": str(actor_config_path.resolve()),
            "mapping": str(mapping_path.resolve()),
            "previous_feed": str(previous_feed_resolved.resolve()) if previous_feed_resolved else None,
            "fixture_dir": str(fixture_dir_resolved.resolve()) if fixture_dir_resolved else None,
            "output_dir": str(dated_output_dir.resolve()),
        },
        "live_env": {
            "apify_token_present": apify_token_present,
        },
    }
    job_request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result: dict[str, Path] = {
        "job_request": job_request_path,
        "output_dir": dated_output_dir,
    }

    if mode == "fixture" and fixture_dir_resolved is not None:
        ranked_rows = _load_fixture_ranked_rows(fixture_dir_resolved)
        platform_names = list(config.platforms.keys())
        normalised_keywords = [
            _normalise_keyword_row(row, platform_names) for row in ranked_rows
        ]
        current_window = {
            "start": windows["current_start"],
            "end": windows["current_end"],
        }
        latest_weekly_json = _write_json(
            dated_output_dir / "weekly_fnb_trending.json",
            {
                "schema_version": "1.0",
                "generated_at": run_at_iso,
                "period": current_window,
                "pipeline": {
                    "mode": mode,
                    "timezone": config.timezone,
                },
                "keywords": normalised_keywords,
                "meta": {
                    "total_candidates": len(ranked_rows),
                    "total_ranked": len(normalised_keywords),
                    "previous_feed_used": previous_feed_resolved is not None,
                },
            },
        )
        result["latest_weekly_json"] = latest_weekly_json

    if mode == "live":
        apify_token = os.environ["APIFY_TOKEN"]
        seed_snapshot = _generate_seed_snapshot(config, run_at_iso, previous_feed_resolved)

        # 1. Fetch raw platform data from Apify
        raw_payloads = fetch_platform_payloads(
            actor_config=actor_config,
            seed_snapshot=seed_snapshot,
            windows=windows,
            apify_token=apify_token,
        )
        # Persist raw payloads
        raw_dir = dated_output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        for platform, payload in raw_payloads.items():
            _write_json(raw_dir / f"{platform}_raw.json", payload)

        # 2. Pre-filter Google Trends to F&B only
        if "google" in raw_payloads:
            raw_payloads["google"] = filter_google_fnb(raw_payloads["google"])
            # Re-persist filtered payload
            _write_json(raw_dir / "google_raw.json", raw_payloads["google"])

        # 3. Normalise raw records → matched + unmatched queue
        matched, unmatched_path = normalize_records(raw_payloads, mapping_path, dated_output_dir)

        # 4. LLM review: auto-classify unmatched terms and expand canonical mapping
        llm_stats = None
        if unmatched_path is not None:
            print("[pipeline] running LLM review on unmatched terms...", file=__import__("sys").stderr)
            llm_stats = review_unmatched(unmatched_path, mapping_path)
            print(
                f"[pipeline] LLM review done: {llm_stats}",
                file=__import__("sys").stderr,
            )
            # Re-normalize with expanded mapping so new entries take effect
            if llm_stats.get("created", 0) + llm_stats.get("merged", 0) > 0:
                print("[pipeline] re-normalizing with expanded mapping...", file=__import__("sys").stderr)
                matched, _ = normalize_records(raw_payloads, mapping_path, dated_output_dir)

        # Inject previous_volume from prior week's feed if available
        if previous_feed_resolved is not None:
            try:
                prev_feed = json.loads(previous_feed_resolved.read_text(encoding="utf-8"))
                prev_keywords = prev_feed.get("keywords", [])
                prev_by_key: dict[str, dict[str, dict[str, Any]]] = {}
                for kw in prev_keywords:
                    ck = kw.get("canonical_key", "")
                    if ck:
                        prev_by_key[ck] = kw.get("platforms", {})
                for ck, data in matched.items():
                    prev_platforms = prev_by_key.get(ck, {})
                    for pname in data.get("platforms", {}):
                        prev_metrics = prev_platforms.get(pname, {})
                        if "current_volume" in prev_metrics:
                            data["platforms"][pname]["previous_volume"] = prev_metrics["current_volume"]
            except (json.JSONDecodeError, KeyError):
                pass

        keywords = rank_keywords(matched, config)
        current_window = {
            "start": windows["current_start"],
            "end": windows["current_end"],
        }
        latest_weekly_json = _write_json(
            dated_output_dir / "weekly_fnb_trending.json",
            {
                "schema_version": "1.0",
                "generated_at": run_at_iso,
                "period": current_window,
                "pipeline": {
                    "mode": mode,
                    "timezone": config.timezone,
                },
                "keywords": keywords,
                "meta": {
                    "total_candidates": sum(
                        len(p.get("records", [])) for p in raw_payloads.values()
                    ),
                    "total_ranked": len(keywords),
                    "previous_feed_used": previous_feed_resolved is not None,
                    "llm_review": llm_stats,
                },
            },
        )
        result["latest_weekly_json"] = latest_weekly_json
        if unmatched_path is not None:
            result["unmatched_review_queue"] = unmatched_path
        if llm_stats is not None:
            result["llm_review_stats"] = llm_stats
        result["raw_payloads"] = {
            platform: raw_dir / f"{platform}_raw.json"
            for platform in raw_payloads
        }

    # Update runs/latest → runs/YYYY-MM-DD symlink
    _update_latest_symlink(output_dir, run_date)

    return result
