---
name: hk-fnb-step-02a-extract-keywords
description: >
  Step 2A of the HK F&B trending keyword pipeline.
  Extracts F&B-related keywords from Instagram post captions using LLM.
  Outputs enriched records with extracted_keywords for downstream filtering.
---

# Step 2A — Instagram Keyword Extraction

**Pipeline position:** after Step 1 (Fetch), before Step 2B (F&B Filter).

## Purpose

Instagram raw data contains `caption_snippet` text (~200 chars) per post.
The raw `raw_term` is the search hashtag (e.g. `#hkfood`), not the actual
content keywords. This step reads each caption and extracts the real F&B
concepts mentioned — dish names, cuisines, ingredients, food trends — so
they can be filtered and ranked in later steps.

## Input

`runs/YYYY-MM-DD/raw/instagram_raw.json`

Each record has:
```json
{
  "raw_term": "#hkfood",
  "source_kind": "hashtag",
  "current_volume": 1,
  "raw_payload": {
    "caption_snippet": "北角真係高手盡在民間...",
    "hashtags": ["香港美食", "hkfood", "北角美食"],
    "likes": 1658,
    "comments": 35,
    "engagement_hint": "medium",
    "geo": "HK",
    "taken_at_timestamp": "2026-06-12T12:20:30+00:00",
    "url": "https://www.instagram.com/reel/...",
    "reshare_count": 2287
  }
}
```

## Output

`runs/YYYY-MM-DD/extracted/instagram_keywords.json`

Same record structure, with an added `extracted_keywords` field:
```json
{
  "raw_term": "#hkfood",
  "source_kind": "hashtag",
  "current_volume": 1,
  "raw_payload": { "caption_snippet": "...", "hashtags": [...], ... },
  "extracted_keywords": ["沙嗲拼盤", "關東煮", "燒蠔", "蒜香茄子"]
}
```

## Project Paths

| Path | Purpose |
|---|---|
| `runs/YYYY-MM-DD/raw/instagram_raw.json` | Input: raw Instagram records with captions |
| `runs/YYYY-MM-DD/extracted/instagram_keywords.json` | Output: records with extracted_keywords |

---

## Procedure

### 1. Check for Resume

Before starting, check if `extracted/instagram_keywords.json` already exists
and has records:

```bash
python3 -c "
import json, os
path = 'runs/YYYY-MM-DD/extracted/instagram_keywords.json'
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print(len(data.get('records', [])))
else:
    print(0)
"
```

If N records already exist, resume from record index N (skip first N records).
If the file does not exist, start from record 0.

### 2. Read Input

Read `raw/instagram_raw.json` and extract the `records` array.
Total records: ~804 (varies per day).

### 3. Batch Processing

Process in batches of **100 records** each.

For each batch:

1. Build the extraction prompt (see below) with the batch's captions.
2. Send the prompt and parse the JSON response.
3. For each record in the batch, add the `extracted_keywords` field.
4. **Append** the batch results to `extracted/instagram_keywords.json`:
   - If first batch: create the file with `{"records": [...]}`.
   - If subsequent batch: read existing file, append new records to the array, write back.
5. Log progress: `[extract] batch N/M done, Y records processed`.

This incremental write ensures that if the Agent crashes mid-run, completed
batches are not lost. On resume, re-read the output file to find the next
unprocessed record index.

### 4. Extraction Prompt

For each batch of 100 records, use this prompt. Replace `{CAPTIONS}` with
the batch's captions in the format shown.

---

You are extracting F&B (Food & Beverage) keywords from Instagram food post captions
for a Hong Kong trending keyword pipeline.

## Task

For each caption below, extract up to 8 F&B-related keywords. Prioritize:

