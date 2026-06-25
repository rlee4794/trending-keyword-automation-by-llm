from __future__ import annotations

import argparse
from pathlib import Path

from social_pipeline.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--actor-config", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--mode", choices=["live", "fixture"], required=True)
    parser.add_argument("--fixture-dir", required=False)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--previous-feed", required=False)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_pipeline(
        config_path=Path(args.config),
        actor_config_path=Path(args.actor_config),
        mapping_path=Path(args.mapping),
        previous_feed_path=Path(args.previous_feed) if args.previous_feed else None,
        mode=args.mode,
        fixture_dir=Path(args.fixture_dir) if args.fixture_dir else None,
        output_dir=Path(args.output_dir),
        run_at_iso=args.run_at,
    )
    print(result.get("latest_weekly_json", result["job_request"]))


if __name__ == "__main__":
    main()
