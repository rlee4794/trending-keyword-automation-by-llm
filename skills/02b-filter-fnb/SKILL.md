---
name: hk-fnb-step-02b-filter-fnb
description: >
  Step 2B of the HK F&B trending keyword pipeline.
  Filters Google Trends terms and Instagram extracted keywords to keep only
  F&B-related content via LLM classification.
---

# Step 2B — F&B Filter

**Pipeline position:** after Step 2A, before Step 3.

## Purpose

Classify all candidate terms (Google Trends + Instagram extracted keywords + hashtags)
as F&B or not. Google Trends may surface non-food content; Instagram keywords may
include locations, activities, or noise.

## Input

| File | Source | Content |
|------|--------|---------|
| `runs/YYYY-MM-DD/raw/google_raw.json` | Step 1 | ~7-8 `raw_representative` entries |
| `runs/YYYY-MM-DD/extracted/instagram_keywords.json` | Step 2A | ~804 records with `extracted_keywords` |

## Output

| File | Content |
|------|---------|
| `runs/YYYY-MM-DD/filtered/google_filtered.json` | Google records with non-F&B removed + `_filter` metadata |
| `runs/YYYY-MM-DD/filtered/instagram_filtered.json` | IG records with non-F&B terms removed, `terms` = `{"text":"...", "source":"keyword|hashtag"}` |

## Procedure

### 1. Prepare Input Terms

```bash
# Google: extract raw_representative from google_raw.json
python3 -c "
import json
with open('runs/YYYY-MM-DD/raw/google_raw.json') as f:
    data = json.load(f)
for r in data['records']:
    print(r.get('raw_representative',''))
" > /tmp/filter_google_terms.txt

# Instagram: collect keywords + hashtags with frequency
python3 -c "
import json
from collections import Counter
with open('runs/YYYY-MM-DD/extracted/instagram_keywords.json') as f:
    data = json.load(f)
counter = Counter()
for r in data['records']:
    for kw in r.get('extracted_keywords', []): counter[kw] += 1
    for ht in (r.get('raw_payload') or {}).get('hashtags', []): counter[ht] += 1
for kw, freq in counter.most_common():
    print(f'{kw} ({freq})')
" > /tmp/filter_instagram_terms.txt
```

### 2. Classify All Terms (LLM)

Build a single prompt with both sources. Classify all terms in one pass.

#### Classification Prompt

Replace `{GOOGLE_TERMS}` and `{INSTAGRAM_TERMS}` with the files above.

---

You are filtering keywords for a Hong Kong F&B trending pipeline.
Classify each term as F&B-related or not.

## F&B definition

IS F&B: food, drinks, cuisine, dishes, ingredients, restaurants, cafes, bars, dining formats
(both concepts AND specific trending HK venues), cooking styles, food brands (KFC, Sushiro,
Godiva), food delivery, food markets, desserts, snacks, food events.

NOT F&B: infrastructure, transport, TV/sports/entertainment, general retail, politics,
weather, generic non-food terms, location-only (旺角, 中環), non-food activities (唱K, 行山),
generic social media terms (hkfood, 香港美食, foodie, 相機食先).

When in doubt, keep — downstream normalization handles borderline cases.

## Terms to classify

### Google Trends:
{GOOGLE_TERMS}

### Instagram (keyword | frequency):
{INSTAGRAM_TERMS}

## Output

Return ONLY JSON. No markdown, no explanation.

```json
{
  "terms": [
    { "term": "肯德基", "source": "google", "is_fnb": true },
    { "term": "港珠澳大橋", "source": "google", "is_fnb": false },
    { "term": "沙嗲拼盤", "source": "instagram", "is_fnb": true }
  ]
}
```

Rules: `term` matches input exactly, `source` is "google" or "instagram", `is_fnb` is boolean.
Classify ALL terms.

---

### 3. Produce Filtered Outputs

After receiving the JSON, write filtered files:

