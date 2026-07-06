---
name: hk-fnb-step-02b-filter-fnb
description: >
  Step 2B of the HK F&B trending keyword pipeline.
  Filters Google Trends terms and Instagram extracted keywords to keep only
  F&B-related content. Outputs filtered records for downstream normalization.
---

# Step 2B — F&B Filter

**Pipeline position:** after Step 2A (Instagram keyword extraction), before Step 3 (Normalize).

## Purpose

Not every term from Google Trends or Instagram is F&B-related. Google Trends
may surface infrastructure, entertainment, or general news. Instagram extracted
keywords may include location names, activities, or non-food concepts picked up
from captions.

This step classifies every candidate term as F&B or not, keeping only the
relevant ones for normalization and ranking.

## Input

| File                                                | Source         | Content                                                           |
| --------------------------------------------------- | -------------- | ----------------------------------------------------------------- |
| `runs/YYYY-MM-DD/raw/google_raw.json`               | Google Trends  | ~7-8 `raw_representative` entries                                 |
| `runs/YYYY-MM-DD/extracted/instagram_keywords.json` | Step 2A output | ~804 records with `extracted_keywords` and `raw_payload.hashtags` |

## Output

| File                                               | Content                                                                                                                                                                          |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| `runs/YYYY-MM-DD/filtered/google_filtered.json`    | Google records with non-F&B removed + `_filter` metadata                                                                                                                         |
| `runs/YYYY-MM-DD/filtered/instagram_filtered.json` | Instagram records with non-F&B keywords removed, `extracted_keywords` + `raw_payload.hashtags` merged into unified `terms` field (each term is `{"text":"...", "source":"keyword | hashtag"}`) + `\_filter` metadata |

## Project Paths

| Path                                                | Purpose                                |
| --------------------------------------------------- | -------------------------------------- |
| `runs/YYYY-MM-DD/raw/google_raw.json`               | Input: raw Google Trends records       |
| `runs/YYYY-MM-DD/extracted/instagram_keywords.json` | Input: records with extracted_keywords |
| `runs/YYYY-MM-DD/filtered/google_filtered.json`     | Output: filtered Google records        |
| `runs/YYYY-MM-DD/filtered/instagram_filtered.json`  | Output: filtered Instagram records     |

---

## Procedure

### 1. Prepare Input Terms

#### Google Trends

Read `raw/google_raw.json`. Extract all `raw_representative` values from the `records` array.
These are the terms to classify.

#### Instagram Keywords

Read `extracted/instagram_keywords.json`. Collect both `extracted_keywords` and
`raw_payload.hashtags` across all records, count their frequency, and deduplicate
into a single flat list:

```bash
python3 -c "
import json
from collections import Counter

with open('runs/YYYY-MM-DD/extracted/instagram_keywords.json') as f:
    data = json.load(f)

counter = Counter()
for r in data['records']:
    for kw in r.get('extracted_keywords', []):
        counter[kw] += 1
    for ht in (r.get('raw_payload') or {}).get('hashtags', []):
        counter[ht] += 1

# Output: keyword | frequency, sorted by frequency desc
for kw, freq in counter.most_common():
    print(f'{kw} ({freq})')
"
```

### 2. Classify All Terms

Build a single classification prompt containing both sources, then classify
all terms in one pass.

#### Classification Prompt

Replace `{GOOGLE_TERMS}` with the Google Trends terms and `{INSTAGRAM_TERMS}`
with the Instagram keyword frequency list.

---

You are filtering keywords for a Hong Kong F&B (Food & Beverage) trending pipeline.

Your job: classify each term below as F&B-related or not.

## F&B definition

A term IS F&B if it relates to:

- Food, drinks, beverages, cuisine, dishes, ingredients
- Restaurants, cafes, bars, dining formats — both as concepts (e.g. 放題, omakase) AND as specific venues that are well-known or currently trending in HK food conversations (e.g. 壽司郎, 麥當勞, 九記牛腩, a viral hotpot spot). When in doubt, keep the term — downstream normalization will handle borderline cases.
- Cooking styles, food culture, food preparation methods
- Specific food/drink brands that are primarily F&B (e.g. 肯德基/KFC, 壽司郎/Sushiro, Godiva, 薩莉亞/Saizeriya)
- Food delivery, food markets, food streets (as food concepts)
- Desserts, snacks, baked goods, confectionery
- Food-related events or festivals (e.g. 美食博覽, wine fair)

