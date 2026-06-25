# Trending Keyword Automation By LLM

## OpenClaw Setup

Use OpenClaw as job runner for this repo. Do not upload whole project on every run if OpenClaw can already access repo checkout.

Primary product loop:

- daily cron job refreshes weekly social-listening result
- when user asks for weekly FnB trending keywords, OpenClaw reads latest result and returns it
- trending and scoring rules stay the same as defined in the implementation plan; only the serving contract is being simplified

### Pipeline flow

Live mode runs the full social-listening pipeline:

```text
Apify fetch → normalize → LLM review → update mapping → re-normalize → ranking
```

Flow details:

- Apify fetches raw platform payloads for Google Trends and Instagram.
- Normalization matches raw terms against `data/mappings/canonical_mapping.csv` and writes an unmatched review queue when needed.
- LLM review classifies unmatched terms as `CREATE`, `MERGE`, or `DISCARD`.
- Accepted `CREATE` and `MERGE` decisions append rows to `data/mappings/canonical_mapping.csv`.
- If the mapping changed, the same raw payloads are normalized again so new mappings affect the current run.
- Ranking scores the normalized keywords and writes the weekly output artifact.

Fixture mode is wiring-only. It uses the existing ranked fixture CSV and does not call Apify, run LLM review, update mappings, re-normalize raw data, or recompute rankings.

### What OpenClaw needs

Required runtime files:

- `pyproject.toml`
- `src/social_pipeline/cli.py`
- `src/social_pipeline/pipeline.py`
- `src/social_pipeline/config.py`
- `src/social_pipeline/apify.py`
- `src/social_pipeline/normalize.py`
- `src/social_pipeline/llm_review.py`
- `src/social_pipeline/ranking.py`
- `config/social_listening_v1.json`
- `config/apify_actors_v1.json`
- `data/mappings/canonical_mapping.csv`

Optional runtime input:

- previous weekly feed JSON, if you want prior output reused for expansion terms and previous-volume comparison

Fixture-only input:

- `examples/social_artifacts/2026-06-22/`

Not needed for live production runs:

- `tests/`
- `docs/`
- sample artifacts under `examples/`
- `.pytest_cache/`

### One-time environment setup

Run once in the repo root:

```powershell
python -m pip install -e .
```

If OpenClaw uses a fixed Python path, use that interpreter instead.

### Fixture mode

Use fixture mode to verify wiring without calling Apify:

```powershell
python -m social_pipeline.cli --config config/social_listening_v1.json --actor-config config/apify_actors_v1.json --mapping data/mappings/canonical_mapping.csv --mode fixture --fixture-dir examples/social_artifacts/2026-06-22 --previous-feed examples/social_artifacts/2026-06-22/social_trending_2026_06_22.csv --output-dir .tmp_openclaw_run --run-at 2026-06-22T09:00:00+08:00
```

### Live mode

Set `APIFY_TOKEN` in OpenClaw secret/env config before live runs. The LLM review step also expects the OpenClaw agent CLI to be available in the runtime environment.

```powershell
python -m social_pipeline.cli --config config/social_listening_v1.json --actor-config config/apify_actors_v1.json --mapping data/mappings/canonical_mapping.csv --mode live --previous-feed runs/latest/weekly_fnb_trending.json --output-dir runs --run-at 2026-06-22T09:00:00+08:00
```

### Current status

Current CLI integration:

- validates required file inputs
- writes `openclaw_job_request.json`
- supports fixture mode from ranked fixture CSV
- supports live mode Apify fetch, raw payload persistence, normalization, LLM review, mapping append, re-normalization, ranking, and weekly JSON output
- auto-resolves the previous weekly feed from the prior dated run directory when `--previous-feed` is omitted and the file exists
- updates `runs/latest` to point at the dated run directory

Known limitations:

- LLM review appends mapping rows but does not update review statuses inside `unmatched_review_queue.csv`
- live LLM review depends on the OpenClaw agent CLI path used by `src/social_pipeline/llm_review.py`
- fixture mode does not exercise the full live pipeline

### Output artifacts

Primary target artifact:

- `runs/latest/weekly_fnb_trending.json`

Dated run output uses `--output-dir/YYYY-MM-DD/`, for example `runs/2026-06-24/`.

Current implemented outputs:

- `weekly_fnb_trending.json`
- `openclaw_job_request.json`
- `raw/google_raw.json` in live mode
- `raw/instagram_raw.json` in live mode
- `unmatched_review_queue.csv` when normalization finds unmatched terms
- LLM review stats in the `weekly_fnb_trending.json` metadata when LLM review runs

`openclaw_job_request.json` records:

- selected mode
- run timestamp
- resolved input paths
- configured actor IDs
- whether `APIFY_TOKEN` was present for live mode
- output directory and previous-feed resolution details
