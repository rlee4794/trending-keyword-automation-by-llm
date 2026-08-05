#### 5b — 分類表格 (Category Tables)

**Format: Top 30 per enabled category, with short background for each item.**
**Use markdown tables, not bullet lists.**

```
✅ Pipeline done. {len(posts)} posts passed threshold → {len(keywords)} keywords extracted

🔥 Social 熱門菜式（按互動熱度，Top 30）

| 關鍵詞 | Posts | Likes | 背景 |
|--------|-------|-------|------|
| 梅菜扣肉飯 → 梅菜扣肉 | 2 | 67.5K | 7-11 聯乘限定新品，兩日內於 IG 爆發，便利店預製食品罕見高熱度 |
| 沙嗲牛 | 4 | 40.1K | #hkfoodie 及 @girlsfoodies 多位 foodie 反覆提及，茶餐廳經典持續發酵 |
| 懷舊棉花糖 → 棉花糖 | 4 | 9.8K | 葵廣地下新店「甜絲絲」重現白兔棉花糖，Threads 尋味帖引爆 nostalgia |

📍 Social 熱門餐廳（按互動熱度，Top 30）

| 餐廳 | Posts | Likes | 背景 |
|------|-------|-------|------|
| 7-11 | 2 | 67.5K | 全港連鎖便利店，聯乘限定食品引發社交媒體罕見高互動 |
| 夜嚐野 | 2 | 27.8K | 深水埗新開宵夜檔，主打串燒及創意小食，凌晨營業吸夜貓客 |

🍽️ 熱門菜系（按提及 post 數，Top 30，無需背景）

| 菜系 | Posts |
|------|-------|
| 甜品 | 20 |
| 咖啡 | 12 |

🔍 Google 熱搜關鍵詞（按搜尋量，Top 30）

| 關鍵詞 | Volume | 趨勢 | 相關詞 |
|--------|--------|------|--------|
| 大家樂冬瓜盅 | 200 | 🔥🔍 | 冬瓜盅、大家樂 |
| 富臨漁港 | 2,000 | — | 富临渔港 |

Full data: runs/YYYY-MM-DD/daily_trending_HK.json
```

#### Background extraction rules

For each keyword's background, infer from the associated posts' `caption_snippet`
and `source` fields. **Each background must be 50-70 characters** (CJK count),
packing in: restaurant/venue name, context (聯乘/新開/限時/傳統), and platform.

- **Dishes**: 50-70字。格式: `[{source}] {餐廳名} {context}，{特色/反應}`
  必須包含餐廳/店名（從 caption 提取，沒有確切名稱則用區域名+類型如「大角咀街坊麵包店」）。
  **Display rule for `concept`**: when a dish keyword has a `concept` field that differs
  from `term`, show it as `term → concept` in the 關鍵詞 column.
  When `concept == term`, show only `term`.
- **Venues**: 50-70字。格式: `[{地區}] {類型}，{招牌菜/特色}，{context}`
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

