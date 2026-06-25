from pathlib import Path

from social_pipeline import cli


def test_cli_main_passes_openclaw_arguments_to_pipeline(monkeypatch, tmp_path: Path):
    captured: dict = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"job_request": tmp_path / "openclaw_job_request.json"}

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        "sys.argv",
        [
            "social_pipeline.cli",
            "--config",
            "config/social_listening_v1.json",
            "--actor-config",
            "config/apify_actors_v1.json",
            "--mapping",
            "examples/social_artifacts/2026-06-22/social_trending_2026_06_22.csv",
            "--mode",
            "fixture",
            "--fixture-dir",
            "examples/social_artifacts/2026-06-22",
            "--previous-feed",
            "examples/social_artifacts/2026-06-22/social_trending_2026_06_22.csv",
            "--output-dir",
            str(tmp_path),
            "--run-at",
            "2026-06-22T09:00:00+08:00",
        ],
    )

    cli.main()

    assert captured["config_path"] == Path("config/social_listening_v1.json")
    assert captured["actor_config_path"] == Path("config/apify_actors_v1.json")
    assert captured["mode"] == "fixture"
    assert captured["fixture_dir"] == Path("examples/social_artifacts/2026-06-22")
    assert captured["run_at_iso"] == "2026-06-22T09:00:00+08:00"


def test_cli_main_prints_primary_weekly_artifact_when_available(monkeypatch, tmp_path: Path, capsys):
    weekly_path = tmp_path / "weekly_fnb_trending.json"

    def fake_run_pipeline(**_: object):
        return {
            "job_request": tmp_path / "openclaw_job_request.json",
            "latest_weekly_json": weekly_path,
        }

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        "sys.argv",
        [
            "social_pipeline.cli",
            "--config",
            "config/social_listening_v1.json",
            "--actor-config",
            "config/apify_actors_v1.json",
            "--mapping",
            "data/mappings/canonical_mapping.csv",
            "--mode",
            "fixture",
            "--fixture-dir",
            "examples/social_artifacts/2026-06-22",
            "--output-dir",
            str(tmp_path),
            "--run-at",
            "2026-06-22T09:00:00+08:00",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == str(weekly_path)
