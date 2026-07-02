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

Terms that failed exact-match in Step 3 need semantic classification.
This step reads the unmatched review queue, classifies each term as
CREATE (new F&B concept), MERGE (alias for existing key), or DISCARD
(noise/chain/brand), then expands `canonical_mapping.csv` and re-runs
exact-match to produce the final `matched_groups.json`.

## Architecture

```
4a: Batch loop (Agent-driven, 75 terms/batch)
     Pre-batch: filter pending terms already covered by mapping → auto_matched
     Per-batch: read review-prompt.md → assemble prompt → classify → write CSV
     Post-batch: update review_status in queue

4b: Merge decisions → append canonical_mapping.csv (Python one-liner)

4c: Re-normalize (exact_match.py --skip-unmatched)
     → final matched_groups.json for Step 5
```

## Input

| File | Source | Content |
|---|---|---|
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Step 3 | Terms with `review_status = pending` |
| `data/mappings/canonical_mapping.csv` | Project asset | Existing canonical keys (4 columns) |
| `skills/04-review/review-prompt.md` | Skill asset | Static classification prompt template |

## Output

| File | Content |
|---|---|
| `runs/YYYY-MM-DD/batch_decisions/batch_NNN_decisions.csv` | Per-batch classification results |
| `data/mappings/canonical_mapping.csv` | Updated with new CREATE/MERGE rows |
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Updated with `review_status` (done/auto_matched/error) |
| `runs/YYYY-MM-DD/matched_groups.json` | Final matched groups for Step 5 (via re-normalize) |

## Project Paths

All paths are relative to the project root.

| Path | Purpose |
|---|---|
| `data/mappings/canonical_mapping.csv` | Core mapping table (4 columns) |
| `runs/YYYY-MM-DD/unmatched_review_queue.csv` | Input: pending terms to review |
| `runs/YYYY-MM-DD/batch_decisions/` | Per-batch decision CSV files |
| `runs/YYYY-MM-DD/matched_groups.json` | Final output for Step 5 |
| `skills/04-review/review-prompt.md` | Classification prompt template |
| `scripts/exact_match.py` | Re-normalize script |

### batch_NNN_decisions.csv schema

```csv
suggested_cleanup_term,platform,action,canonical_key,display_term,enriched_description,category,target_canonical_key,reason
酸辣粉,google,CREATE,hot-sour-noodles,酸辣粉,"Spicy and sour glass noodle soup...",fnb,,
旺角cafe,instagram,MERGE,,,,,coffee-shop,
肯德基,google,DISCARD,,,,,,restaurant chain
```

---

## Procedure

### 0. Pre-flight Checks

```bash
# Verify required files exist
test -f "data/mappings/canonical_mapping.csv" || { echo "ERROR: canonical_mapping.csv missing"; exit 1; }
test -f "runs/YYYY-MM-DD/unmatched_review_queue.csv" || { echo "ERROR: unmatched_review_queue.csv missing"; exit 1; }
test -f "skills/04-review/review-prompt.md" || { echo "ERROR: review-prompt.md missing"; exit 1; }
```

If any file is missing, abort.

### 1. Check for Resume

Read `unmatched_review_queue.csv` and count pending rows:

```bash
python3 -c "
import csv
with open('runs/YYYY-MM-DD/unmatched_review_queue.csv') as f:
    rows = list(csv.DictReader(f))
pending = sum(1 for r in rows if r.get('review_status') == 'pending')
done = sum(1 for r in rows if r.get('review_status') == 'done')
auto = sum(1 for r in rows if r.get('review_status') == 'auto_matched')
error = sum(1 for r in rows if r.get('review_status') == 'error')
print(f'pending={pending} done={done} auto_matched={auto} error={error}')
"
```

- If `pending = 0`: all terms processed. Skip to step 5 (merge + re-normalize).
- If `pending > 0`: continue with batch loop (step 2).

Create batch output directory:

