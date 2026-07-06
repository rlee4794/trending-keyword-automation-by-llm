#!/usr/bin/env python3
"""Step 4 helper — manage review queue, filter auto-matched, handle batches, merge, verify.

The LLM classification itself is Agent-driven (step 2c-2e in SKILL.md).
This script handles all the mechanical parts:

  review.py check <run_dir>           — preflight + resume check
  review.py filter <run_dir>          — auto-match pending terms already in mapping
  review.py next-batch <run_dir>      — take next ≤75 pending terms, write batch_terms.txt
  review.py commit-batch <run_dir> <batch_num> '<json>'  — write decisions CSV + update queue
  review.py mark-error <run_dir> <batch_num>  — mark failed batch terms as error
  review.py merge <run_dir>           — merge all batch decisions into canonical_mapping.csv
  review.py verify <run_dir>          — final verification
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────────

def _read_queue(run_dir: str) -> tuple[list[str], list[dict]]:
    path = Path(run_dir) / "unmatched_review_queue.csv"
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    return fieldnames or [], rows


def _write_queue(run_dir: str, fieldnames: list[str], rows: list[dict]) -> None:
    path = Path(run_dir) / "unmatched_review_queue.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    content = path.read_text()
    if content and not content.endswith("\n"):
        path.write_text(content + "\n")


def _load_mapping() -> dict[str, str]:
    """match_value → canonical_key (first-match-wins)."""
    m = {}
    path = Path("data/mappings/canonical_mapping.csv")
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            mv = (row.get("match_value") or "").strip()
            ck = (row.get("canonical_key") or "").strip()
            if mv and mv not in m:
                m[mv] = ck
    return m


def _load_existing_keys() -> dict[str, dict]:
    """canonical_key → {display_term, enriched_description, category, potential}."""
    keys = {}
    path = Path("data/mappings/canonical_mapping.csv")
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            ck = (row.get("canonical_key") or "").strip()
            if ck and ck not in keys:
                keys[ck] = {
                    "display_term": (row.get("display_term") or "").strip(),
                    "enriched_description": (row.get("enriched_description") or "").strip(),
                    "category": (row.get("category") or "").strip(),
                    "potential": (row.get("potential") or "").strip(),
                }
    return keys


# ── commands ─────────────────────────────────────────────────────────────

def cmd_check(run_dir: str) -> None:
    """Preflight + resume check."""
    queue_path = Path(run_dir) / "unmatched_review_queue.csv"
    mapping_path = Path("data/mappings/canonical_mapping.csv")
    prompt_path = Path("skills/04-review/review-prompt.md")

    errors = []
    for p in [queue_path, mapping_path, prompt_path]:
        if not p.exists():
            errors.append(f"MISSING: {p}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    _, rows = _read_queue(run_dir)
    pending = sum(1 for r in rows if r.get("review_status") == "pending")
    done = sum(1 for r in rows if r.get("review_status") == "done")
    auto = sum(1 for r in rows if r.get("review_status") == "auto_matched")
    error = sum(1 for r in rows if r.get("review_status") == "error")
    print(f"pending={pending} done={done} auto_matched={auto} error={error}")
    if pending == 0:
        print("NO_PENDING")


def cmd_filter(run_dir: str) -> None:
    """Auto-match pending terms already covered by mapping."""
    match_to_key = _load_mapping()
    fieldnames, rows = _read_queue(run_dir)

    auto_matched = 0
    for r in rows:
        if r.get("review_status") != "pending":
            continue
        term = (r.get("suggested_cleanup_term") or "").strip()
        if term in match_to_key:
            r["review_status"] = "auto_matched"
            r["review_action"] = "AUTO_MATCHED"
            r["target_canonical_key"] = match_to_key[term]
            auto_matched += 1

    if auto_matched:
        _write_queue(run_dir, fieldnames, rows)

    still_pending = sum(1 for r in rows if r.get("review_status") == "pending")
    print(f"auto_matched={auto_matched} still_pending={still_pending}")


def cmd_next_batch(run_dir: str) -> None:
    """Take next ≤75 pending terms, write batch_terms.txt."""
    _, rows = _read_queue(run_dir)
    pending = [r for r in rows if r.get("review_status") == "pending"]
    batch = pending[:75]

    batch_dir = Path(run_dir) / "batch_decisions"
    batch_dir.mkdir(parents=True, exist_ok=True)

    existing = os.listdir(str(batch_dir))
    nums = [
        int(re.match(r"batch_(\d+)_decisions\.csv", f).group(1))
        for f in existing
        if re.match(r"batch_(\d+)_decisions\.csv", f)
    ]
    batch_num = max(nums) + 1 if nums else 1

    terms_path = batch_dir / f"batch_{batch_num:03d}_terms.txt"
    with terms_path.open("w") as f:
        for r in batch:
            f.write(f"{r['suggested_cleanup_term']} | {r['platform']}\n")

    remaining = len(pending) - len(batch)
    print(f"batch={batch_num} terms={len(batch)} remaining_pending={remaining}")


def cmd_commit_batch(run_dir: str, batch_num: int, json_str: str) -> None:
    """Parse JSON response, write decisions CSV, update queue."""
    data = json.loads(json_str)
    decisions = data.get("decisions", [])

    batch_dir = Path(run_dir) / "batch_decisions"
    out_path = batch_dir / f"batch_{batch_num:03d}_decisions.csv"

    fieldnames = [
        "suggested_cleanup_term", "platform", "action",
        "canonical_key", "display_term", "enriched_description", "category", "potential",
        "target_canonical_key", "reason",
    ]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for d in decisions:
            w.writerow({
                "suggested_cleanup_term": d.get("suggested_cleanup_term", ""),
                "platform": d.get("platform", ""),
                "action": (d.get("action") or "").upper(),
                "canonical_key": d.get("canonical_key", ""),
                "display_term": d.get("display_term", ""),
                "enriched_description": d.get("enriched_description", ""),
                "category": d.get("category", ""),
                "potential": d.get("potential", ""),
                "target_canonical_key": d.get("target_canonical_key", ""),
                "reason": d.get("reason", ""),
            })
    content = out_path.read_text()
    if content and not content.endswith("\n"):
        out_path.write_text(content + "\n")

    # Update queue
    decision_map = {}
    for d in decisions:
        key = (d.get("suggested_cleanup_term", "").strip(), d.get("platform", "").strip())
        decision_map[key] = d

    qfieldnames, rows = _read_queue(run_dir)
    updated = 0
    for r in rows:
        if r.get("review_status") != "pending":
            continue
        key = (r.get("suggested_cleanup_term", "").strip(), r.get("platform", "").strip())
        if key in decision_map:
            d = decision_map[key]
            r["review_status"] = "done"
            r["review_action"] = d.get("action", "")
            r["target_canonical_key"] = d.get("target_canonical_key", d.get("canonical_key", ""))
            r["review_note"] = d.get("reason", "")
            updated += 1

    _write_queue(run_dir, qfieldnames, rows)
    print(f"Wrote {len(decisions)} decisions to {out_path}, updated {updated} queue rows")


def cmd_mark_error(run_dir: str, batch_num: int) -> None:
    """Mark terms from a failed batch as error."""
    batch_dir = Path(run_dir) / "batch_decisions"
    terms_path = batch_dir / f"batch_{batch_num:03d}_terms.txt"

    failed_terms = set()
    with terms_path.open() as f:
        for line in f:
            parts = line.strip().split(" | ")
            if len(parts) >= 2:
                failed_terms.add((parts[0].strip(), parts[1].strip()))

    fieldnames, rows = _read_queue(run_dir)
    updated = 0
    for r in rows:
        if r.get("review_status") != "pending":
            continue
        key = (r.get("suggested_cleanup_term", "").strip(), r.get("platform", "").strip())
        if key in failed_terms:
            r["review_status"] = "error"
            r["review_note"] = "LLM parse failed after retry"
            updated += 1

    _write_queue(run_dir, fieldnames, rows)
    print(f"Marked {updated} rows as error")


def cmd_merge(run_dir: str) -> None:
    """Merge all batch decisions into canonical_mapping.csv."""
    match_to_key = _load_mapping()
    existing_keys = _load_existing_keys()
    mapping_path = Path("data/mappings/canonical_mapping.csv")

    batch_dir = Path(run_dir) / "batch_decisions"
    decisions = []
    for f in sorted(batch_dir.glob("batch_*_decisions.csv")):
        with f.open(newline="") as fh:
            decisions.extend(list(csv.DictReader(fh)))

    # Ensure trailing newline
    content = mapping_path.read_text()
    if content and not content.endswith("\n"):
        mapping_path.write_text(content + "\n")

    added = 0
    conflicts = 0
    with mapping_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "canonical_key", "match_value", "display_term",
            "enriched_description", "category", "potential",
        ])
        for d in decisions:
            action = (d.get("action") or "").upper()
            match_value = (d.get("suggested_cleanup_term") or "").strip()
            if not match_value or match_value in match_to_key:
                continue

            if action == "CREATE":
                canonical_key = (d.get("canonical_key") or "").strip().lower()
                if not canonical_key:
                    continue
                w.writerow({
                    "canonical_key": canonical_key,
                    "match_value": match_value,
                    "display_term": (d.get("display_term") or match_value).strip(),
                    "enriched_description": (d.get("enriched_description") or "").strip(),
                    "category": (d.get("category") or "").strip(),
                    "potential": (d.get("potential") or "").strip(),
                })
                match_to_key[match_value] = canonical_key
                added += 1

            elif action == "MERGE":
                target_key = (d.get("target_canonical_key") or "").strip()
                if not target_key or target_key not in existing_keys:
                    continue
                existing_for_mv = match_to_key.get(match_value)
                if existing_for_mv and existing_for_mv != target_key:
                    print(
                        f"CONFLICT: \"{match_value}\" → MERGE to \"{target_key}\" "
                        f"but already mapped to \"{existing_for_mv}\". SKIPPED.",
                        file=sys.stderr,
                    )
                    conflicts += 1
                    continue
                ek = existing_keys[target_key]
                w.writerow({
                    "canonical_key": target_key,
                    "match_value": match_value,
                    "display_term": ek["display_term"],
                    "enriched_description": ek.get("enriched_description", ""),
                    "category": ek.get("category", ""),
                    "potential": ek.get("potential", ""),
                })
                match_to_key[match_value] = target_key
                added += 1

    # Ensure trailing newline after appending
    content = mapping_path.read_text()
    if content and not content.endswith("\n"):
        mapping_path.write_text(content + "\n")

    created = sum(1 for d in decisions if (d.get("action") or "").upper() == "CREATE")
    merged = sum(1 for d in decisions if (d.get("action") or "").upper() == "MERGE")
    discarded = sum(1 for d in decisions if (d.get("action") or "").upper() == "DISCARD")
    print(f"Merge complete: {created} CREATE, {merged} MERGE, {discarded} DISCARD "
          f"→ {added} rows appended, {conflicts} conflicts skipped")


def cmd_verify(run_dir: str) -> None:
    """Final verification."""
    mg_path = Path(run_dir) / "matched_groups.json"
    with mg_path.open() as f:
        matched = json.load(f)
    print(f"matched_groups.json: {len(matched)} keys")

    _, rows = _read_queue(run_dir)
    statuses: dict[str, int] = {}
    for r in rows:
        s = r.get("review_status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1
    print(f"unmatched_review_queue.csv: {statuses}")

    mapping = _load_mapping()
    print(f"canonical_mapping.csv: {len(mapping)} match_values")

    keys_with_desc = 0
    mp = Path("data/mappings/canonical_mapping.csv")
    with mp.open(newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("enriched_description") or "").strip():
                keys_with_desc += 1
    print(f"  keys with description: {keys_with_desc}/{len(mapping)}")
    print("Step 4 complete.")


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Step 4: LLM Review helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check")
    p.add_argument("run_dir")

    p = sub.add_parser("filter")
    p.add_argument("run_dir")

    p = sub.add_parser("next-batch")
    p.add_argument("run_dir")

    p = sub.add_parser("commit-batch")
    p.add_argument("run_dir")
    p.add_argument("batch_num", type=int)
    p.add_argument("json_str")

    p = sub.add_parser("mark-error")
    p.add_argument("run_dir")
    p.add_argument("batch_num", type=int)

    p = sub.add_parser("merge")
    p.add_argument("run_dir")

    p = sub.add_parser("verify")
    p.add_argument("run_dir")

    args = parser.parse_args()

    if args.cmd == "check":
        cmd_check(args.run_dir)
    elif args.cmd == "filter":
        cmd_filter(args.run_dir)
    elif args.cmd == "next-batch":
        cmd_next_batch(args.run_dir)
    elif args.cmd == "commit-batch":
        cmd_commit_batch(args.run_dir, args.batch_num, args.json_str)
    elif args.cmd == "mark-error":
        cmd_mark_error(args.run_dir, args.batch_num)
    elif args.cmd == "merge":
        cmd_merge(args.run_dir)
    elif args.cmd == "verify":
        cmd_verify(args.run_dir)


if __name__ == "__main__":
    main()
