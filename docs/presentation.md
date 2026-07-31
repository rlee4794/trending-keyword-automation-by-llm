#### 5b — 分類表格 (Category Tables)

**Format: Top 10 per enabled category, with short background for each item.**
**Use markdown tables, not bullet lists.**

```
✅ Pipeline done. {len(posts)} posts passed threshold → {len(keywords)} keywords extracted

🔥 Social 熱門菜式（按互動熱度，Top 10）

| 關鍵詞 | Posts | Likes | 背景 |
|--------|-------|-------|------|
| 梅菜扣肉飯 → 梅菜扣肉 | 2 | 67.5K | 源自 7-11 聯乘貼文，兩日內爆發 |
| 沙嗲牛 | 4 | 40.1K | #hkfoodie 及 @girlsfoodies 多位 foodie 提及 |
| 懷舊棉花糖 → 棉花糖 | 4 | 9.8K | 葵廣地下新店重現白兔棉花糖 |

📍 Social 熱門餐廳（按互動熱度，Top 10）

| 餐廳 | Posts | Likes | 背景 |
|------|-------|-------|------|
| 7-11 | 2 | 67.5K | 便利商店聯乘新品引發熱潮 |
| 夜嚐野 | 2 | 27.8K | 深水埗新開宵夜檔，串燒為主 |

🍽️ 熱門菜系（按提及 post 數，Top 10，無需背景）

| 菜系 | Posts |
|------|-------|
| 甜品 | 20 |
| 咖啡 | 12 |

🔍 Google 熱搜關鍵詞（按搜尋量，Top 10）

| 關鍵詞 | Volume | 趨勢 | 相關詞 |
|--------|--------|------|--------|
| 大家樂冬瓜盅 | 200 | 🔥🔍 | 冬瓜盅、大家樂 |
| 富臨漁港 | 2,000 | — | 富临渔港 |

Full data: runs/YYYY-MM-DD/daily_trending_HK.json
```

#### Background extraction rules

For each keyword's background, infer from the associated posts' `caption_snippet`
and `source` fields. Keep it to one short line:
- **Dishes**: mention the source context (聯乘/新開/限時/傳統) and notable platform.
  **Display rule for `concept`**: when a dish keyword has a `concept` field that differs
  from `term`, show it as `term → concept` in the 關鍵詞 column.
  When `concept == term`, show only `term`.
- **Venues**: mention location/type (連鎖/新開/地區) and what they're known for
- **Cuisines**: NO background needed — just list post_count
- **Google**: show `related_terms` as a comma-separated list (exclude the term itself).
  If the term also appears in social keywords, tag `🔥🔍`

#### Google related_terms display rules

Each Google Trends entry now carries a `related_terms` array from the raw data.
When presenting Google results:
- Show `related_terms` inline after the volume, e.g. `— 相關詞：燒鵝, 大家樂`
- Exclude the primary term itself from the display (it's redundant)
- Deduplicate — if the same related term appears multiple times, show it once
- If no related_terms or all are duplicates of the primary term, omit the `— 相關詞：` part

