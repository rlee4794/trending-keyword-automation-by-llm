"""Tests for social_pipeline.llm_review."""

from __future__ import annotations

from pathlib import Path

from social_pipeline.llm_review import _append_mappings, _build_prompt


def test_build_prompt_prefers_fnb_concepts_over_district_or_restaurant_terms():
    prompt = _build_prompt(
        [
            {
                "platform": "google",
                "suggested_cleanup_term": "旺角cafe",
                "raw_term": "旺角cafe",
            },
            {
                "platform": "google",
                "suggested_cleanup_term": "火鍋配料",
                "raw_term": "火鍋配料",
            },
            {
                "platform": "instagram",
                "suggested_cleanup_term": "達摩堂",
                "raw_term": "達摩堂",
            },
        ],
        {
            "coffee-shop": "cafe",
            "hotpot": "火鍋",
        },
    )

    assert "portable F&B concepts" in prompt
    assert "Do not create canonical keys that include district names" in prompt
    assert "restaurant names" in prompt
    assert '"旺角cafe" → MERGE target_canonical_key="coffee-shop"' in prompt
    assert '"火鍋配料" → MERGE target_canonical_key="hotpot"' in prompt
    assert '"達摩堂" → DISCARD reason="restaurant name"' in prompt
    assert '"mongkok" → "mong-kok-cafe"' not in prompt


def test_append_mappings_uses_existing_display_term_for_merge(tmp_path: Path):
    mapping = tmp_path / "mapping.csv"
    mapping.write_text(
        "canonical_key,match_value,display_term\n"
        "hotpot,火鍋,火鍋\n",
        encoding="utf-8",
    )

    added = _append_mappings(
        mapping,
        [
            {
                "suggested_cleanup_term": "火鍋配料",
                "action": "MERGE",
                "target_canonical_key": "hotpot",
            }
        ],
        {"hotpot": "火鍋"},
    )

    assert added == 1
    assert "hotpot,火鍋配料,火鍋" in mapping.read_text(encoding="utf-8")