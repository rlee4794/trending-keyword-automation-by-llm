---
name: hk-fnb-step-03-normalize
description: >
  Step 3 of the HK F&B trending keyword pipeline.
  Performs deterministic exact-match normalization: maps filtered platform
  terms against canonical_mapping.csv and outputs matched groups plus an
  unmatched review queue for Step 4 (LLM Review).
---

# Step 3 — Normalize (Exact Match)

**Pipeline position:** after Step 2B (F&B filter), before Step 4 (LLM Review).

## Purpose

Map every filtered candidate term from Google Trends and Instagram to a stable
`canonical_key` using exact-match lookup against `canonical_mapping.csv`.

Terms that match are grouped by canonical key for ranking.
Terms that don't match are written to `unmatched_review_queue.csv` for
Step 4 (LLM Review) to classify.

This step is **purely deterministic** — zero LLM tokens.

## Input

| File | Source | Content |
|---|---|---|
| `runs/YYYY-MM-DD/filtered/google_filtered.json` | Step 2B | Filtered Google Trends records |
| `runs/YYYY-MM-DD/filtered/instagram_filtered.json` | Step 2B | Filtered Instagram records with `terms` field |
| `data/mappings/canonical_mapping.csv` | Project asset | Core mapping table (4 columns) |

## Output

| File | Content |
|---|---|
| `runs/YYYY-MM-DD/matched_groups.json` | Terms grouped by canonical key, with per-platform volume |
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Terms that failed exact match (→ Step 4) |

### matched_groups.json schema

```json
{
  "sukiyaki": {
    "canonical_key": "sukiyaki",
    "display_name": "Sukiyaki",
    "enriched_description": "Japanese hot pot with thinly sliced beef, common in HK放題 restaurants",
    "category": "fnb",
    "potential": "high",
    "platforms": {
      "google": {"current_volume": 1000, "record_count": 3},
      "instagram": {"current_volume": 45, "record_count": 12, "engagement_raw": 142.5, "engagement_details": [{"likes": 1658, "comments": 35, "shares": 2287}]}
    },
    "matched_terms": {
      "sukiyaki": {"platforms": ["instagram", "google"], "is_hashtag": false},
      "#sukiyaki": {"platforms": ["instagram"], "is_hashtag": true}
    }
  }
}
```

Instagram platform entries include `engagement_raw` (log-normalised weighted sum of likes/comments/shares across all matching posts) and `engagement_details` (per-post breakdown). `matched_terms` tracks which raw surface terms mapped to this canonical key, with source platform and hashtag status — used by Step 5 for raw term selection. `category` and `potential` are pass-throughs from `canonical_mapping.csv`.

### unmatched_review_queue.csv schema

```csv
raw_term,platform,suggested_cleanup_term,review_status,review_action,target_canonical_key,review_note
一粥麵,google,一粥麵,pending,,,
沙嗲拼盤,instagram,沙嗲拼盤,pending,,,
```

## Project Paths

All paths are relative to the project root.

| Path | Purpose |
|---|---|
| `data/mappings/canonical_mapping.csv` | Core mapping table (4 columns: canonical_key, match_value, display_term, enriched_description) |
| `runs/YYYY-MM-DD/filtered/google_filtered.json` | Input: Google Trends filtered payload |
| `runs/YYYY-MM-DD/filtered/instagram_filtered.json` | Input: Instagram filtered payload |
| `runs/YYYY-MM-DD/matched_groups.json` | Output: matched groups for Step 5 (ranking) |
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Output: unmatched terms for Step 4 (LLM Review) |
| `scripts/exact_match.py` | Deterministic exact-match script |

### canonical_mapping.csv schema

```csv
canonical_key,match_value,display_term,enriched_description
sukiyaki,sukiyaki,Sukiyaki,"Japanese hot pot with thinly sliced beef, common in HK放題 restaurants"
leng-mian,冷麵,冷麵,
coffee-shop,旺角cafe,Cafe,"Generic coffee shop/cafe concept in HK"
```

