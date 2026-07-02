# Step 1–3 對接審視總結

> 審視日期：2026-06-29
> 範圍：`skills/01-fetch/` → `skills/02a-extract-keywords/` → `skills/02b-filter-fnb/` → `skills/03-normalize/`

---

## 管線全景

```
Step 1 (Fetch)
  ├─ Apify Google Trends ──→ raw/google_raw.json
  └─ Apify Instagram (×4) ──→ raw/instagram_raw.json
                                    │
Step 2A (Extract Keywords) ←────────┘
  └─ LLM 從 captions 提取關鍵詞 ──→ extracted/instagram_keywords.json
                                    │
Step 2B (F&B Filter) ←──────────────┘  + raw/google_raw.json
  ├─ LLM 分類 F&B / 非 F&B
  ├─ Google: 過濾 records ──→ filtered/google_filtered.json
  └─ Instagram: 合併 extracted_keywords + hashtags → 統一 `terms` 欄位
       └─ filtered/instagram_filtered.json
                                    │
Step 3 (Normalize) ←─────────────────┘
  ├─ 3a: Python exact match → matched_groups.json + unmatched_review_queue.csv
  ├─ 3b: Agent batch review (MERGE/CREATE/DISCARD)
  ├─ 3c: Merge decisions → append canonical_mapping.csv
  └─ 3d: Re-normalize → final matched_groups.json → Step 5
```

---

## 發現的 7 個對接斷層

### 🔴 #1：Step 2A 的 extracted_keywords 在 Step 3 完全被忽略

- **問題：** Step 3a 讀 `raw/instagram_raw.json`，提取 `raw_payload.hashtags[]`，完全不用 Step 2A 花 ~220K tokens 提取的 `extracted_keywords`
- **修復：** Step 3 改讀 `filtered/instagram_filtered.json`，使用統一的 `terms` 欄位

### 🔴 #2：Step 3 讀 `raw/` 而非 `filtered/`

- **問題：** Step 3a 路徑指向 `raw/`，繞過 Step 2B 的 F&B 過濾
- **修復：** 路徑改為 `filtered/`，Google 和 Instagram 都先經過 Step 2B 再到 Step 3

### 🟡 #3：Instagram hashtags 未經 Step 2B 過濾

- **問題：** Step 2B 只過濾 extracted_keywords，hashtags 原封不動保留，會繞過 F&B gate
- **修復：** Step 2B 同時接收 extracted_keywords + hashtags，合併分類後輸出統一 `terms` 欄位

### 🟡 #4：Step 3a unmatched 邏輯在新方案下會漏失

- **問題：** 原邏輯是「逐 record 判斷」——只要有一個 term 匹配，其他 unmatched terms 全部被靜默丟棄
- **修復：** 改為「逐 term 判斷」，每個 term 獨立匹配或進入 unmatched queue

### 🟡 #5：Step 2B record drop 邏輯過嚴

- **問題：** 如果 extracted_keywords 全部被過濾掉，整條 record 被丟棄，即使 hashtags 有有效 F&B term
- **修復：** 合併 extracted_keywords + hashtags 後再判斷是否保留 record

### 🟡 #6：`_filter` metadata 傳遞策略

- **決策：** `_filter` 止於 Step 2B，不往下游傳遞（解耦優先）

### 🟡 #7：Volume 語義接受新方案

- **現狀：** 一篇 post 的 signal 分散到多個 canonical key（各 +1）
- **決策：** 接受此 trade-off，不調整 volume 計算

---

## Step 1 獨立審視（5 個 gap）

| # | Gap | 處理 |
|---|---|---|
| 1 | Config 檔名不一致（`apify_actors.json` vs `_v1`） | ✅ 全部改為 `_v1` 版本 |
| 2 | `expansion_terms` 永遠為空，管線無消費者 | ✅ 從 schema 移除 |
| 3 | Apify 參數硬編碼在 shell 指令裡 | ✅ 移到 `apify_actors_v1.json` 的 `input` 欄位 |
| 4 | `normalize_raw.py` 的 `--config` contract 描述不精確 | ✅ 修正為 "for broad_seed_group metadata" |
| 5 | Instagram `raw_term` 是 dead field | ✅ 保留（追蹤用 metadata） |

---

## 修改的檔案

| 檔案 | 變更摘要 |
|---|---|
| `skills/02b-filter-fnb/SKILL.md` | Input 加 hashtags、產出改 `terms` 欄位、record drop 邏輯修正、`_filter` 欄位更新、token budget 調整 |
| `skills/03-normalize/SKILL.md` | 讀取路徑 `raw/`→`filtered/`、Instagram 來源改 `terms`、逐 term 匹配、Dependencies/Error Handling 更新 |
| `skills/01-fetch/SKILL.md` | Config 檔名 `_v1`、移除 `expansion_terms`、Apify 參數改從 config 讀、contract 描述修正 |
| `config/apify_actors_v1.json` | 新增 `input` 欄位（Google Trends + Instagram actor 參數） |
| `scripts/apify_fetch.sh` | **新建** — Apify API 完整交互（啟動/poll/下載） |
| `scripts/normalize_raw.py` | **新建** — 獨立 normalize 腳本，mirror `social_pipeline/apify.py` |

---

## 設計決策記錄

| 決策 | 選擇 | 理由 |
|---|---|---|
| Fuzzy match 層 | 不加 | Agent 為主軸，Python 只做 exact match |
| `_filter` 傳遞 | 止於 Step 2B | 解耦，避免下游 schema 膨脹 |
| `record_count` 語義 | 匹配次數（非 post 數） | 一篇 post 多個 term 命中同一 key 多次遞增 |
| `raw_term` (Instagram) | 保留 | 追蹤用 metadata，不影響排名 |
| 腳本實現時機 | 先對接、後實現 | contract 先對，避免重寫 |

---

## 待辦

- [ ] Step 4–6 對接審視（另開 session）
- [ ] `scripts/apify_fetch.sh` 與 `scripts/normalize_raw.py` 在實際 Apify 環境中端到端測試
