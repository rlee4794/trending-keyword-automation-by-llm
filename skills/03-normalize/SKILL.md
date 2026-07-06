---
name: hk-fnb-step-03-normalize
description: >
  Step 3 of the HK F&B trending keyword pipeline.
  Deterministic exact-match normalization against canonical_mapping.csv.
  Groups matched terms, queues unmatched for Step 4 LLM review.
---

# Step 3 — Normalize (Exact Match)

**Pipeline position:** after Step 2B, before Step 4.

## Purpose

Match filtered platform terms against `canonical_mapping.csv` via exact-match lookup.
Zero LLM tokens. Produces matched groups for ranking + unmatched queue for Step 4 review.

## Input

| File | Source | Content |
|------|--------|---------|
| `runs/YYYY-MM-DD/filtered/google_filtered.json` | Step 2B | Filtered Google records |
| `runs/YYYY-MM-DD/filtered/instagram_filtered.json` | Step 2B | Filtered IG records with `terms` field |
| `data/mappings/canonical_mapping.csv` | Project asset | Core mapping table |

## Output

| File | Content |
|------|---------|
| `runs/YYYY-MM-DD/matched_groups.json` | Matched canonical keys with engagement |
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Unmatched terms for Step 4 |

## Output schema

```json
{
  "sukiyaki": {
    "canonical_key": "sukiyaki",
    "display_term": "Sukiyaki",
    "category": "fnb",
    "potential": "high",
    "platforms": {
      "google": { "current_volume": 1000, "record_count": 3 },
      "instagram": {
        "current_volume": 45,
        "record_count": 12,
        "engagement_raw": 142.5,
        "engagement_details": [
          { "likes": 1658, "comments": 35, "shares": 2287 }
        ]
      }
    },
    "matched_terms": {
      "sukiyaki": { "platforms": ["instagram", "google"], "is_hashtag": false }
    }
  }
}
```

`engagement_raw` = sum of per-post engagement scores. Step 5 divides by `record_count`
to get per-post average for scoring.

## Procedure

```bash
# Full mode (Step 3): produces matched_groups.json + unmatched_review_queue.csv
python3 scripts/exact_match.py --date YYYY-MM-DD

# Skip-unmatched mode (Step 4 re-normalize): only update matched_groups.json
python3 scripts/exact_match.py --date YYYY-MM-DD --skip-unmatched
```

`exact_match.py` handles: mapping load, exact-match lookup, engagement computation
(ln(weighted likes/comments/shares + 1)), popular post boost, matched_groups assembly,
unmatched queue generation.

## Error Handling

| Scenario | Action |
|----------|--------|
| Filtered files missing | Abort |
| `canonical_mapping.csv` missing | Abort |
| All terms matched, no unmatched | Queue CSV has header only, Step 4 skips |

## Dependencies

- **Input**: `runs/YYYY-MM-DD/filtered/*` (Step 2B)
- **Asset**: `data/mappings/canonical_mapping.csv`
- **Script**: `scripts/exact_match.py`
- **Output**: `runs/YYYY-MM-DD/matched_groups.json` (Step 5), `runs/YYYY-MM-DD/unmatched_review_queue.csv` (Step 4)
