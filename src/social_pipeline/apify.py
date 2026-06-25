"""Apify actor integration: trigger runs, collect datasets, normalise output."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from apify_client import ApifyClient

from social_pipeline.config import ActorConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_platform_payloads(
    actor_config: ActorConfig,
    seed_snapshot: dict[str, Any],
    windows: dict[str, str],
    apify_token: str,
) -> dict[str, dict[str, Any]]:
    """Trigger Apify actors for each platform and return normalised raw payloads.

    Returns a dict keyed by platform name (e.g. "google", "instagram").
    Each value is the pipeline-normalised raw payload with a ``records`` list.
    """
    client = ApifyClient(apify_token)
    results: dict[str, dict[str, Any]] = {}

    # --- Google Trends ---
    google_input = _build_google_trends_input(seed_snapshot, windows)
    google_raw = _run_actor(client, actor_config.platforms["google"].actor_id, google_input)
    results["google"] = _normalise_google_trends(google_raw, seed_snapshot, windows)

    # --- Instagram (one run per seed hashtag, then merge) ---
    instagram_seeds: list[str] = seed_snapshot.get("instagram_seeds", [])
    instagram_records: list[dict[str, Any]] = []
    for seed in instagram_seeds:
        hashtag = seed.lstrip("#")
        ig_input = _build_instagram_input(hashtag, seed_snapshot)
        ig_raw = _run_actor(client, actor_config.platforms["instagram"].actor_id, ig_input)
        instagram_records.extend(
            _normalise_instagram_posts(ig_raw, hashtag, seed_snapshot)
        )
    results["instagram"] = {
        "platform": "instagram",
        "run_at": windows.get("current_start", ""),
        "window_current": {
            "start": windows["current_start"],
            "end": windows["current_end"],
        },
        "window_previous": {
            "start": windows["previous_start"],
            "end": windows["previous_end"],
        },
        "seed_context": {
            "broad_seed_group": seed_snapshot.get("broad_seed_group"),
            "expansion_terms": seed_snapshot.get("expansion_terms", []),
        },
        "records": instagram_records,
    }

    return results


# ---------------------------------------------------------------------------
# Actor runner
# ---------------------------------------------------------------------------


def _run_actor(
    client: ApifyClient,
    actor_id: str,
    run_input: dict[str, Any],
    *,
    timeout_secs: int = 300,
) -> list[dict[str, Any]]:
    """Run an Apify actor, wait for completion, and return dataset items."""
    logger.info("Starting actor %s …", actor_id)
    run = client.actor(actor_id).call(
        run_input=run_input,
        wait_duration=timedelta(seconds=timeout_secs),
    )
    if run is None:
        logger.warning("Actor %s returned no run object", actor_id)
        return []
    dataset_id: str = run.default_dataset_id or ""
    if not dataset_id:
        logger.warning("Actor %s returned no defaultDatasetId", actor_id)
        return []
    items = list(client.dataset(dataset_id).iterate_items())
    logger.info("Actor %s finished: %d items collected", actor_id, len(items))
    return items


# ---------------------------------------------------------------------------
# Per-actor input builders
# ---------------------------------------------------------------------------


def _build_google_trends_input(
    seed_snapshot: dict[str, Any],
    windows: dict[str, str],
) -> dict[str, Any]:
    """Build run_input for data_xplorer/google-trends-trending-now.

    Scrapes Google Trends trending searches for HK, category 5 (Food & Drink),
    over the last 24 hours.
    """
    return {
        "categories": ["5"],
        "geo": "HK",
        "hl": "zh-TW",
        "timeframe": "168",
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": [],
            "apifyProxyCountry": "HK",
        },
    }


def _build_instagram_input(
    hashtag: str,
    seed_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Build run_input for breathtaking_anthem/instagram-hashtag-posts-scraper.

    Scrapes top posts for a single hashtag.  Called once per seed hashtag.
    """
    return {
        "hashtag": hashtag,
        "scrape_type": "top",
        "max_items": 200,
    }


# ---------------------------------------------------------------------------
# Per-actor output normalisers  (Apify raw → pipeline raw)
# ---------------------------------------------------------------------------


def _normalise_google_trends(
    raw_items: list[dict[str, Any]],
    seed_snapshot: dict[str, Any],
    windows: dict[str, str],
) -> dict[str, Any]:
    """Convert Google Trends actor output into pipeline-normalised raw format."""
    records: list[dict[str, Any]] = []
    for item in raw_items:
        # The actor returns fields like: title, traffic, relatedQueries, etc.
        # We map to the pipeline's expected schema.
        term = item.get("term") or ""
        current_volume = item.get("trend_volume_raw", 0) or 0

        records.append({
            "raw_term": term,
            "source_kind": "trending_search",
            "current_volume": current_volume,
            "previous_volume": None,  # not available from trending-now; filled by ranking step
            "raw_payload": item,
        })

    return {
        "platform": "google_trends",
        "run_at": windows.get("current_start", ""),
        "window_current": {
            "start": windows["current_start"],
            "end": windows["current_end"],
        },
        "window_previous": {
            "start": windows["previous_start"],
            "end": windows["previous_end"],
        },
        "seed_context": {
            "broad_seed_group": seed_snapshot.get("broad_seed_group"),
            "expansion_terms": seed_snapshot.get("expansion_terms", []),
        },
        "records": records,
    }


def _normalise_instagram_posts(
    raw_items: list[dict[str, Any]],
    hashtag: str,
    seed_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert Instagram hashtag scraper output into pipeline-normalised records.

    Each Apify item has fields like: caption, like_count, comment_count,
    taken_at_timestamp, hashtags, url, reshare_count, etc.
    We count posts as volume and extract co-occurring hashtags from captions.
    """
    records: list[dict[str, Any]] = []
    for item in raw_items:
        caption = item.get("caption") or ""
        likes = item.get("like_count", 0) or 0
        comments = item.get("comment_count", 0) or 0

        records.append({
            "raw_term": f"#{hashtag}",
            "source_kind": "hashtag",
            "current_volume": 1,  # one post = one unit; aggregated by ranking step
            "previous_volume": None,
            "raw_payload": {
                "engagement_hint": _engagement_tier(likes, comments),
                "geo": "HK",
                "likes": likes,
                "comments": comments,
                "taken_at_timestamp": item.get("taken_at_timestamp"),
                "hashtags": item.get("hashtags", []),
                "url": item.get("url"),
                "reshare_count": item.get("reshare_count"),
                "caption_snippet": caption[:200] if caption else "",
            },
        })

    return records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engagement_tier(likes: int, comments: int) -> str:
    score = likes + comments * 2
    if score > 5000:
        return "high"
    if score > 500:
        return "medium"
    return "low"