A term is NOT F&B if it is:

- Infrastructure, transport (e.g. 港珠澳大橋, bridges, highways, MTR stations)
- TV channels, sports, entertainment (e.g. cctv 5, NBA, concert)
- General retail/shopping not food-specific (e.g. 手袋, clothing, electronics)
- Politics, news, weather, current affairs
- Generic non-food terms
- Location-only terms without food context (e.g. 旺角, 中環 — unless part of a food term)
- Non-food activities (e.g. 唱K, 行山, 打卡, yoga)
- Generic social media terms (e.g. hkfood, 香港美食, foodie, 相機食先)

## Terms to classify

### Google Trends:

{GOOGLE_TERMS}

### Instagram terms — extracted keywords + hashtags (frequency):

{INSTAGRAM_TERMS}

## Output format

Return ONLY a JSON object. No markdown, no explanation.

```json
{
  "terms": [
    { "term": "肯德基", "source": "google", "is_fnb": true },
    { "term": "港珠澳大橋", "source": "google", "is_fnb": false },
    { "term": "cctv 5", "source": "google", "is_fnb": false },
    { "term": "沙嗲拼盤", "source": "instagram", "is_fnb": true },
    { "term": "唱K", "source": "instagram", "is_fnb": false }
  ]
}
```

Rules:

- `term` must match the input term exactly.
- `source` must be `"google"` or `"instagram"`.
- `is_fnb` is `true` if the term is F&B-related, `false` otherwise.
- Classify ALL terms. Return ONLY the JSON.

---

### 3. Produce Filtered Outputs

After receiving the classification JSON, produce two filtered output files.

#### google_filtered.json

```bash
python3 -c "
import json

# Load classification results
classifications = {item['term']: item['is_fnb'] for item in CLASSIFICATION_JSON['terms'] if item['source'] == 'google'}

# Load raw Google data
with open('runs/YYYY-MM-DD/raw/google_raw.json') as f:
    raw = json.load(f)

records = raw.get('records', [])
kept = []
dropped = []
for r in records:
    term = r.get('raw_representative', '')
    if classifications.get(term, True):  # fail-open: keep if not in results
        kept.append(r)
    else:
        dropped.append(term)

output = {
    **{k: v for k, v in raw.items() if k != 'records'},
    'records': kept,
    '_filter': {
        'total': len(records),
        'kept': len(kept),
        'dropped': dropped
    }
}

import os
os.makedirs('runs/YYYY-MM-DD/filtered', exist_ok=True)
with open('runs/YYYY-MM-DD/filtered/google_filtered.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'Google: kept={len(kept)} dropped={len(dropped)}')
"
```

#### instagram_filtered.json

```bash
python3 -c "
import json

# Load classification results
fnb_terms = {item['term'] for item in CLASSIFICATION_JSON['terms'] if item['source'] == 'instagram' and item['is_fnb']}

# Load extracted Instagram data
with open('runs/YYYY-MM-DD/extracted/instagram_keywords.json') as f:
    data = json.load(f)

records = data.get('records', [])
kept_records = []
total_terms = 0
kept_terms = 0
dropped_terms = {}  # term -> frequency

for r in records:
    kws = r.get('extracted_keywords', [])
    hts = (r.get('raw_payload') or {}).get('hashtags', [])
    # Build terms with source tracking
    all_terms = [{'text': t, 'source': 'keyword'} for t in kws] + \
                [{'text': t, 'source': 'hashtag'} for t in hts]
    all_texts = [t['text'] for t in all_terms]
    total_terms += len(all_texts)
    filtered = [t for t in all_terms if t['text'] in fnb_terms]
    kept_terms += len(filtered)
    for t in all_terms:
        if t['text'] not in fnb_terms:
            dropped_terms[t['text']] = dropped_terms.get(t['text'], 0) + 1
    if filtered:  # only keep record if it has remaining terms
        # Build output record: replace extracted_keywords with unified terms field
        out_rec = {k: v for k, v in r.items() if k != 'extracted_keywords'}
        out_rec['terms'] = filtered
        kept_records.append(out_rec)

dropped_list = [{'term': t, 'frequency': freq} for t, freq in sorted(dropped_terms.items(), key=lambda x: -x[1])]

output = {
    **{k: v for k, v in data.items() if k != 'records'},
    'records': kept_records,
    '_filter': {
        'total_terms': total_terms,
        'kept_terms': kept_terms,
        'dropped': dropped_list
    }
}

import os
os.makedirs('runs/YYYY-MM-DD/filtered', exist_ok=True)
with open('runs/YYYY-MM-DD/filtered/instagram_filtered.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'Instagram: records kept={len(kept_records)}/{len(records)}, terms kept={kept_terms}/{total_terms}')
"
```

