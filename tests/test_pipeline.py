import json
from pathlib import Path

from social_pipeline.pipeline import run_pipeline


def test_run_pipeline_fixture_mode_writes_openclaw_job_request(tmp_path: Path):
    result = run_pipeline(
        config_path=Path("config/social_listening_v1.json"),
        actor_config_path=Path("config/apify_actors_v1.json"),
        mapping_path=Path("examples/social_artifacts/2026-06-22/social_trending_2026_06_22.csv"),
        previous_feed_path=Path("examples/social_artifacts/2026-06-22/social_trending_2026_06_22.csv"),
        mode="fixture",
        fixture_dir=Path("examples/social_artifacts/2026-06-22"),
        output_dir=tmp_path,
        run_at_iso="2026-06-22T09:00:00+08:00",
    )

    job_request = result["job_request"]
    payload = json.loads(job_request.read_text(encoding="utf-8"))

    assert job_request.exists()
    assert payload["mode"] == "fixture"
    assert payload["run_at"] == "2026-06-22T09:00:00+08:00"
    assert payload["config"]["timezone"] == "Asia/Hong_Kong"
    assert payload["actors"]["google"] == "data_xplorer/google-trends-trending-now"
    assert payload["paths"]["fixture_dir"].endswith("examples\\social_artifacts\\2026-06-22")


def test_run_pipeline_fixture_mode_writes_weekly_keyword_artifact(tmp_path: Path):
    result = run_pipeline(
        config_path=Path("config/social_listening_v1.json"),
        actor_config_path=Path("config/apify_actors_v1.json"),
        mapping_path=Path("data/mappings/canonical_mapping.csv"),
        previous_feed_path=Path("examples/social_artifacts/2026-06-22/social_trending_2026_06_22.csv"),
        mode="fixture",
        fixture_dir=Path("examples/social_artifacts/2026-06-22"),
        output_dir=tmp_path,
        run_at_iso="2026-06-22T09:00:00+08:00",
    )

    weekly_json = result["latest_weekly_json"]
    payload = json.loads(weekly_json.read_text(encoding="utf-8"))

    assert weekly_json.exists()
    assert payload["run_at"] == "2026-06-22T09:00:00+08:00"
    assert payload["timezone"] == "Asia/Hong_Kong"
    assert payload["window_current"]["start"] == "2026-06-15T09:00:00+08:00"
    assert len(payload["keywords"]) == 3
    assert payload["keywords"][0]["canonical_key"] == "壽喜燒"
    assert payload["keywords"][0]["representative_social_term"] == "sukiyaki"
    assert payload["keywords"][0]["social_rank"] == 1
    assert payload["keywords"][0]["social_composite_score"] == 0.912