```bash
mkdir -p "runs/YYYY-MM-DD/batch_decisions"
```

### 2. Batch Loop

Repeat the following sub-steps while `pending > 0`.

#### 2a. Filter: Check if Pending Terms Are Already in Mapping

Before each batch, check if any pending terms are now covered by the
canonical mapping (e.g. a previous batch's MERGE added a match_value
that covers a term still in the queue).

```bash
python3 -c "
import csv
from pathlib import Path

MAPPING = Path('data/mappings/canonical_mapping.csv')
QUEUE = Path('runs/YYYY-MM-DD/unmatched_review_queue.csv')

# Load all match_values from mapping
match_values = set()
with MAPPING.open() as f:
    for row in csv.DictReader(f):
        mv = (row.get('match_value') or '').strip()
        if mv:
            match_values.add(mv)

# Find pending terms that are now in mapping
auto_matched = []
still_pending = []
with QUEUE.open() as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        if row.get('review_status') != 'pending':
            continue
        term = (row.get('suggested_cleanup_term') or '').strip()
        if term in match_values:
            auto_matched.append(row)
        else:
            still_pending.append(row)

# Update auto_matched rows in queue
if auto_matched:
    all_rows = []
    with QUEUE.open() as f:
        all_rows = list(csv.DictReader(f))
    for r in all_rows:
        key = (r.get('suggested_cleanup_term') or '').strip(), r.get('platform', '')
        for am in auto_matched:
            am_key = (am.get('suggested_cleanup_term') or '').strip(), am.get('platform', '')
            if key == am_key:
                r['review_status'] = 'auto_matched'
                r['review_action'] = 'AUTO_MATCHED'
                # Find which canonical_key this matches
                with MAPPING.open() as mf:
                    for mrow in csv.DictReader(mf):
                        if (mrow.get('match_value') or '').strip() == am.get('suggested_cleanup_term', '').strip():
                            r['target_canonical_key'] = mrow.get('canonical_key', '')
                            break
    with QUEUE.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    # Ensure trailing newline
    content = QUEUE.read_text()
    if content and not content.endswith('\n'):
        QUEUE.write_text(content + '\n')

print(f'auto_matched={len(auto_matched)} still_pending={len(still_pending)}')
"
```

#### 2b. Take Next Batch (≤75 Pending Terms)

```bash
python3 -c "
import csv

with open('runs/YYYY-MM-DD/unmatched_review_queue.csv') as f:
    rows = list(csv.DictReader(f))

pending = [r for r in rows if r.get('review_status') == 'pending']
batch = pending[:75]

# Determine batch number
import os, re
existing = os.listdir('runs/YYYY-MM-DD/batch_decisions/')
nums = [int(re.match(r'batch_(\d+)_decisions\.csv', f).group(1))
        for f in existing if re.match(r'batch_(\d+)_decisions\.csv', f)]
batch_num = max(nums) + 1 if nums else 1

# Write batch terms for prompt assembly
with open(f'runs/YYYY-MM-DD/batch_decisions/batch_{batch_num:03d}_terms.txt', 'w') as f:
    for r in batch:
        f.write(f\"{r['suggested_cleanup_term']} | {r['platform']}\n\")

print(f'batch={batch_num} terms={len(batch)} remaining_pending={len(pending) - len(batch)}')
"
```

#### 2c. Read Prompt Template

Read `skills/04-review/review-prompt.md`. This is the static classification
template with `{ANCHORS}` and `{TERMS}` placeholders.

#### 2d. Assemble Prompt

1. Read `canonical_mapping.csv` and build the anchor list:

```bash
python3 -c "
import csv
with open('data/mappings/canonical_mapping.csv') as f:
    for row in csv.DictReader(f):
        ck = row.get('canonical_key', '').strip()
        dt = row.get('display_term', '').strip()
        desc = (row.get('enriched_description') or '').strip()
        if ck and dt:
            if desc:
                print(f'{ck} | {dt} | {desc}')
            else:
                print(f'{ck} | {dt}')
" > /tmp/step4_anchors.txt
```