- `canonical_key`: stable slug (lowercase, hyphens)
- `match_value`: cleaned term used for exact-match lookup
- `display_term`: human-facing label
- `enriched_description`: one-sentence F&B concept description (may be empty for legacy keys)

---

## Procedure

### 1. Determine Target Date

Default to **yesterday** (same date as Step 1):

```bash
TARGET_DATE="YYYY-MM-DD"
```

### 2. Run Exact Match

```bash
cd PROJECT_ROOT && python3 scripts/exact_match.py --date "$TARGET_DATE"
```

This script:
1. Reads `canonical_mapping.csv` into a `{match_value → canonical_key}` lookup table.
   **First-match-wins**: if a match_value appears for multiple canonical keys, the
   first occurrence in CSV order wins. Conflicts are printed as WARNING to stderr.
2. Reads `google_filtered.json` and `instagram_filtered.json`
3. Loads engagement weights and popular post boost config from `config/instagram_scoring.json`
4. Extracts candidate terms:
   - **Google:** `raw_term` field from each record
   - **Instagram:** `terms` field from each record (supports both `{"text":"...", "source":"keyword|hashtag"}` objects and legacy plain strings)
5. Cleans each term: strip leading `#`, lowercase, trim whitespace
6. Looks up cleaned term in the lookup table **per term** (not per record)
   - Matched → group by `canonical_key`, sum `current_volume`, compute `engagement_raw` + `engagement_details` (Instagram), track `matched_terms`
   - Unmatched → write to `unmatched_review_queue.csv` with `review_status = pending`
7. **Popular post boost**: posts with `likes > threshold_likes` AND `shares > threshold_shares` (from `instagram_scoring.json`) have their engagement score multiplied by `weight_multiplier`. This rewards viral content without discarding non-viral signal.
8. Writes `matched_groups.json` (with engagement data, matched_terms, and `popular` flag on each engagement_detail) and `unmatched_review_queue.csv`

### 3. Verify Output

```bash
python3 -c "
import json, os, csv

run_dir = 'runs/YYYY-MM-DD'

# Check matched_groups.json
with open(os.path.join(run_dir, 'matched_groups.json')) as f:
    matched = json.load(f)
print(f'matched_groups.json: {len(matched)} keys')

# Check unmatched_review_queue.csv
queue_path = os.path.join(run_dir, 'unmatched_review_queue.csv')
if os.path.exists(queue_path):
    with open(queue_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    pending = sum(1 for r in rows if r.get('review_status') == 'pending')
    print(f'unmatched_review_queue.csv: {len(rows)} total, {pending} pending')
else:
    print('unmatched_review_queue.csv: not found')
"
```

### 4. Determine Next Step

- If `unmatched_review_queue.csv` has **0 pending rows**: all terms matched. Skip Step 4, go directly to Step 5 (ranking).
- If `unmatched_review_queue.csv` has **pending rows**: proceed to Step 4 (LLM Review).

---

## Error Handling

| Scenario | Action |
|---|---|
| `canonical_mapping.csv` missing | Abort. This is a required asset. |
| Both filtered JSON files missing | Abort. Nothing to match. |
| One filtered JSON missing | Continue with available platform. Log warning. |
| `exact_match.py` fails | Abort. Check script output for details. |
| Output directory not writable | Abort. Check permissions. |

---

## Token Budget

| Item | Estimate |
|---|---|
| Shell exec (exact_match.py) | 0 LLM tokens |
| Verification output | ~500 tokens |
| **Total** | **~500 tokens** |

This step is purely Python execution. Agent only verifies results.

---

## Dependencies

- **Input from Step 2B**: `runs/YYYY-MM-DD/filtered/google_filtered.json`, `runs/YYYY-MM-DD/filtered/instagram_filtered.json`
- **Required asset**: `data/mappings/canonical_mapping.csv`
- **Script**: `scripts/exact_match.py`
- **Output to Step 4**: `runs/YYYY-MM-DD/unmatched_review_queue.csv`
- **Output to Step 5**: `runs/YYYY-MM-DD/matched_groups.json` (preliminary; final version produced by Step 4 re-normalize)
