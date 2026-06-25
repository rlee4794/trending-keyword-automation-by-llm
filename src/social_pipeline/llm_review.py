"""LLM-powered review of unmatched terms for canonical mapping expansion.

Reads unmatched_review_queue.csv, batches terms, and uses OpenClaw's
agent to classify each term as CREATE, MERGE, or DISCARD. New mappings
are appended to canonical_mapping.csv.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── helpers ──────────────────────────────────────────────────────────────


def _load_existing_keys(mapping_path: Path) -> dict[str, str]:
    """Load existing canonical keys and their display terms."""
    keys: dict[str, str] = {}
    with mapping_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ck = (row.get("canonical_key") or "").strip()
            dt = (row.get("display_term") or "").strip()
            if ck and (ck not in keys or (dt and keys[ck] == ck)):
                keys[ck] = dt or ck
    return keys


def _read_unmatched(unmatched_path: Path) -> list[dict[str, str]]:
    """Read unmatched review queue, returning only pending rows."""
    rows: list[dict[str, str]] = []
    with unmatched_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("review_status") or "").strip() == "pending":
                rows.append(row)
    return rows


def _build_prompt(
    batch: list[dict[str, str]],
    existing_keys: dict[str, str],
) -> str:
    """Build the LLM classification prompt for a batch of unmatched terms."""
    keys_list = "\n".join(
        f"  - {k} ({v})" for k, v in sorted(existing_keys.items())
    )
    terms_list = "\n".join(
        f"  {i + 1}. [{row['platform']}] {row['suggested_cleanup_term']}"
        f" (raw: {row['raw_term']})"
        for i, row in enumerate(batch)
    )

    return f"""You are reviewing unmatched social media terms from a Hong Kong F&B trending keyword pipeline.

Your job: classify each term below into one of three actions.

## Existing canonical keys:
{keys_list}

## Terms to review:
{terms_list}

## Normalization policy:

Canonical keys must represent portable F&B concepts, not locations,
restaurant chains, brands, campaigns, or decorated search phrases.

Before choosing an action, mentally simplify each term:
- remove district/location qualifiers such as 旺角, 尖沙咀, 上環, 沙田, 中環
- remove generic suffixes such as 系列, 必備, 配料, 推介, 推薦, 攻略, 合集
- keep the underlying FnB concept if one remains

## Classification rules:

CREATE — The simplified term is a distinct reusable HK F&B concept (food,
drink, cuisine, dish, ingredient, dining format, cooking style, or generic
restaurant category) AND is NOT a variant of any existing canonical key.
Generate a short English slug as canonical_key (lowercase, hyphens, no special chars).
The display_term should be a clean user-facing F&B concept name, using the most
common Chinese or English form. Remove district names, generic suffixes, and
campaign words from display_term. Do not set display_term to canonical_key unless
that is genuinely the natural public label.

NEVER CREATE canonical keys for:
- Restaurant chains or individual restaurants (e.g. 肯德基/KFC, 薩莉亞/Saizeriya,
  壽司郎/Sushiro, 麥當勞/McDonald's, 美心/Maxim's, 大家樂, 譚仔, etc.)
- Brands or brand names (e.g. Godiva, TCL, Biore, BRUNO)
- Overly generic terms (e.g. 香港美食, hkfood, hongkongfood, food, hk, 美食,
  香港, hongkong, 食好西, 吃貨, foodie, yummy)
- Location-only terms (e.g. 旺角, 中環, 尖沙咀, causewaybay, mongkok)
- Non-F&B terms (e.g. 港珠澳大橋, cctv 5, 手袋維修, 隱形眼鏡, 瑜伽)

MERGE — The term is a variant, translation, alias, district-qualified phrase,
or decorated phrase for an EXISTING canonical key. Set target_canonical_key to
the existing key.
Examples: "旺角cafe" → MERGE target_canonical_key="coffee-shop",
"尖沙咀cafe" → MERGE target_canonical_key="coffee-shop",
"火鍋配料" → MERGE target_canonical_key="hotpot",
"打邊爐必備" → MERGE target_canonical_key="hotpot".

DISCARD — The term is: a restaurant chain/brand, not F&B related, not HK-local,
too generic (e.g. "food", "hk", "lifestyle", "香港美食", "hkfood"),
a district-only term, a brand advertisement, non-food hashtag spam,
campaign text, or garbage text.
Examples: "肯德基" → DISCARD reason="restaurant chain",
"薩莉亞" → DISCARD reason="restaurant chain",
"壽司郎" → DISCARD reason="restaurant chain",
"達摩堂" → DISCARD reason="restaurant name",
"Panos" → DISCARD reason="restaurant name",
"香港美食" → DISCARD reason="too generic",
"hkfood" → DISCARD reason="too generic",
"沙田美食" → DISCARD reason="district-qualified generic food term",
"港珠澳大橋" → DISCARD reason="not F&B",
"cctv 5" → DISCARD reason="not F&B".

## Output format:
Return ONLY a JSON object with a "decisions" array. No markdown, no explanation.

```json
{{
  "decisions": [
    {{"suggested_cleanup_term": "酸辣粉", "action": "CREATE",
      "canonical_key": "hot-sour-noodles", "display_term": "酸辣粉"}},
    {{"suggested_cleanup_term": "旺角cafe", "action": "MERGE",
      "target_canonical_key": "coffee-shop"}},
    {{"suggested_cleanup_term": "肯德基", "action": "DISCARD",
      "reason": "restaurant chain"}},
    {{"suggested_cleanup_term": "cctv 5", "action": "DISCARD",
      "reason": "not F&B"}},
    {{"suggested_cleanup_term": "香港美食", "action": "DISCARD",
      "reason": "too generic"}}
  ]
}}
```