```bash
python3 -c "
import json, os

# Paste the LLM response JSON here
resp = '''PASTE_JSON_HERE'''
classifications = json.loads(resp)

fnb_google = {t['term'] for t in classifications['terms'] if t['source']=='google' and t['is_fnb']}
fnb_ig = {t['term'] for t in classifications['terms'] if t['source']=='instagram' and t['is_fnb']}

run_dir = 'runs/YYYY-MM-DD'
os.makedirs(f'{run_dir}/filtered', exist_ok=True)

# Google
with open(f'{run_dir}/raw/google_raw.json') as f:
    raw = json.load(f)
records = raw.get('records', [])
kept, dropped = [], []
for r in records:
    term = r.get('raw_representative', '')
    if fnb_google and term not in fnb_google:
        dropped.append(term)
    else:
        kept.append(r)
output = {**{k:v for k,v in raw.items() if k!='records'}, 'records': kept,
          '_filter': {'total': len(records), 'kept': len(kept), 'dropped': dropped}}
with open(f'{run_dir}/filtered/google_filtered.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'Google: kept={len(kept)} dropped={len(dropped)}')

# Instagram
with open(f'{run_dir}/extracted/instagram_keywords.json') as f:
    data = json.load(f)
kept_records, total_terms, kept_terms, dropped_terms = [], 0, 0, {}
for r in data['records']:
    kws = r.get('extracted_keywords', [])
    hts = (r.get('raw_payload') or {}).get('hashtags', [])
    all_terms = [{'text': t, 'source': 'keyword'} for t in kws] + \
                [{'text': t, 'source': 'hashtag'} for t in hts]
    total_terms += len(all_terms)
    filtered = [t for t in all_terms if t['text'] in fnb_ig]
    kept_terms += len(filtered)
    for t in all_terms:
        if t['text'] not in fnb_ig:
            dropped_terms[t['text']] = dropped_terms.get(t['text'], 0) + 1
    if filtered:
        out_rec = {k:v for k,v in r.items() if k!='extracted_keywords'}
        out_rec['terms'] = filtered
        kept_records.append(out_rec)
dropped_list = [{'term': t, 'freq': f} for t,f in sorted(dropped_terms.items(), key=lambda x:-x[1])]
output = {**{k:v for k,v in data.items() if k!='records'}, 'records': kept_records,
          '_filter': {'total_terms': total_terms, 'kept_terms': kept_terms, 'dropped': dropped_list}}
with open(f'{run_dir}/filtered/instagram_filtered.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'Instagram: records={len(kept_records)}/{len(data[\"records\"])}, terms={kept_terms}/{total_terms}')
"
```

### 4. Verify

```bash
python3 -c "
import json, os
for fname in ['google_filtered.json', 'instagram_filtered.json']:
    path = f'runs/YYYY-MM-DD/filtered/{fname}'
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        meta = data.get('_filter', {})
        print(f'{fname}: kept={meta.get(\"kept\", meta.get(\"kept_terms\"))}, '
              f'total={meta.get(\"total\", meta.get(\"total_terms\"))}')
    else:
        print(f'{fname}: MISSING')
"
```

## Key Decisions

- **Fail-open**: if LLM fails, keep all terms. False positive < false negative.
- **Records with zero terms dropped**: IG records with all terms filtered out are removed entirely.
- **Single prompt**: both Google and Instagram classified in one LLM call.

## Error Handling

| Scenario | Action |
|----------|--------|
| Input file missing | Skip that platform, continue with available data |
| Both inputs missing | Abort |
| LLM fails / malformed JSON | Retry once. If still failing, keep all terms (fail-open) |
| No terms to classify | Skip, write empty filtered files |

## Dependencies

- **Input**: `runs/YYYY-MM-DD/raw/google_raw.json` (Step 1), `runs/YYYY-MM-DD/extracted/instagram_keywords.json` (Step 2A)
- **Output to Step 3**: `runs/YYYY-MM-DD/filtered/google_filtered.json`, `runs/YYYY-MM-DD/filtered/instagram_filtered.json`
