"""Tests for social_pipeline.normalize."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from social_pipeline.normalize import (
    _clean_term,
    _extract_candidate_terms,
    load_canonical_mapping,
    normalize_records,
)


# ---------------------------------------------------------------------------
# _clean_term
# ---------------------------------------------------------------------------


def test_clean_term_strips_leading_hash():
    assert _clean_term("#hkfood") == "hkfood"
    assert _clean_term("##double") == "#double"


def test_clean_term_lowercases():
    assert _clean_term("Omakase") == "omakase"
    assert _clean_term("#HKFood") == "hkfood"


def test_clean_term_trims_whitespace():
    assert _clean_term("  sukiyaki  ") == "sukiyaki"
    assert _clean_term("\t冷麵\n") == "冷麵"


def test_clean_term_preserves_non_ascii():
    assert _clean_term("壽喜燒") == "壽喜燒"
    assert _clean_term("#香港美食") == "香港美食"


# ---------------------------------------------------------------------------
# _extract_candidate_terms
# ---------------------------------------------------------------------------


def test_extract_google_uses_raw_term_and_payload_term():
    record = {
        "raw_term": "omakase",
        "raw_payload": {"term": "omakase hk"},
    }
    terms = _extract_candidate_terms(record, "google")
    assert "omakase" in terms
    assert "omakase hk" in terms


def test_extract_google_skips_duplicate_payload_term():
    record = {
        "raw_term": "sukiyaki",
        "raw_payload": {"term": "sukiyaki"},
    }
    terms = _extract_candidate_terms(record, "google")
    assert terms == ["sukiyaki"]


def test_extract_google_handles_missing_payload():
    record = {"raw_term": "冷麵", "raw_payload": {}}
    terms = _extract_candidate_terms(record, "google")
    assert terms == ["冷麵"]


def test_extract_instagram_uses_hashtags():
    record = {
        "raw_payload": {"hashtags": ["hkfood", "omakase", "香港美食"]},
    }
    terms = _extract_candidate_terms(record, "instagram")
    assert terms == ["hkfood", "omakase", "香港美食"]


def test_extract_instagram_handles_empty_hashtags():
    record = {"raw_payload": {}}
    terms = _extract_candidate_terms(record, "instagram")
    assert terms == []


# ---------------------------------------------------------------------------
# load_canonical_mapping
# ---------------------------------------------------------------------------


def test_load_canonical_mapping_returns_match_and_display_dicts(tmp_path: Path):
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_text(
        "canonical_key,match_value,display_term\n"
        "sukiyaki,sukiyaki,Sukiyaki\n"
        "omakase,omakase,Omakase\n"
        "leng-mian,冷麵,冷麵\n",
        encoding="utf-8",
    )
    match_to_key, key_to_display = load_canonical_mapping(csv_path)

    assert match_to_key == {
        "sukiyaki": "sukiyaki",
        "omakase": "omakase",
        "冷麵": "leng-mian",
    }
    assert key_to_display == {
        "sukiyaki": "Sukiyaki",
        "omakase": "Omakase",
        "leng-mian": "冷麵",
    }


def test_load_canonical_mapping_prefers_later_non_empty_display_term(tmp_path: Path):
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_text(
        "canonical_key,match_value,display_term\n"
        "hotpot,打邊爐,\n"
        "hotpot,火鍋配料,火鍋\n",
        encoding="utf-8",
    )
    _, key_to_display = load_canonical_mapping(csv_path)

    assert key_to_display["hotpot"] == "火鍋"


def test_load_canonical_mapping_skips_empty_rows(tmp_path: Path):
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_text(
        "canonical_key,match_value,display_term\n"
        "sukiyaki,sukiyaki,Sukiyaki\n"
        ",,\n"
        "omakase,omakase,Omakase\n",
        encoding="utf-8",
    )
    match_to_key, _ = load_canonical_mapping(csv_path)
    assert len(match_to_key) == 2


# ---------------------------------------------------------------------------
# normalize_records
# ---------------------------------------------------------------------------


def _make_mapping_csv(tmp_path: Path) -> Path:
    p = tmp_path / "mapping.csv"
    p.write_text(
        "canonical_key,match_value,display_term\n"
        "sukiyaki,sukiyaki,Sukiyaki\n"
        "omakase,omakase,Omakase\n",
        encoding="utf-8",
    )
    return p


def test_normalize_matches_google_terms(tmp_path: Path):
    mapping = _make_mapping_csv(tmp_path)
    raw = {
        "google": {
            "records": [
                {
                    "raw_term": "omakase",
                    "source_kind": "trending_search",
                    "current_volume": 78,
                    "raw_payload": {"term": "omakase"},
                },
                {
                    "raw_term": "sukiyaki",
                    "source_kind": "trending_search",
                    "current_volume": 55,
                    "raw_payload": {"term": "sukiyaki"},
                },
            ]
        }
    }
    matched, unmatched = normalize_records(raw, mapping, tmp_path / "out")

    assert len(matched) == 2
    assert matched["omakase"]["platforms"]["google"]["current_volume"] == 78
    assert matched["sukiyaki"]["platforms"]["google"]["current_volume"] == 55
    assert unmatched is None


def test_normalize_matches_instagram_hashtags(tmp_path: Path):
    mapping = _make_mapping_csv(tmp_path)
    raw = {
        "instagram": {
            "records": [
                {
                    "raw_term": "#hkfood",
                    "source_kind": "hashtag",
                    "current_volume": 1,
                    "raw_payload": {"hashtags": ["hkfood", "omakase", "香港美食"]},
                },
                {
                    "raw_term": "#hkfoodie",
                    "source_kind": "hashtag",
                    "current_volume": 1,
                    "raw_payload": {"hashtags": ["hkfoodie", "sukiyaki"]},
                },
            ]
        }
    }
    matched, unmatched = normalize_records(raw, mapping, tmp_path / "out")

    assert len(matched) == 2
    assert matched["omakase"]["platforms"]["instagram"]["current_volume"] == 1
    assert matched["sukiyaki"]["platforms"]["instagram"]["current_volume"] == 1


def test_normalize_aggregates_volumes_across_records(tmp_path: Path):
    mapping = _make_mapping_csv(tmp_path)
    raw = {
        "instagram": {
            "records": [
                {
                    "raw_term": "#hkfood",
                    "source_kind": "hashtag",
                    "current_volume": 1,
                    "raw_payload": {"hashtags": ["hkfood", "omakase"]},
                },
                {
                    "raw_term": "#hkfood",
                    "source_kind": "hashtag",
                    "current_volume": 1,
                    "raw_payload": {"hashtags": ["hkfood", "omakase"]},
                },
                {
                    "raw_term": "#hkfood",
                    "source_kind": "hashtag",
                    "current_volume": 1,
                    "raw_payload": {"hashtags": ["hkfood", "omakase"]},
                },
            ]
        }
    }
    matched, _ = normalize_records(raw, mapping, tmp_path / "out")

    assert matched["omakase"]["platforms"]["instagram"]["current_volume"] == 3
    assert matched["omakase"]["platforms"]["instagram"]["record_count"] == 3


def test_normalize_writes_unmatched_queue(tmp_path: Path):
    mapping = _make_mapping_csv(tmp_path)
    raw = {
        "google": {
            "records": [
                {
                    "raw_term": "肯德基",
                    "source_kind": "trending_search",
                    "current_volume": 5000,
                    "raw_payload": {"term": "肯德基"},
                },
            ]
        }
    }
    _, unmatched_path = normalize_records(raw, mapping, tmp_path / "out")

    assert unmatched_path is not None
    assert unmatched_path.exists()
    rows = list(csv.DictReader(unmatched_path.open(encoding="utf-8", newline="")))
    assert len(rows) == 1
    assert rows[0]["raw_term"] == "肯德基"
    assert rows[0]["platform"] == "google"
    assert rows[0]["suggested_cleanup_term"] == "肯德基"
    assert rows[0]["review_status"] == "pending"


def test_normalize_deduplicates_unmatched_terms(tmp_path: Path):
    mapping = _make_mapping_csv(tmp_path)
    raw = {
        "google": {
            "records": [
                {"raw_term": "肯德基", "source_kind": "trending_search", "current_volume": 5000, "raw_payload": {"term": "肯德基"}},
                {"raw_term": "肯德基", "source_kind": "trending_search", "current_volume": 3000, "raw_payload": {"term": "肯德基"}},
            ]
        }
    }
    _, unmatched_path = normalize_records(raw, mapping, tmp_path / "out")
    rows = list(csv.DictReader(unmatched_path.open(encoding="utf-8", newline="")))
    assert len(rows) == 1  # deduplicated


def test_normalize_tracks_matched_terms(tmp_path: Path):
    mapping = _make_mapping_csv(tmp_path)
    raw = {
        "google": {
            "records": [
                {"raw_term": "omakase", "source_kind": "trending_search", "current_volume": 78, "raw_payload": {"term": "omakase"}},
            ]
        },
        "instagram": {
            "records": [
                {"raw_term": "#hkfood", "source_kind": "hashtag", "current_volume": 1, "raw_payload": {"hashtags": ["hkfood", "#omakase"]}},
            ]
        },
    }
    matched, _ = normalize_records(raw, mapping, tmp_path / "out")

    terms = matched["omakase"]["matched_terms"]
    assert "omakase" in terms
    # #omakase cleans to omakase, so it merges into the same entry
    assert terms["omakase"]["platforms"] == {"google", "instagram"}
    assert terms["omakase"]["is_hashtag"] is False  # first-seen (Google) was non-hashtag