Classify ALL {len(batch)} terms. Return ONLY the JSON."""


def _call_openclaw_agent(prompt: str, session_key: str, timeout: int = 120) -> str:
    """Call OpenClaw agent CLI and return the response text."""
    result = subprocess.run(
        [
            "/usr/bin/openclaw", "agent",
            "--agent", "main",
            "--session-key", session_key,
            "-m", prompt,
            "--json",
            "--thinking", "off",
            "--timeout", str(timeout),
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"openclaw agent failed (rc={result.returncode}): {result.stderr}")

    data = json.loads(result.stdout)
    if data.get("status") != "ok":
        raise RuntimeError(f"openclaw agent returned status={data.get('status')}")

    payloads = data.get("result", {}).get("payloads", [])
    if not payloads:
        raise RuntimeError("openclaw agent returned no payloads")

    return payloads[0].get("text", "")


def _parse_decisions(text: str) -> list[dict[str, str]]:
    """Parse the LLM response text into a list of decision dicts."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    data = json.loads(text)
    return data.get("decisions", [])


def _ensure_trailing_newline(path: Path) -> None:
    """Ensure file ends with exactly one newline."""
    content = path.read_text(encoding="utf-8")
    if not content:
        return
    stripped = content.rstrip("\r\n")
    path.write_text(stripped + "\n", encoding="utf-8")


def _append_mappings(
    mapping_path: Path,
    decisions: list[dict[str, str]],
    existing_keys: dict[str, str],
) -> int:
    """Append new mappings to canonical_mapping.csv. Returns count of rows added."""
    # Read existing match_values to avoid duplicates
    existing_matches: set[str] = set()
    with mapping_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            mv = (row.get("match_value") or "").strip()
            if mv:
                existing_matches.add(mv)

    _ensure_trailing_newline(mapping_path)

    added = 0
    with mapping_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["canonical_key", "match_value", "display_term"],
        )
        for d in decisions:
            action = (d.get("action") or "").upper()
            match_value = (d.get("suggested_cleanup_term") or "").strip()
            if not match_value or match_value in existing_matches:
                continue

            if action == "CREATE":
                canonical_key = (d.get("canonical_key") or "").strip().lower()
                display_term = (d.get("display_term") or match_value).strip()
                if not canonical_key:
                    continue
                writer.writerow({
                    "canonical_key": canonical_key,
                    "match_value": match_value,
                    "display_term": display_term,
                })
                existing_matches.add(match_value)
                added += 1

            elif action == "MERGE":
                target_key = (d.get("target_canonical_key") or "").strip()
                if not target_key or target_key not in existing_keys:
                    continue
                writer.writerow({
                    "canonical_key": target_key,
                    "match_value": match_value,
                    "display_term": existing_keys[target_key],
                })
                existing_matches.add(match_value)
                added += 1

            # DISCARD: intentionally do nothing

    return added


# ── public API ───────────────────────────────────────────────────────────


def review_unmatched(
    unmatched_path: Path,
    mapping_path: Path,
    batch_size: int = 30,
) -> dict[str, Any]:
    """Review unmatched terms via LLM and expand canonical mapping.

    Args:
        unmatched_path: path to unmatched_review_queue.csv
        mapping_path: path to canonical_mapping.csv (will be appended to)
        batch_size: terms per LLM call (default 30)

    Returns:
        dict with stats: created, merged, discarded, errors, batches
    """
    if not unmatched_path.exists():
        return {"created": 0, "merged": 0, "discarded": 0, "errors": 0, "batches": 0}

    rows = _read_unmatched(unmatched_path)
    if not rows:
        return {"created": 0, "merged": 0, "discarded": 0, "errors": 0, "batches": 0}

    existing_keys = _load_existing_keys(mapping_path)
    total_batches = (len(rows) + batch_size - 1) // batch_size

    stats: dict[str, Any] = {
        "created": 0, "merged": 0, "discarded": 0, "errors": 0, "batches": 0,
    }

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        stats["batches"] += 1
        batch_num = stats["batches"]

        try:
            prompt = _build_prompt(batch, existing_keys)
            session_key = f"agent:main:llm-review-{batch_num}"
            response_text = _call_openclaw_agent(prompt, session_key)
            decisions = _parse_decisions(response_text)

            # Count actions
            for d in decisions:
                action = (d.get("action") or "").upper()
                if action == "CREATE":
                    stats["created"] += 1
                elif action == "MERGE":
                    stats["merged"] += 1
                elif action == "DISCARD":
                    stats["discarded"] += 1

            added = _append_mappings(mapping_path, decisions, existing_keys)
            # Refresh existing keys for subsequent MERGE validation
            existing_keys = _load_existing_keys(mapping_path)

            print(
                f"  [llm-review] batch {batch_num}/{total_batches}: "
                f"created={stats['created']} merged={stats['merged']} "
                f"discarded={stats['discarded']} added={added}",
                file=sys.stderr,
            )

        except Exception as exc:
            stats["errors"] += 1
            print(
                f"  [llm-review] batch {batch_num}/{total_batches} ERROR: {exc}",
                file=sys.stderr,
            )

    return stats
