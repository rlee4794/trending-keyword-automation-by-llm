#!/usr/bin/env python3
"""One-shot backfill: add enriched_description column to canonical_mapping.csv
and generate descriptions for keys that lack them.

Usage:
  # Step 1: Prepare — upgrade CSV schema to 4 columns, output batch files
  python3 scripts/backfill_descriptions.py prepare --mapping data/mappings/canonical_mapping.csv --batch-size 75

  # Step 2: Agent reads each batch file, generates descriptions, writes a
  #          batch_N_results.json per batch (see Agent instructions below).

  # Step 3: Apply — merge all batch_N_results.json back into the CSV
  python3 scripts/backfill_descriptions.py apply --mapping data/mappings/canonical_mapping.csv --results-dir /tmp/backfill_batches/
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


# ── schema upgrade ──────────────────────────────────────────────────────

FIELD_NAMES_3 = ["canonical_key", "match_value", "display_term"]
FIELD_NAMES_4 = ["canonical_key", "match_value", "display_term", "enriched_description"]


def _upgrade_schema(mapping_path: Path) -> bool:
    """Ensure CSV has 4 columns. Returns True if upgrade was needed."""
    with mapping_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        rows = list(reader)

    if existing_fields == FIELD_NAMES_4:
        return False  # already 4 columns

    if existing_fields == FIELD_NAMES_3:
        # Upgrade: add empty enriched_description
        for row in rows:
            row["enriched_description"] = ""
        _write_csv(mapping_path, FIELD_NAMES_4, rows)
        print(f"Upgraded {mapping_path} from 3 to 4 columns ({len(rows)} rows)", file=sys.stderr)
        return True

    print(f"ERROR: unexpected columns in {mapping_path}: {existing_fields}", file=sys.stderr)
    sys.exit(1)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Write CSV with trailing newline."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    # Ensure trailing newline
    content = path.read_text(encoding="utf-8")
    if not content.endswith("\n"):
        path.write_text(content + "\n", encoding="utf-8")


# ── prepare ──────────────────────────────────────────────────────────────

def cmd_prepare(mapping_path: Path, batch_size: int) -> None:
    """Upgrade schema and write batch files for keys needing descriptions."""
    _upgrade_schema(mapping_path)

    # Find keys without description
    with mapping_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    needs_desc = [
        {"canonical_key": r["canonical_key"], "display_term": r["display_term"]}
        for r in rows
        if not (r.get("enriched_description") or "").strip()
    ]

    if not needs_desc:
        print("All keys already have descriptions. Nothing to do.")
        return

    # Write batch files
    out_dir = Path("/tmp/backfill_batches")
    out_dir.mkdir(parents=True, exist_ok=True)

    total_batches = (len(needs_desc) + batch_size - 1) // batch_size
    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(needs_desc))
        batch = needs_desc[start:end]

        batch_path = out_dir / f"batch_{batch_idx + 1:03d}_keys.txt"
        with batch_path.open("w", encoding="utf-8") as f:
            for item in batch:
                f.write(f"{item['canonical_key']} | {item['display_term']}\n")

    print(f"Wrote {total_batches} batch files to {out_dir}/")
    print(f"Total keys needing descriptions: {len(needs_desc)}")
    print()
    print("── Agent instructions ──")
    print("For each batch file, read the keys and generate a one-sentence")
    print("F&B concept description. Write results to batch_NNN_results.json")
    print("in the same directory. Format:")
    print()
    print('  {')
    print('    "results": [')
    print('      {"canonical_key": "sukiyaki",')
    print('       "enriched_description": "Japanese hot pot with thinly sliced beef, common in HK放題 restaurants"},')
    print('      {"canonical_key": "coffee-shop",')
    print('       "enriched_description": "Generic coffee shop/cafe concept in HK, includes 咖啡店 and 茶餐廳-style cafes"}')
    print('    ]')
    print('  }')
    print()
    print("After all batches are done, run:")
    print(f"  python3 scripts/backfill_descriptions.py apply --mapping {mapping_path} --results-dir {out_dir}")


# ── apply ────────────────────────────────────────────────────────────────

def cmd_apply(mapping_path: Path, results_dir: Path) -> None:
    """Merge batch_NNN_results.json files back into the CSV."""
    # Collect all descriptions
    descriptions: dict[str, str] = {}
    result_files = sorted(results_dir.glob("batch_*_results.json"))
    if not result_files:
        print(f"ERROR: no batch_*_results.json files found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    for rf in result_files:
        with rf.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("results", []):
            ck = item.get("canonical_key", "").strip()
            desc = item.get("enriched_description", "").strip()
            if ck and desc:
                descriptions[ck] = desc

    # Apply to CSV
    with mapping_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    updated = 0
    for row in rows:
        ck = row["canonical_key"].strip()
        if ck in descriptions and not (row.get("enriched_description") or "").strip():
            row["enriched_description"] = descriptions[ck]
            updated += 1

    _write_csv(mapping_path, FIELD_NAMES_4, rows)
    print(f"Applied {updated} descriptions from {len(result_files)} result files.")
    print(f"Keys still without description: {sum(1 for r in rows if not (r.get('enriched_description') or '').strip())}")


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill enriched_description in canonical_mapping.csv")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prep = sub.add_parser("prepare", help="Upgrade schema + write batch files")
    p_prep.add_argument("--mapping", required=True, type=Path, help="Path to canonical_mapping.csv")
    p_prep.add_argument("--batch-size", type=int, default=75, help="Keys per batch (default: 75)")

    p_apply = sub.add_parser("apply", help="Merge batch results back into CSV")
    p_apply.add_argument("--mapping", required=True, type=Path, help="Path to canonical_mapping.csv")
    p_apply.add_argument("--results-dir", required=True, type=Path, help="Directory with batch_NNN_results.json files")

    args = parser.parse_args()

    if args.command == "prepare":
        cmd_prepare(args.mapping, args.batch_size)
    elif args.command == "apply":
        cmd_apply(args.mapping, args.results_dir)


if __name__ == "__main__":
    main()
