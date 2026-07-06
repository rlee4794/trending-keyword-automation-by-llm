---
name: hk-fnb-step-04-review
description: >
  Step 4 of the HK F&B trending keyword pipeline.
  LLM-powered review of unmatched terms from Step 3.
  Classifies each term as CREATE, MERGE, or DISCARD in batches of 75,
  expands canonical_mapping.csv, then re-normalizes to produce the
  final matched_groups.json for Step 5 (ranking).
---

# Step 4 — LLM Review

**Pipeline position:** after Step 3 (Normalize), before Step 5 (Ranking).

## Purpose

Terms that failed exact-match in Step 3 need semantic classification:
CREATE (new F&B concept), MERGE (alias for existing key), or DISCARD
(noise/chain/brand). Expands `canonical_mapping.csv`, then re-normalizes
to produce final `matched_groups.json`.

## Architecture

```
4a: Batch loop (Agent-driven, 75 terms/batch)
     Pre-batch: review.py filter  → auto_matched
     Per-batch: read review-prompt.md → classify → review.py commit-batch
     Post-batch: review.py filter  (loop)
4b: review.py merge  → append canonical_mapping.csv
4c: exact_match.py --skip-unmatched  → final matched_groups.json
```

## Input

| File | Source | Content |
|------|--------|---------|
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Step 3 | Terms with `review_status = pending` |
| `data/mappings/canonical_mapping.csv` | Project asset | Existing canonical keys |
| `skills/04-review/review-prompt.md` | Skill asset | Classification prompt template |

## Output

| File | Content |
|------|---------|
| `runs/YYYY-MM-DD/batch_decisions/batch_NNN_decisions.csv` | Per-batch results |
| `data/mappings/canonical_mapping.csv` | Updated with new rows |
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Updated statuses |
| `runs/YYYY-MM-DD/matched_groups.json` | Final matched groups (re-normalize) |

## batch_decisions CSV schema

```csv
suggested_cleanup_term,platform,action,canonical_key,display_term,enriched_description,category,potential,target_canonical_key,reason
酸辣粉,google,CREATE,hot-sour-noodles,酸辣粉,"Spicy and sour...",fnb,high,,
旺角cafe,instagram,MERGE,,,,,coffee-shop,
肯德基,google,DISCARD,,,,,,restaurant chain
```

## Procedure

### 1. Preflight

```bash
python3 scripts/review.py check runs/YYYY-MM-DD
```

If output contains `NO_PENDING`, skip to step 4 (merge + re-normalize).

### 2. Batch Loop

Repeat while `pending > 0`:

#### 2a. Auto-match filter

```bash
python3 scripts/review.py filter runs/YYYY-MM-DD
```

Checks if pending terms now match the updated mapping (e.g. from prior batch MERGE).
Output: `auto_matched=N still_pending=M`.

#### 2b. Take next batch

```bash
python3 scripts/review.py next-batch runs/YYYY-MM-DD
```

Writes `batch_NNN_terms.txt` (≤75 terms). Output: `batch=N terms=M remaining_pending=R`.

#### 2c. Read prompt template

Read `skills/04-review/review-prompt.md`.

#### 2d. Assemble prompt

1. Load anchor list from `canonical_mapping.csv` (canonical_key | display_term | description)
2. Read `batch_NNN_terms.txt`
3. Replace `{ANCHORS}` and `{TERMS}` placeholders in prompt template

#### 2e. Classify (thinking=low sub-agent)

**Spawn a sub-agent with `thinking="low"`** to classify the batch:

```
sessions_spawn(task="<assembled prompt>", thinking="low")
sessions_yield
```

This saves ~42K thinking tokens per run vs thinking=medium.
The sub-agent receives the full prompt as its task, classifies every term
as CREATE / MERGE / DISCARD, and returns ONLY the JSON response.

#### 2f. Commit batch

```bash
python3 scripts/review.py commit-batch runs/YYYY-MM-DD <batch_num> '<json_response>'
```

Writes `batch_NNN_decisions.csv` and updates `review_status` in queue.

#### 2g. Error handling

If LLM response is malformed JSON, retry once. If still failing:

```bash
python3 scripts/review.py mark-error runs/YYYY-MM-DD <batch_num>
```

Marks those terms as `review_status = error`, then continue.

#### 2h. Check loop

```bash
python3 scripts/review.py filter runs/YYYY-MM-DD
```

If `still_pending > 0`, return to step 2b.

### 3. Merge

```bash
python3 scripts/review.py merge runs/YYYY-MM-DD
```

Appends CREATE/MERGE rows to `canonical_mapping.csv`. Flags conflicts
(match_value already assigned to different key).

### 4. Re-normalize

```bash
python3 scripts/exact_match.py --date YYYY-MM-DD --skip-unmatched
```

### 5. Verify

```bash
python3 scripts/review.py verify runs/YYYY-MM-DD
```

## Error Handling

| Scenario | Action |
|----------|--------|
| Required files missing | Abort |
| No pending terms | Skip to merge + re-normalize |
| LLM returns malformed JSON | Retry once; if still failing, `review.py mark-error` |
| Merge conflict | Flagged to stderr; operator resolves manually |
| Re-normalize fails | Abort; check exact_match.py output |

## Dependencies

- **Input**: `runs/YYYY-MM-DD/unmatched_review_queue.csv` (Step 3)
- **Assets**: `canonical_mapping.csv`, `review-prompt.md`
- **Scripts**: `scripts/review.py`, `scripts/exact_match.py`
- **Output**: `runs/YYYY-MM-DD/matched_groups.json` (Step 5)