### 4. Verify

```bash
python3 -c "
import json, os

run_dir = 'runs/YYYY-MM-DD'

for fname in ['google_filtered.json', 'instagram_filtered.json']:
    path = os.path.join(run_dir, 'filtered', fname)
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        fmeta = data.get('_filter', {})
        print(f'{fname}:')
        if 'total' in fmeta:
            print(f'  records: {fmeta[\"kept\"]}/{fmeta[\"total\"]} kept')
            if fmeta.get('dropped'):
                print(f'  dropped: {fmeta[\"dropped\"]}')
        if 'total_terms' in fmeta:
            print(f'  terms: {fmeta[\"kept_terms\"]}/{fmeta[\"total_terms\"]} kept')
            if fmeta.get('dropped'):
                print(f'  dropped top-10: {fmeta[\"dropped\"][:10]}')
    else:
        print(f'{fname}: MISSING')
"
```

---

## Key Design Decisions

### Fail-Open

If the LLM classification fails or returns malformed JSON, **keep all terms**.
A false positive (non-F&B term in the ranking) is less harmful than a false
negative (missing a real F&B trend). Non-F&B terms that slip through will
likely fail to match any canonical key in Step 3 and be discarded there.

### Records with No Remaining Terms

If ALL terms (extracted_keywords + hashtags) for an Instagram record are
filtered out, the entire record is dropped from `instagram_filtered.json`.
Records with zero valid terms contribute nothing to downstream steps.

### Volume Semantics

For Instagram, keyword volume = frequency (how many posts mention the keyword).
This is computed during deduplication and carried through as metadata. It is
NOT used in the filter decision itself, but is preserved for Step 5 ranking.

---

## Error Handling

| Scenario                            | Action                                              |
| ----------------------------------- | --------------------------------------------------- |
| `google_raw.json` missing           | Skip Google filter, proceed with Instagram only.    |
| `instagram_keywords.json` missing   | Skip Instagram filter, proceed with Google only.    |
| Both inputs missing                 | Abort. Nothing to filter.                           |
| LLM classification fails            | Fail-open: keep all terms, write unfiltered output. |
| LLM returns malformed JSON          | Retry once. If still failing, fail-open.            |
| No terms to classify (empty inputs) | Skip step, write empty filtered files.              |

---

## Token Budget

| Item                                                    | Estimate          |
| ------------------------------------------------------- | ----------------- |
| Google Trends terms (~8)                                | negligible        |
| Instagram terms — keywords + hashtags (~500-800 unique) | ~8K chars         |
| Classification prompt + instructions                    | ~3K chars         |
| JSON response (~800 terms)                              | ~20K chars output |
| **Total**                                               | **~35K tokens**   |

---

## Dependencies

- **Input from Step 1**: `runs/YYYY-MM-DD/raw/google_raw.json`
- **Input from Step 2A**: `runs/YYYY-MM-DD/extracted/instagram_keywords.json`
- **Output to Step 3**: `runs/YYYY-MM-DD/filtered/google_filtered.json`, `runs/YYYY-MM-DD/filtered/instagram_filtered.json`
