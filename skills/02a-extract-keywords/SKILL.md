---
name: hk-fnb-step-02a-extract-keywords
description: >
  Step 2A of the HK F&B trending keyword pipeline.
  Extracts F&B-related keywords from Instagram post captions using LLM.
  Outputs enriched records with extracted_keywords for Step 2B filtering.
---

# Step 2A — Instagram Keyword Extraction

**Pipeline position:** after Step 1, before Step 2B.

## Purpose

Extract F&B keywords (dishes, cuisines, ingredients, restaurants) from Instagram
caption snippets. Raw data has `#hkfood` as `raw_representative` — the real content
is in the captions.

## Input

`runs/YYYY-MM-DD/raw/instagram_raw.json` — each record has `raw_payload.caption_snippet` (~500 chars).

## Output

`runs/YYYY-MM-DD/extracted/instagram_keywords.json` — same structure + `extracted_keywords` field.

```json
{
  "raw_representative": "#hkfood",
  "source_kind": "hashtag",
  "raw_payload": { "caption_snippet": "...", "hashtags": [...], ... },
  "extracted_keywords": ["沙嗲拼盤", "關東煮", "燒蠔", "蒜香茄子"]
}
```

## Procedure

### 1. Resume Check

Check if `extracted/instagram_keywords.json` exists. If N records already processed,
resume from index N. Otherwise start from 0.

### 2. Batch Processing

Process in batches of **100 records**. Per batch:

1. Build prompt with batch captions (format: `record_index | caption_text`)
2. Send prompt, parse JSON response
3. Append `extracted_keywords` to each record
4. Write incrementally to output file (crash-safe)

### 3. Extraction Prompt

Use the following prompt template, replacing `{CAPTIONS}`:

---

You are extracting F&B keywords from Instagram food post captions for a
Hong Kong trending keyword pipeline.

For each caption, extract up to 8 F&B-related keywords. Prioritize:
1. Dish names and cuisine types (肉餅, 沙嗲拼盤, ramen, dim sum)
2. Specific food ingredients (抹茶, matcha, 和牛)
3. Dining formats (放題, omakase, 茶餐廳)
4. Food/drink items (珍珠奶茶, craft beer)
5. Well-known/trending restaurants and food venues (壽司郎, 麥當勞, viral IG cafes)

Do NOT extract: standalone locations (北角, 旺角), non-food activities (唱K, 行山),
generic social media terms (hkfood, 香港美食, foodie, 相機食先), prices/dates.

Captions format: `record_index | caption_text`

{CAPTIONS}

Return ONLY JSON:
```json
{
  "results": [
    { "record_index": 0, "extracted_keywords": ["沙嗲拼盤", "關東煮"] },
    { "record_index": 1, "extracted_keywords": [] }
  ]
}
```

---

### 4. Empty Caption Fallback

If `caption_snippet` is empty, use `raw_payload.hashtags` as source, filtering out
generic hashtags. Most empty-caption records yield few/no keywords.

### 5. Verify

```bash
python3 -c "
import json
with open('runs/YYYY-MM-DD/extracted/instagram_keywords.json') as f:
    data = json.load(f)
records = data['records']
with_kw = sum(1 for r in records if r.get('extracted_keywords'))
print(f'Records: {len(records)}, with keywords: {with_kw}, total keywords: {sum(len(r.get(\"extracted_keywords\",[])) for r in records)}')
"
```

## Error Handling

| Scenario | Action |
|----------|--------|
| Input missing | Abort |
| Empty records | Skip, create empty output |
| LLM fails / malformed JSON | Retry once; if still failing, skip batch |
| Resume after crash | Re-read output file, continue from last index |

## Dependencies

- **Input**: `runs/YYYY-MM-DD/raw/instagram_raw.json` (Step 1)
- **Output**: `runs/YYYY-MM-DD/extracted/instagram_keywords.json` (Step 2B)
