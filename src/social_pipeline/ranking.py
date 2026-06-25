"""Classify and rank normalised canonical keywords.

Applies per-platform threshold rules (trending / NEW), computes
velocity, composite score, trend direction, and emits a ranked list
matching the weekly_fnb_trending_v1 schema.
"""

from __future__ import annotations

from typing import Any

from social_pipeline.config import PipelineConfig


def _pick_representative_term(
    matched_terms: dict[str, dict[str, Any]],
    display_name: str,
) -> str:
    """Select the best weekly representative social term.

    Rules (in priority order):
    1. Most platforms seen
    2. Prefer non-hashtag form
    3. Fall back to display_name
    """
    if not matched_terms:
        return display_name

    def _sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, int]:
        _cleaned, info = item
        platforms = len(info.get("platforms", set()))
        is_hashtag = info.get("is_hashtag", False)
        # Higher platform count = better; non-hashtag (1) beats hashtag (0)
        return (platforms, 0 if is_hashtag else 1)

    best = max(matched_terms.items(), key=_sort_key)
    return best[1].get("original", display_name)


def _safe_velocity(current: int | float | None, previous: int | float | None) -> float | None:
    """Compute (current - previous) / previous, returning None when undefined."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous


def _classify_platform(
    current_volume: int | None,
    previous_volume: int | None,
    rule: Any,  # PlatformRule
) -> dict[str, bool | float | None]:
    """Apply one platform's threshold rules.

    Returns a dict with pass_trending, pass_new, velocity.
    """
    cur = current_volume or 0
    prev = previous_volume  # keep None as None

    velocity = _safe_velocity(cur, prev)

    # Trending: pass floor (volume + abs_gain) AND pass velocity (rate + abs_gain)
    pass_trending = False
    abs_gain = cur - (prev or 0)
    if cur >= rule.floor_current and abs_gain >= rule.floor_abs_gain:
        if velocity is not None and velocity >= rule.min_velocity and abs_gain >= rule.min_abs_gain:
            pass_trending = True

    # NEW: previous near zero AND current above launch threshold
    pass_new = False
    effective_prev = prev if prev is not None else 0
    if effective_prev <= rule.new_tiny_floor and cur >= rule.new_launch_floor:
        pass_new = True

    return {
        "current_volume": cur,
        "previous_volume": prev,
        "velocity": velocity,
        "passed_trending": pass_trending,
        "is_new": pass_new,
    }


def rank_keywords(
    matched: dict[str, dict[str, Any]],
    config: PipelineConfig,
) -> list[dict[str, Any]]:
    """Rank normalised keywords by social composite score.

    Args:
        matched: {canonical_key → {display_name, platforms: {platform → {current_volume, previous_volume, record_count}}}}
        config: pipeline config with platform rules and weights

    Returns:
        list of keyword dicts conforming to weekly_fnb_trending_v1 schema,
        ordered by social_composite_score descending.
    """
    scored: list[dict[str, Any]] = []

    for canonical_key, data in matched.items():
        platform_results: dict[str, dict[str, Any]] = {}
        composite_score = 0.0
        platform_hits = 0

        for platform_name, rule in config.platforms.items():
            metrics = data.get("platforms", {}).get(platform_name, {})
            cur = metrics.get("current_volume")
            prev = metrics.get("previous_volume")

            result = _classify_platform(cur, prev, rule)
            platform_results[platform_name] = result

            if result["passed_trending"]:
                platform_hits += 1
                vel = result["velocity"] or 0
                composite_score += rule.weight * vel
            elif result["is_new"]:
                platform_hits += 1
                composite_score += rule.weight * 0.2

        # Dual-platform bonus
        if platform_hits >= 2:
            composite_score += config.dual_platform_bonus

        # Trend direction
        velocities = [
            v
            for p in platform_results.values()
            if (v := p.get("velocity")) is not None
        ]
        all_new = all(p.get("is_new") for p in platform_results.values())
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

        # Representative term: pick highest-signal matched surface term
        representative_term = _pick_representative_term(
            data.get("matched_terms", {}),
            data.get("display_name", canonical_key),
        )

        # Inclusion gate: must pass trend rules on at least one platform
        if platform_hits < 1:
            continue

        scored.append({
            "canonical_key": canonical_key,
            "display_name": data.get("display_name", canonical_key),
            "representative_term": representative_term,
            "category": None,
            "social_composite_score": round(composite_score, 4),
            "trend_direction": direction,
            "platform_hits": platform_hits,
            "platforms": platform_results,
        })

    # Sort descending by score, assign rank
    scored.sort(key=lambda k: k["social_composite_score"], reverse=True)
    for idx, keyword in enumerate(scored, start=1):
        keyword["rank"] = idx

    return scored
