You are extracting trending F&B keywords from Hong Kong social media posts
and Google Trends data. Your output drives a daily HK food trends report.

## Task

For each post below, extract:

1. **Dishes** (優先) — specific dish names. Keep the full name with modifiers:
   "蝦拉麵" NOT "拉麵", "冰鎮咕嚕肉" NOT "咕嚕肉", "沙嗲牛肉麵" NOT "沙嗲".
   Include: individual dishes, desserts, drinks, baked goods, specific food items.

   **For each dish, also output a `concept`** — a generalized version that strips
   **marketing noise** but keeps **food-attribute modifiers**:

   For **specific (non-aggregate) keywords**: `concept` strips marketing noise from `term`.
   For **aggregate keywords**: `concept` is the broad category (雪糕, 串燒, 西多士).

   | Strip (marketing noise) | Keep (food attributes) |
   |--------------------------|------------------------|
   | Brand names: KFC, 麥當勞, 7-11 | Ingredients: 龍蝦, 和牛, 斑蘭 |
   | Campaign/seasonal: 紫色(EVA聯乘), 至尊(product line), 期間限定 | Cooking methods: 沙嗲, 鐵板, 冰鎮 |
   | Promotional adjectives: 懷舊, 激抵, 超值 | Flavors: 麻辣, 蒜蓉, 朱古力 |
   | Co-branding markers: × EVA, × Chiikawa | Dish type: 拉麵, 漢堡, 年糕 |

   **Examples:**
   - "紫色巴辣雞腿包" → concept: "巴辣雞腿包" (strip 紫色=聯乘色)
   - "至尊漢堡" → concept: "安格斯牛肉漢堡" (strip 至尊=product line, keep core)
   - "朱古力班戟豬柳蛋漢堡" → concept: "豬柳蛋漢堡" (strip 朱古力班戟=McGriddles variant)
   - "懷舊棉花糖" → concept: "棉花糖" (strip 懷舊=promotional adjective)
   - "龍蝦湯拉麵" → concept: "龍蝦湯拉麵" (no change — 龍蝦 is ingredient, keep)
   - "沙嗲牛肉麵" → concept: "沙嗲牛肉麵" (no change — already a clean food concept)
   - "牛油年糕" → concept: "牛油年糕" (no change — 牛油 is ingredient, keep)

   If the dish name is already a clean food concept with no marketing noise,
   `concept` should equal the dish name exactly.