2. Read the batch terms file from step 2b.

3. Replace placeholders in the prompt template:
   - `{ANCHORS}` → contents of `/tmp/step4_anchors.txt`
   - `{TERMS}` → contents of `batch_NNN_terms.txt`

#### 2e. Classify the Batch

Send the assembled prompt. You (the Agent) are the classifier.
Read the prompt, classify every term as CREATE / MERGE / DISCARD,
and output ONLY the JSON response as specified in the prompt template.

#### 2f. Parse JSON and Write batch_NNN_decisions.csv

Take the JSON response and write it as CSV:

```bash
python3 -c "
import csv, json, os, sys

# Paste the JSON response here
response = '''PASTE_JSON_RESPONSE_HERE'''
data = json.loads(response)
decisions = data.get('decisions', [])

batch_num = BATCH_NUMBER  # from step 2b
out_path = f'runs/YYYY-MM-DD/batch_decisions/batch_{batch_num:03d}_decisions.csv'

fieldnames = [
    'suggested_cleanup_term', 'platform', 'action',
    'canonical_key', 'display_term', 'enriched_description', 'category',
    'target_canonical_key', 'reason'
]

with open(out_path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for d in decisions:
        row = {
            'suggested_cleanup_term': d.get('suggested_cleanup_term', ''),
            'platform': d.get('platform', ''),
            'action': d.get('action', '').upper(),
            'canonical_key': d.get('canonical_key', ''),
            'display_term': d.get('display_term', ''),
            'enriched_description': d.get('enriched_description', ''),
            'category': d.get('category', ''),
            'target_canonical_key': d.get('target_canonical_key', ''),
            'reason': d.get('reason', ''),
        }
        w.writerow(row)

# Ensure trailing newline
content = open(out_path).read()
if content and not content.endswith('\n'):
    open(out_path, 'w').write(content + '\n')

print(f'Wrote {len(decisions)} decisions to {out_path}')
"
```

#### 2g. Update review_status in Queue

Mark the processed terms as `done`:

```bash
python3 -c "
import csv

QUEUE = 'runs/YYYY-MM-DD/unmatched_review_queue.csv'
DECISIONS = 'runs/YYYY-MM-DD/batch_decisions/batch_BATCH_NUMBER_decisions.csv'

# Load decisions
decisions = {}
with open(DECISIONS) as f:
    for row in csv.DictReader(f):
        key = (row.get('suggested_cleanup_term', '').strip(), row.get('platform', '').strip())
        decisions[key] = row

# Update queue
with open(QUEUE) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

updated = 0
for r in rows:
    if r.get('review_status') != 'pending':
        continue
    key = (r.get('suggested_cleanup_term', '').strip(), r.get('platform', '').strip())
    if key in decisions:
        d = decisions[key]
        r['review_status'] = 'done'
        r['review_action'] = d.get('action', '')
        r['target_canonical_key'] = d.get('target_canonical_key', d.get('canonical_key', ''))
        r['review_note'] = d.get('reason', '')
        updated += 1

with open(QUEUE, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

# Ensure trailing newline
content = open(QUEUE).read()
if content and not content.endswith('\n'):
    open(QUEUE, 'w').write(content + '\n')

print(f'Updated {updated} rows to done')
"
```

#### 2h. Check Loop Condition

Count remaining pending rows:

```bash
python3 -c "
import csv
with open('runs/YYYY-MM-DD/unmatched_review_queue.csv') as f:
    rows = list(csv.DictReader(f))
pending = sum(1 for r in rows if r.get('review_status') == 'pending')
print(f'remaining_pending={pending}')
"
```

- If `pending > 0`: go back to step 2a (next batch).
- If `pending = 0`: all batches complete. Proceed to step 3.

#### 2i. Error Handling for Failed Batches

