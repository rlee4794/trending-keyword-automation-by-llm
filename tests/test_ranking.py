"""Tests for social_pipeline.ranking."""

from __future__ import annotations

from typing import Any

import pytest

from social_pipeline.config import PipelineConfig, PlatformRule
from social_pipeline.ranking import (
    _classify_platform,
    _pick_representative_term,
    _safe_velocity,
    rank_keywords,
)


# ---------------------------------------------------------------------------
# _safe_velocity
# ---------------------------------------------------------------------------


def test_safe_velocity_normal():
    assert _safe_velocity(100, 50) == 1.0
    assert _safe_velocity(75, 100) == -0.25


def test_safe_velocity_none_previous():
    assert _safe_velocity(100, None) is None


def test_safe_velocity_zero_previous():
    assert _safe_velocity(100, 0) is None


def test_safe_velocity_none_current():
    assert _safe_velocity(None, 50) is None


# ---------------------------------------------------------------------------
# _classify_platform
# ---------------------------------------------------------------------------


def _make_rule(**overrides: Any) -> PlatformRule:
    defaults = {
        "weight": 0.4,
        "floor_current": 35,
        "floor_abs_gain": 20,
        "min_velocity": 0.4,
        "min_abs_gain": 15,
        "new_tiny_floor": 0,
        "new_launch_floor": 35,
    }
    defaults.update(overrides)
    return PlatformRule(**defaults)


def test_classify_passes_trending():
    rule = _make_rule()
    result = _classify_platform(78, 42, rule)
    assert result["passed_trending"] is True
    assert result["is_new"] is False
    assert result["velocity"] == pytest.approx(0.8571, abs=1e-4)


def test_classify_fails_below_floor():
    rule = _make_rule()
    result = _classify_platform(20, 15, rule)
    assert result["passed_trending"] is False


def test_classify_fails_below_floor_abs_gain():
    """Keyword passes volume floor but not the absolute gain floor."""
    rule = _make_rule(floor_current=35, floor_abs_gain=20)
    # cur=50 >= 35, but abs_gain=5 < 20
    result = _classify_platform(50, 45, rule)
    assert result["passed_trending"] is False


def test_classify_fails_below_velocity():
    rule = _make_rule()
    result = _classify_platform(78, 70, rule)  # velocity ~0.11, below 0.4
    assert result["passed_trending"] is False


def test_classify_fails_below_velocity_abs_gain():
    """Passes floor (vol + abs_gain) but fails velocity rate."""
    rule = _make_rule(floor_current=35, floor_abs_gain=20, min_velocity=0.4, min_abs_gain=15)
    # cur=78, prev=58 → abs_gain=20 >= 20 (floor OK), velocity=0.345 < 0.4 (fails)
    result = _classify_platform(78, 58, rule)
    assert result["passed_trending"] is False


def test_classify_passes_new():
    rule = _make_rule()
    result = _classify_platform(50, None, rule)  # no previous → effective 0
    assert result["passed_trending"] is False
    assert result["is_new"] is True


def test_classify_new_fails_below_launch_floor():
    rule = _make_rule()
    result = _classify_platform(20, None, rule)  # 20 < launch_floor 35
    assert result["is_new"] is False


def test_classify_new_fails_with_previous_above_tiny():
    rule = _make_rule()
    result = _classify_platform(50, 10, rule)  # previous 10 > tiny_floor 0
    assert result["is_new"] is False


# ---------------------------------------------------------------------------
# _pick_representative_term
# ---------------------------------------------------------------------------


def test_pick_representative_prefers_non_hashtag_on_tie():
    terms = {
        "omakase": {"platforms": {"google"}, "is_hashtag": False, "original": "omakase"},
        "#omakase": {"platforms": {"instagram"}, "is_hashtag": True, "original": "#omakase"},
    }
    assert _pick_representative_term(terms, "Omakase") == "omakase"


def test_pick_representative_prefers_more_platforms():
    terms = {
        "sukiyaki": {"platforms": {"google"}, "is_hashtag": False, "original": "sukiyaki"},
        "#sukiyaki": {"platforms": {"google", "instagram"}, "is_hashtag": True, "original": "#sukiyaki"},
    }
    assert _pick_representative_term(terms, "Sukiyaki") == "#sukiyaki"


def test_pick_representative_falls_back_to_display_name():
    assert _pick_representative_term({}, "display_name") == "display_name"


# ---------------------------------------------------------------------------
# rank_keywords
# ---------------------------------------------------------------------------


def _make_config(**overrides: Any) -> PipelineConfig:
    defaults = {
        "timezone": "Asia/Hong_Kong",
        "expansion_top_n": 20,
        "dual_platform_bonus": 0.1,
        "platforms": {
            "google": PlatformRule(weight=0.4, floor_current=35, floor_abs_gain=20, min_velocity=0.4, min_abs_gain=15, new_tiny_floor=0, new_launch_floor=35),
            "instagram": PlatformRule(weight=0.6, floor_current=40, floor_abs_gain=0, min_velocity=0.5, min_abs_gain=0, new_tiny_floor=0, new_launch_floor=40),
        },
        "broad_seeds": {"google": [], "instagram": []},
    }
    defaults.update(overrides)
    return PipelineConfig(**defaults)