1. **Dish names and cuisine types** (e.g. 肉餅, 杜拜朱古力, 沙嗲拼盤, 酸辣粉, ramen, dim sum)
2. **Specific ingredients with food significance** (e.g. 雞蛋, 抹茶, matcha, 和牛)
3. **Dining formats and food categories** (e.g. 放題, 自助餐, omakase, 茶餐廳)
4. **Food/drink items** (e.g. 珍珠奶茶, craft beer, 手沖咖啡)
5. **Well-known or trending restaurants and food venues** — restaurant names that appear prominently in food content and generate discussion. Include both major chains (e.g. 壽司郎, 麥當勞, 薩莉亞) and notable independent restaurants that are clearly being talked about as food destinations (e.g. a famous dai pai dong, a viral Instagram cafe). If uncertain, err on the side of extracting — downstream filtering will handle borderline cases.

Do NOT extract:
- Location names used standalone (北角, 旺角, 中環, mongkok, causeway bay) — but DO extract location+food compounds like 北角雞蛋仔 where the location is part of a known food concept
- Non-food activities (唱K, 打卡, 行山)
- Generic social media terms (hkfood, 香港美食, foodie, 相機食先)
- Prices, dates, or non-food metadata

## Captions

Format: `record_index | caption_text`

{CAPTIONS}

## Output format

Return ONLY a JSON object. No markdown, no explanation.

```json
{
  "results": [
    {
      "record_index": 0,
      "extracted_keywords": ["沙嗲拼盤", "關東煮", "燒蠔"]
    },
    {
      "record_index": 1,
      "extracted_keywords": ["抹茶蛋糕", "手沖咖啡"]
    },
    {
      "record_index": 2,
      "extracted_keywords": []
    }
  ]
}
```

Rules:
- `record_index` must match the input index exactly.
- If no F&B keywords are found, return an empty array `[]`.
- Return at most 8 keywords per caption, ordered by relevance.
- Keywords should be in their most common form (Chinese or English, as used in the caption).
- Return ONLY the JSON. No markdown, no explanation.

---

### 5. Empty Caption Fallback

If a record has an empty `caption_snippet`, use its `raw_payload.hashtags` as
the source for extraction instead. Apply the same extraction logic: filter out
generic hashtags like `#hkfood`, `#香港美食`, `#foodie`, `#相機食先`, and keep
only specific F&B hashtags (e.g. `#北角美食` → extract `北角美食`, but then
simplify to remove location: `美食` is too generic → discard).

In practice, most empty-caption records will yield few or no keywords. That's
expected — these posts contribute little signal.

### 6. Complete

After all batches are processed, verify:

```bash
python3 -c "
import json
with open('runs/YYYY-MM-DD/extracted/instagram_keywords.json') as f:
    data = json.load(f)
records = data['records']
total = len(records)
with_kw = sum(1 for r in records if r.get('extracted_keywords'))
total_kw = sum(len(r.get('extracted_keywords', [])) for r in records)
print(f'Records: {total}')
print(f'Records with keywords: {with_kw}')
print(f'Total keywords extracted: {total_kw}')
"
```

---

## Error Handling

| Scenario | Action |
|---|---|
| `instagram_raw.json` missing | Abort. Log error. |
| Empty records array | Skip step, create empty output. |
| Batch LLM call fails | Retry once. If still failing, skip batch and log. |
| LLM returns malformed JSON | Retry batch with stricter prompt. If still failing, skip. |
| Resume after crash | Re-read output file, continue from last processed index. |

---

## Token Budget

| Item | Estimate |
|---|---|
| 100 captions (~200 chars each) | ~20K chars input |
| Extraction prompt + instructions | ~2K chars |
| JSON response (100 × avg 5 keywords) | ~5K chars output |
| **Per batch** | **~27K tokens** |
| **8 batches total** | **~220K tokens** |

---

## Dependencies

- **Input from Step 1**: `runs/YYYY-MM-DD/raw/instagram_raw.json`
- **Output to Step 2B**: `runs/YYYY-MM-DD/extracted/instagram_keywords.json`
