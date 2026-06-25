"""LLM-based pre-filter for Google Trends terms — keep only F&B-related terms."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def _call_openclaw_agent(prompt: str, session_key: str, timeout: int = 60) -> str:
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


def _parse_filter_result(text: str) -> set[str]:
    """Parse LLM response into a set of terms to KEEP."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    data = json.loads(text)
    keep = set()
    for item in data.get("terms", []):
        if item.get("is_fnb"):
            keep.add(item["term"])
    return keep


def filter_google_fnb(
    raw_payload: dict[str, Any],
    batch_size: int = 50,
) -> dict[str, Any]:
    """Filter Google Trends raw payload to keep only F&B-related terms.

    Returns a new payload dict with non-F&B records removed.
    """
    records = raw_payload.get("records", [])
    if not records:
        return raw_payload

    # Build term list for LLM
    terms_list = "\n".join(
        f"  {i + 1}. {r.get('raw_term', '')}"
        for i, r in enumerate(records)
    )

    prompt = f"""You are filtering Google Trends keywords for a Hong Kong F&B (Food & Beverage) trending pipeline.

Your job: classify each term below as F&B-related or not.

## F&B definition:
A term is F&B if it relates to:
- Food, drinks, beverages, cuisine, dishes, ingredients
- Restaurants, cafes, bars, dining formats
- Cooking styles, food culture
- Specific food/drink brands that are primarily F&B (e.g. 肯德基/KFC, 壽司郎, Godiva, 薩莉亞)
- Food delivery, food markets, food streets

A term is NOT F&B if it is:
- Infrastructure, transport (e.g. 港珠澳大橋, bridges, highways)
- TV channels, sports, entertainment (e.g. cctv 5)
- General retail/shopping not food-specific
- Politics, news, weather
- Generic non-food terms

## Terms to classify:
{terms_list}

## Output format:
Return ONLY a JSON object. No markdown, no explanation.

```json
{{
  "terms": [
    {{"term": "肯德基", "is_fnb": true}},
    {{"term": "港珠澳大橋", "is_fnb": false}},
    {{"term": "cctv 5", "is_fnb": false}}
  ]
}}
```

Classify ALL {len(records)} terms."""

    print(f"  [fnb-filter] classifying {len(records)} Google terms ...", file=sys.stderr)
    try:
        response_text = _call_openclaw_agent(prompt, "agent:main:fnb-filter")
        keep_terms = _parse_filter_result(response_text)
        dropped = [r for r in records if r.get("raw_term", "") not in keep_terms]
        kept = [r for r in records if r.get("raw_term", "") in keep_terms]

        for r in dropped:
            print(f"  [fnb-filter] DROP: {r.get('raw_term', '')}", file=sys.stderr)
        for r in kept:
            print(f"  [fnb-filter] KEEP: {r.get('raw_term', '')}", file=sys.stderr)

        print(
            f"  [fnb-filter] kept={len(kept)} dropped={len(dropped)}",
            file=sys.stderr,
        )

        return {
            **raw_payload,
            "records": kept,
            "_fnb_filter": {
                "total": len(records),
                "kept": len(kept),
                "dropped": [r.get("raw_term", "") for r in dropped],
            },
        }
    except Exception as exc:
        print(f"  [fnb-filter] ERROR: {exc}, keeping all terms", file=sys.stderr)
        return raw_payload