If a batch classification returns malformed JSON:

1. Retry once with the same prompt.
2. If still failing, mark those terms as `review_status = error`,
   `review_note = "LLM parse failed after retry"`:

```bash
python3 -c "
import csv

QUEUE = 'runs/YYYY-MM-DD/unmatched_review_queue.csv'
# Read the batch terms file to know which terms failed
with open('runs/YYYY-MM-DD/batch_decisions/batch_BATCH_NUMBER_terms.txt') as f:
    failed_terms = set()
    for line in f:
        parts = line.strip().split(' | ')
        if len(parts) >= 2:
            failed_terms.add((parts[0].strip(), parts[1].strip()))

with open(QUEUE) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

updated = 0
for r in rows:
    if r.get('review_status') != 'pending':
        continue
    key = (r.get('suggested_cleanup_term', '').strip(), r.get('platform', '').strip())
    if key in failed_terms:
        r['review_status'] = 'error'
        r['review_note'] = 'LLM parse failed after retry'
        updated += 1

with open(QUEUE, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

# Ensure trailing newline
content = open(QUEUE).read()
if content and not content.endswith('\n'):
    open(QUEUE, 'w').write(content + '\n')

print(f'Marked {updated} rows as error')
"
```

Then continue to next batch (go to step 2a).

### 3. Merge Decisions → Append canonical_mapping.csv

After all batches complete, merge all `batch_NNN_decisions.csv` files
and append new mappings to `canonical_mapping.csv`:

```bash
python3 -c "
import csv
from pathlib import Path

MAPPING = Path('data/mappings/canonical_mapping.csv')
BATCH_DIR = Path('runs/YYYY-MM-DD/batch_decisions')

# Load existing match_values for dedup
existing_matches = set()
existing_keys = {}
with MAPPING.open() as f:
    for row in csv.DictReader(f):
        mv = (row.get('match_value') or '').strip()
        ck = (row.get('canonical_key') or '').strip()
        dt = (row.get('display_term') or '').strip()
        desc = (row.get('enriched_description') or '').strip()
        cat = (row.get('category') or '').strip()
        if mv:
            existing_matches.add(mv)
        if ck and ck not in existing_keys:
            existing_keys[ck] = {'display_term': dt, 'enriched_description': desc, 'category': cat}

# Collect all decisions
decisions = []
for f in sorted(BATCH_DIR.glob('batch_*_decisions.csv')):
    with f.open() as fh:
        for row in csv.DictReader(fh):
            decisions.append(row)

# Ensure trailing newline before appending
content = MAPPING.read_text()
if content and not content.endswith('\n'):
    MAPPING.write_text(content + '\n')

# Append new mappings
added = 0
with MAPPING.open('a', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['canonical_key', 'match_value', 'display_term', 'enriched_description', 'category'])
    for d in decisions:
        action = (d.get('action') or '').upper()
        match_value = (d.get('suggested_cleanup_term') or '').strip()
        if not match_value or match_value in existing_matches:
            continue

        if action == 'CREATE':
            canonical_key = (d.get('canonical_key') or '').strip().lower()
            display_term = (d.get('display_term') or match_value).strip()
            enriched_description = (d.get('enriched_description') or '').strip()
            if not canonical_key:
                continue
            w.writerow({
                'canonical_key': canonical_key,
                'match_value': match_value,
                'display_term': display_term,
                'enriched_description': enriched_description,
                'category': (d.get('category') or '').strip(),
            })
            existing_matches.add(match_value)
            added += 1

        elif action == 'MERGE':
            target_key = (d.get('target_canonical_key') or '').strip()
            if not target_key or target_key not in existing_keys:
                continue
            ek = existing_keys[target_key]
            w.writerow({
                'canonical_key': target_key,
                'match_value': match_value,
                'display_term': ek['display_term'],
                'enriched_description': ek.get('enriched_description', ''),
                'category': ek.get('category', ''),
            })
            existing_matches.add(match_value)
            added += 1

        # DISCARD: intentionally do nothing

# Ensure trailing newline after appending
content = MAPPING.read_text()
if content and not content.endswith('\n'):
    MAPPING.write_text(content + '\n')

# Summary
created = sum(1 for d in decisions if (d.get('action') or '').upper() == 'CREATE')
merged = sum(1 for d in decisions if (d.get('action') or '').upper() == 'MERGE')
discarded = sum(1 for d in decisions if (d.get('action') or '').upper() == 'DISCARD')
print(f'Merge complete: {created} CREATE, {merged} MERGE, {discarded} DISCARD → {added} rows appended')
"
```