2. **Venues** (優先) — restaurant names, cafe names, food venues, food streets,
   dai pai dong, markets with food significance. Must be at least 2 characters.
   Include both chains (壽司郎, 麥當勞, 薩莉亞) and notable independents.
   A venue is a PROPER NOUN — if it's a common Chinese word that could appear
   in any sentence (不, 的, 好, 是, 有, 食, 飲, 去, 來, 我, 你, 他, 她, 很,
   個, 種, 啲, 嘅, 咁, 仲, 未, 冇, 無, 係, 喺, 俾, 畀, 令, 將, 但, 只,
   已, 更, 最, 都, 就, 也, 會, 要, 可, 又, 或, 與, 及), it is NOT a venue.

   **Extracting venues from lists and markers:**
   - Numbered/bullet lists of restaurants → extract each as a venue.
     Example: "1. 牛奶冰室 2. 蜜雪冰城 3. 百分百餐廳" → venues: [牛奶冰室, 蜜雪冰城, 百分百餐廳]
   - 📍 followed by a name → extract as venue.
     Example: "📍Picanhas' 中環伊利近街" → venues: [Picanhas']
   - Restaurant name + food description → extract the name.
     Example: "紅磡炒得喜 超大盆花甲蒸蛋！！" → venues: [紅磡炒得喜]

3. **Cuisines** (次要) — cuisine types or food categories: 日本菜, 泰國菜, 川菜,
   dim sum, ramen, omakase, 放題, 茶餐廳, 打邊爐, 燒烤.

4. **geo_by_content** (必須) — where the food/venue is physically located.
   Output a **free-form location tag**, NOT a yes/no bucket.

   **⚠️ CRITICAL: The food's physical location determines geo. NOT the author, NOT the language, NOT the hashtags.**

   - `"HK"` — food/venue is IN Hong Kong (香港地名、港式用語、香港分店、$HKD 標價)
   - `"TW"` — food/venue is IN Taiwan (台灣地名如一中街/逢甲/西門町、台灣手機格式 09xx-xxx-xxx、
     台灣分店命名如XX店/XX分店、台幣 NT$ 標價、台灣特有品牌)
   - `"JP"` — food/venue is IN Japan (大阪、東京、京都、札幌、沖縄、📍東京…)
   - `"KR"` — food/venue is IN Korea (首爾、釜山、明洞…)
   - `"TH"` — food/venue is IN Thailand (曼谷、清邁、布吉…)
   - `"MO"` — food/venue is IN Macau
   - `"CN"` — food/venue is IN Mainland China (深圳、上海、北京…)
   - `"SG"` — food/venue is IN Singapore
   - `"MY"` — food/venue is IN Malaysia
   - `null` — truly cannot determine (e.g. pure food photo with no location clues)

   **Red flags that mean NOT HK (common pitfall):**
   - "📍東京" anywhere in caption → `"JP"` (Tokyo = Japan, always)
   - "東京最新" / "東京超巨大" / "Tokyo's" / "Tokyo" → `"JP"`
   - "📍大阪" / "📍京都" / "📍札幌" → `"JP"`
   - ¥ (yen) pricing with Japanese location → `"JP"`
   - NT$ pricing → `"TW"`
   - 深圳地名 (福田/南山/羅湖/宝安) → `"CN"`
   - 曼谷/曼谷地名 → `"TH"`

   **HK indicators (only tag HK if food IS in HK):**
   - HKD pricing, 香港地名, 港式用語, 香港分店地址
   - $XX蚊, HK$XX, 港幣

   If a post mentions both regions (e.g. "香港人去台北食XXX"),
   classify by where the FOOD is served, not the author's location.
   If a post says "傳給你想一起去東京旅行的人" or "傳給想去東京的",
   the food IS in Tokyo → `"JP"`.

**DO NOT extract:**
- Single characters as venues or dishes — minimum 2 characters required.
  A single Chinese character is almost never a restaurant name or dish.
  The rare exceptions (like the restaurant '不' at 北角錦屏街) appear
  ONLY in location/address contexts (📍不, 🗺️ address). If a single
  character appears mid-sentence as a common word, do NOT extract it.
- Common Chinese function words / adverbs / conjunctions as venues or dishes:
  不, 的, 了, 是, 在, 有, 和, 都, 就, 也, 會, 要, 可, 好, 食, 飲, 去, 來,
  我, 你, 他, 她, 很, 個, 種, 啲, 嘅, 咁, 仲, 未, 冇, 無, 係, 喺, 俾, 畀,
  令, 將, 但, 只, 已, 更, 最, 又, 或, 與, 及
- Vague/generic terms as standalone per-post dishes: 好味, 美食, 必食, 好食, 好西, 香港, foodie, foodporn, yum.
  **Exception for aggregate keywords**: category-level terms like 雪糕, 串燒, 西多士, 榴槤, 拉麵
  are VALID as aggregate keywords when they group multiple specific dish variants across posts.
- Standalone locations without food context: 北角, 旺角, 中環, mongkok, causeway bay
- Non-food activities: 唱K, 行山, 打卡, yoga
- Generic social media tags: hkfood, 香港美食, 相機食先, hkfoodie
- Shop/brand names that look like food — if a term appears alongside
  開幕/插旗/進駐/新店/排隊/分店/試業/開張 without describing the food
  itself, it's a VENUE, not a dish. Examples: 夏茶, 五桐號, 龜記,
  天仁茗茶, 吃茶三千, 牛大人, 板神, 鼎泰豐, 鴻福堂. These are brands
  that happen to sell food/drinks — do NOT extract them as dishes.

**Naming rules:**
- Use the most common Hong Kong Chinese name: 壽司郎 not Sushiro, 麥當勞 not McDonald's
- For English-only concepts, keep English: craft beer, omakase, ramen
- Mixed terms OK: 和牛burger, DIY燒肉

## Posts

Format: `[N] platform | source | likes ❤️ | comments 💬 | shares 🔄`

**Threads-specific notes:** Threads posts are shorter and more conversational
than Instagram. They rarely use hashtags. Pay extra attention to:
- Numbered/bullet lists of restaurants or dishes (e.g. "1. 牛奶冰室 2. 蜜雪冰城")
- Venue names after 📍 markers (e.g. "📍Picanhas'")
- Standalone restaurant names followed by food descriptions
  (e.g. "紅磡炒得喜 超大盆花甲蒸蛋！！")
- Dish names in short declarative sentences
  (e.g. "推薦一間中環附近嘅牛排午餐")

{CAPTIONS}

## Google Trends

{GOOGLE_TERMS}

## Output

Return ONLY JSON. No markdown, no explanation.

```json
{
  "posts": [
    {
      "index": 0,
      "dishes": ["沙嗲拼盤", "燒蠔"],
      "venues": ["北角串燒店"],
      "cuisines": ["串燒"],
      "geo_by_content": "HK"
    },
    {
      "index": 1,
      "dishes": ["豬排", "千層酥"],
      "venues": ["KYK", "grenier"],
      "cuisines": ["日本菜", "咖啡"],
      "geo_by_content": "JP"
    }
  ],
  "keywords": [
    {
      "term": "沙嗲拼盤",
      "concept": "沙嗲拼盤",
      "type": "dish",
      "post_indices": [0, 3, 7]
    },
    {
      "term": "雪糕",
      "concept": "雪糕",
      "type": "dish",
      "post_indices": [2, 4, 8, 11, 15]
    },
    {
      "term": "壽司郎",
      "type": "venue",
      "post_indices": [1, 4, 5, 8, 12]
    },
    {
      "term": "日本菜",
      "type": "cuisine",
      "post_indices": [1, 6, 9]
    }
  ]
}
```

Rules:
- `dishes`, `venues`, `cuisines` arrays — empty `[]` if nothing found
- `geo_by_content` — free-form location tag (e.g. `"HK"`, `"TW"`, `"JP"`, `"KR"`, …) or `null`
- `keywords[].post_indices` — which posts mention this keyword (0-based)
- `keywords[].type` — "dish", "venue", or "cuisine"
- `keywords[].concept` — **required for `type: "dish"`**, omit for venue/cuisine. Generalized food concept stripped of marketing noise (brands, campaigns, promotional adjectives) but keeping food-attribute modifiers (ingredients, cooking methods, flavors, dish type). Equal to `term` if the dish name is already clean.
- Google Trends terms: only include if they are **specific F&B proper nouns** — named dishes (至尊漢堡, 大家樂冬瓜盅), named venues (富臨漁港), or named brands (McGriddles, McDonald). Omit generic category words (套餐, 麵包, 榴槤), supermarket/retail names (百佳超級市場), and non-F&B terms entirely. Included terms get `post_indices: []`

### ⚠️ Aggregate Keywords (MANDATORY)

You MUST create **aggregate keywords** that group related specific dishes under a
common food concept. These are the PRIMARY output for trend reporting — they show
broad trends, not just individual dish variants.

**How it works:**
1. Extract specific dish names per post as usual (芫茜雪糕, 大蒜雪糕, 開心果Gelato, 鵝肝雪糕)
2. Group dishes sharing the same **core food identity** into an aggregate keyword
3. The aggregate `term` is the most representative/common name (雪糕)
4. `post_indices` is the UNION of all variant posts (no duplicates)
5. The aggregate replaces the individual variants in the keywords array

**When to aggregate:**
- Same base food with different flavors/toppings: 芫茜雪糕 + 大蒜雪糕 + 開心果Gelato + 鵝肝雪糕 → aggregate "雪糕"
- Same dish type with different proteins/sauces: 沙爹串燒 + 鹽燒多春魚 + 燒雞肉串 + 燒鰻魚肝 → aggregate "串燒"
- Same dish with different regional/brand variants: 黑芝麻漏奶西多士 + 抹茶漏奶西多士 + 蘋果肉桂西多士 → aggregate "西多士"
- Same ingredient appearing across dishes: 貓山王榴槤月餅 + D24榴槤卡邦尼 + 榴奶冰 + 榴槤放題 → aggregate "榴槤"

**When NOT to aggregate (keep separate):**
- Distinct dishes even if same cuisine: 冬陰功 vs 青木瓜沙律 → separate (different dish identity)
- Different cooking format changes the dish: 鐵板燒鮑魚 vs 酒醉鮑魚 → separate
- Named signature dishes with strong brand identity: 巴辣雞腿包 (KFC EVA聯乘) → keep separate
- Dishes with unique concept/format that define their own trend: 拿坡里黑手黨意粉 (Netflix聯乘) → keep separate

**Aggregate term naming:**
- Use the most common HK Chinese name: 雪糕 not 冰淇淋, 串燒 not 烤串
- Keep English if that's the dominant term: Omakase, Gelato
- If a specific variant dominates (>70% of posts), the aggregate `term` can be that variant
  (e.g. if 15/20 雪糕 posts are 開心果Gelato, term can be "開心果Gelato")
- Return ONLY the JSON

---