def test_rank_keywords_sorts_by_score_descending():
    config = _make_config()
    matched = {
        "omakase": {
            "canonical_key": "omakase",
            "display_name": "Omakase",
            "platforms": {
                "google": {"current_volume": 78, "previous_volume": 42, "record_count": 1},
                "instagram": {"current_volume": 50, "previous_volume": 30, "record_count": 50},
            },
            "matched_terms": {},
        },
        "sukiyaki": {
            "canonical_key": "sukiyaki",
            "display_name": "Sukiyaki",
            "platforms": {
                "google": {"current_volume": 60, "previous_volume": 35, "record_count": 1},
            },
            "matched_terms": {},
        },
    }
    keywords = rank_keywords(matched, config)

    assert len(keywords) == 2
    assert keywords[0]["rank"] == 1
    assert keywords[1]["rank"] == 2
    assert keywords[0]["social_composite_score"] > keywords[1]["social_composite_score"]


def test_rank_keywords_applies_dual_platform_bonus():
    config = _make_config()
    matched = {
        "omakase": {
            "canonical_key": "omakase",
            "display_name": "Omakase",
            "platforms": {
                "google": {"current_volume": 78, "previous_volume": 42, "record_count": 1},
                "instagram": {"current_volume": 50, "previous_volume": 30, "record_count": 50},
            },
            "matched_terms": {},
        },
    }
    keywords = rank_keywords(matched, config)
    kw = keywords[0]

    # Google vel = (78-42)/42 = 0.8571, score = 0.4 * 0.8571 = 0.3429
    # Instagram vel = (50-30)/30 = 0.6667, score = 0.6 * 0.6667 = 0.4
    # Dual bonus = 0.1
    # Total ≈ 0.8429
    assert kw["platform_hits"] == 2
    assert kw["social_composite_score"] == pytest.approx(0.8429, abs=0.01)


def test_rank_keywords_handles_new_keywords():
    config = _make_config()
    matched = {
        "new-item": {
            "canonical_key": "new-item",
            "display_name": "New Item",
            "platforms": {
                "google": {"current_volume": 50, "previous_volume": None, "record_count": 1},
                "instagram": {"current_volume": 50, "previous_volume": None, "record_count": 50},
            },
            "matched_terms": {},
        },
    }
    keywords = rank_keywords(matched, config)
    kw = keywords[0]

    assert kw["trend_direction"] == "new"
    assert kw["platform_hits"] == 2
    # Each NEW platform: weight * 0.2 → 0.4*0.2 + 0.6*0.2 + 0.1 bonus = 0.3
    assert kw["social_composite_score"] == pytest.approx(0.3, abs=0.01)


def test_rank_keywords_trend_direction_up():
    config = _make_config()
    matched = {
        "up-item": {
            "canonical_key": "up-item",
            "display_name": "Up Item",
            "platforms": {
                "google": {"current_volume": 78, "previous_volume": 42, "record_count": 1},
            },
            "matched_terms": {},
        },
    }
    keywords = rank_keywords(matched, config)
    assert keywords[0]["trend_direction"] == "up"


def test_rank_keywords_trend_direction_down():
    """Passes Google but Instagram is crashing hard → overall down."""
    config = _make_config()
    matched = {
        "down-item": {
            "canonical_key": "down-item",
            "display_name": "Down Item",
            "platforms": {
                "google": {"current_volume": 60, "previous_volume": 40, "record_count": 1},
                "instagram": {"current_volume": 5, "previous_volume": 500, "record_count": 5},
            },
            "matched_terms": {},
        },
    }
    keywords = rank_keywords(matched, config)
    assert len(keywords) == 1
    # Google vel=0.5, Instagram vel=-0.99, avg=-0.245 → down
    assert keywords[0]["trend_direction"] == "down"


def test_rank_keywords_trend_direction_stable():
    """Google passes but Instagram flat → average velocity in stable range."""
    config = _make_config()
    matched = {
        "stable-item": {
            "canonical_key": "stable-item",
            "display_name": "Stable Item",
            "platforms": {
                # Google: vel=0.5 (passes), Instagram: vel=-0.3 (doesn't pass, has velocity)
                # avg = 0.1 → stable
                "google": {"current_volume": 60, "previous_volume": 40, "record_count": 1},
                "instagram": {"current_volume": 35, "previous_volume": 50, "record_count": 35},
            },
            "matched_terms": {},
        },
    }
    keywords = rank_keywords(matched, config)
    assert len(keywords) == 1
    assert keywords[0]["trend_direction"] == "stable"


def test_rank_keywords_excludes_zero_hits():
    """Keywords with 0 platform hits are excluded from output."""
    config = _make_config()
    matched = {
        "noise": {
            "canonical_key": "noise",
            "display_name": "Noise",
            "platforms": {
                "google": {"current_volume": 20, "previous_volume": 18, "record_count": 1},
            },
            "matched_terms": {},
        },
    }
    keywords = rank_keywords(matched, config)
    assert len(keywords) == 0


def test_rank_keywords_uses_representative_term():
    config = _make_config()
    matched = {
        "omakase": {
            "canonical_key": "omakase",
            "display_name": "Omakase",
            "platforms": {
                "google": {"current_volume": 78, "previous_volume": 42, "record_count": 1},
            },
            "matched_terms": {
                "omakase": {"platforms": {"google"}, "is_hashtag": False, "original": "omakase"},
                "#omakase": {"platforms": {"instagram"}, "is_hashtag": True, "original": "#omakase"},
            },
        },
    }
    keywords = rank_keywords(matched, config)
    assert keywords[0]["representative_term"] == "omakase"