### 4. Re-normalize

Re-run exact match with the updated mapping to produce final matched groups:

```bash
cd PROJECT_ROOT && python3 scripts/exact_match.py --date YYYY-MM-DD --skip-unmatched
```

This updates `matched_groups.json` with all newly-added MERGE mappings.
Terms that were unmatched in Step 3 are now correctly grouped under their
canonical keys.

### 5. Verify

```bash
python3 -c "
import json, csv, os

run_dir = 'runs/YYYY-MM-DD'

# Check matched_groups.json
with open(os.path.join(run_dir, 'matched_groups.json')) as f:
    matched = json.load(f)
print(f'matched_groups.json: {len(matched)} keys')

# Check queue status
with open(os.path.join(run_dir, 'unmatched_review_queue.csv')) as f:
    rows = list(csv.DictReader(f))
statuses = {}
for r in rows:
    s = r.get('review_status', 'unknown')
    statuses[s] = statuses.get(s, 0) + 1
print(f'unmatched_review_queue.csv: {statuses}')

# Check mapping growth
with open('data/mappings/canonical_mapping.csv') as f:
    mapping_rows = list(csv.DictReader(f))
print(f'canonical_mapping.csv: {len(mapping_rows)} rows')
keys_with_desc = sum(1 for r in mapping_rows if (r.get('enriched_description') or '').strip())
print(f'  keys with description: {keys_with_desc}/{len(mapping_rows)}')

print('Step 4 complete.')
"
```

---

## Error Handling

| Scenario | Action |
|---|---|
| `unmatched_review_queue.csv` missing | Abort. Step 3 must run first. |
| `canonical_mapping.csv` missing | Abort. This is a required asset. |
| `review-prompt.md` missing | Abort. Cannot classify without prompt template. |
| No pending terms (all done/auto_matched/error) | Skip batch loop, go directly to merge + re-normalize. |
| Batch classification returns malformed JSON | Retry once. If still failing, mark terms as `error`, continue to next batch. |
| Merge append fails | Abort. Check CSV file permissions. |
| Re-normalize fails | Abort. Check `exact_match.py` output. |

---

## Token Budget

| Item | Estimate |
|---|---|
| Pre-flight + resume check | ~1K tokens |
| Per batch: anchor list (~900 keys × ~80 chars) | ~72K chars input |
| Per batch: 75 terms × ~30 chars | ~2.3K chars input |
| Per batch: prompt template | ~5K chars |
| Per batch: JSON response | ~8K chars output |
| **Per batch total** | **~55K tokens** |
| **8 batches (593 terms ÷ 75)** | **~440K tokens** |
| Merge + verify | ~2K tokens |
| **Step 4 total** | **~450K tokens** |

Token cost decreases over time as `canonical_mapping.csv` grows and
exact-match hit rate improves, reducing the number of unmatched terms.

---

## Dependencies

- **Input from Step 3**: `runs/YYYY-MM-DD/unmatched_review_queue.csv`
- **Required assets**: `data/mappings/canonical_mapping.csv`, `skills/04-review/review-prompt.md`
- **Script**: `scripts/exact_match.py` (for re-normalize)
- **Output to Step 5**: `runs/YYYY-MM-DD/matched_groups.json`
