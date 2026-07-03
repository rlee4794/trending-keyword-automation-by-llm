<!--
  review-prompt.md — Static classification prompt template for Step 4 (LLM Review).
  Agent reads this template, replaces {ANCHORS} and {TERMS} with live data,
  then classifies each term as CREATE / MERGE / DISCARD.
-->

You are reviewing unmatched social media terms from a Hong Kong F&B trending keyword pipeline.

Your job: classify each term below into one of three actions.

## Existing canonical keys:

{ANCHORS}

Format: `canonical_key | display_term | description`
(description may be empty for legacy keys)

## Terms to review:

{TERMS}

Format: `suggested_cleanup_term | platform`

## Normalization policy

Canonical keys must represent portable F&B concepts or notable F&B venues,
not locations, non-F&B brands, campaigns, or decorated search phrases.

Before choosing an action, mentally simplify each term:
- Remove district/location qualifiers (旺角, 尖沙咀, 上環, 沙田, 中環, 北角, etc.)
- Remove generic suffixes (系列, 必備, 配料, 推介, 推薦, 攻略, 合集)
- Keep the underlying F&B concept if one remains

## Classification rules

**MERGE** — The term is a variant, translation, alias, district-qualified phrase,
or decorated phrase for an EXISTING canonical key. Set `target_canonical_key` to
the existing key.

MERGE only when the term and target canonical key are TRUE SYNONYMS
(translations, spelling variants, abbreviations, district-qualified phrases,
or decorated phrases of the SAME concept).

⚠️ Semantic hierarchy check — before MERGE, verify the relationship:

1. If the term is a BROADER concept than the target canonical key
   → DO NOT MERGE. CREATE a new key instead.
   Example: "韓國菜" is broader than "korean-bbq" (韓燒只是韓國菜的一種)
            → CREATE korean-food, don't MERGE into korean-bbq
   Example: "粵菜" is broader than "cantonese-restaurant" (粵式酒樓只是粵菜的一種)
            → CREATE cantonese-food, don't MERGE

2. If the term is a NARROWER concept than the target canonical key
   → DO NOT MERGE. CREATE a new key instead.
   Example: "拌麵" is narrower than "noodles" (拌麵是具體菜式，麵食是泛稱)
            → CREATE lo-mein, don't MERGE into noodles
   Example: "豚丼" is narrower than "donburi" (豚丼是丼飯的一種但本身是獨立菜式)
            → CREATE butadon, don't MERGE into donburi

3. If the term and target are DIFFERENT concepts entirely
   → DO NOT MERGE. CREATE a new key (or DISCARD if noise).
   Example: "海膽" (ingredient) ≠ "uni-pasta" (pasta dish)
            → CREATE sea-urchin, don't MERGE into uni-pasta
   Example: "咖啡" (beverage) ≠ "coffee-shop" (venue type)
            → CREATE coffee, don't MERGE into coffee-shop

Examples of VALID MERGE (true synonyms):
- "旺角cafe" → MERGE target_canonical_key="coffee-shop"
- "尖沙咀cafe" → MERGE target_canonical_key="coffee-shop"
- "火鍋配料" → MERGE target_canonical_key="hotpot"
- "打邊爐必備" → MERGE target_canonical_key="hotpot"
- "すき焼き" → MERGE target_canonical_key="sukiyaki"
- "壽喜燒" → MERGE target_canonical_key="sukiyaki"

**CREATE** — The simplified term is a distinct reusable HK F&B concept (food,
drink, cuisine, dish, ingredient, dining format, cooking style, or generic
restaurant category) AND is NOT a variant of any existing canonical key.
Generate a short English slug as `canonical_key` (lowercase, hyphens, no special chars).
The `display_term` should be a clean user-facing F&B concept name, using the most
common Chinese or English form. Remove district names, generic suffixes, and
campaign words from display_term. Do not set display_term to canonical_key unless
that is genuinely the natural public label.

Also provide `enriched_description`: a one-sentence description of the F&B concept
in English. Example: "Japanese hot pot with thinly sliced beef, common in HK放題 restaurants"

Also assign a `category` for every CREATE:
- `fnb` — dishes, cuisines, dining formats, ingredients, drinks, cooking styles
  (e.g. 酸辣粉, omakase, 酒吧, 抹茶, 肉餅, 自助餐)
- `poi` — restaurants, food shops, chain F&B brands
  (e.g. 壽司郎, 九記牛腩, 麥當勞, KFC)
- `location` — places, malls, districts with F&B relevance but not themselves eateries
  (e.g. 希慎廣場, 廟街, 蘭桂坊)

If unsure between fnb/poi, prefer fnb for concepts and poi for named venues.

Also assign a `potential` for every CREATE:
- `high` — specific dish/ingredient/format/landmark that can be pointed to on a menu or map
  (e.g. 酸辣粉, 杜拜朱古力, 半島酒店, 潮州打冷, 慢煮牛舌, 爆檸)
- `medium` — restaurant brand/chain name (not a dish, not a landmark)
  (e.g. 壽司郎, 鮨政, 吉野家)
- `low` — broad food categories, district names, generic concepts
  (e.g. 日本菜, 燒肉, 沙田美食, 放題, 甜品)

NEVER CREATE canonical keys for:
- Brands that are not primarily F&B (Godiva is borderline-F&B → keep; Nike, TCL, Biore, BRUNO → discard)
- Overly generic terms (香港美食, hkfood, hongkongfood, food, hk, 美食,
  香港, hongkong, 食好西, 吃貨, foodie, yummy)
- Location-only terms (旺角, 中環, 尖沙咀, causewaybay, mongkok)
- Non-F&B terms (港珠澳大橋, cctv 5, 手袋維修, 隱形眼鏡, 瑜伽)

Restaurant/venue names are ALLOWED as CREATE candidates IF they are:
- Major chains with significant HK F&B presence (e.g. 壽司郎, 麥當勞, 美心, 大家樂, 譚仔)
- Notable independent restaurants that are clearly trending in the data
  (high frequency across multiple days, strong engagement, multi-platform presence)
- For trending independent venues: use the restaurant's commonly-known name as
  `display_term`, and include "HK restaurant/venue" context in `enriched_description`.
  Only CREATE if the venue shows clear trending signal (appears across multiple
  days/platforms, not a one-off mention).
- Obscure single-mention restaurant names → DISCARD as noise.

**DISCARD** — The term is: not F&B related, not HK-local, too generic, a district-only term, a brand advertisement for non-F&B products, non-food hashtag spam, campaign text, garbage text, or an obscure single-mention restaurant with no trending signal.

Examples:
- "香港美食" → DISCARD reason="too generic"
- "hkfood" → DISCARD reason="too generic"
- "沙田美食" → DISCARD reason="district-qualified generic food term"
- "港珠澳大橋" → DISCARD reason="not F&B"
- "cctv 5" → DISCARD reason="not F&B"
- "TCL" → DISCARD reason="non-F&B brand"
- "隱形眼鏡" → DISCARD reason="not F&B"
- "阿強小食" → DISCARD reason="obscure single-mention restaurant" (only if truly a one-off with no trending signal)

## Output format

Return ONLY a JSON object with a "decisions" array. No markdown, no explanation.

```json
{
  "decisions": [
    {
      "suggested_cleanup_term": "酸辣粉",
      "platform": "google",
      "action": "CREATE",
      "canonical_key": "hot-sour-noodles",
      "display_term": "酸辣粉",
      "enriched_description": "Spicy and sour glass noodle soup, popular HK street food",
      "category": "fnb",
      "potential": "high"
    },
    {
      "suggested_cleanup_term": "旺角cafe",
      "platform": "instagram",
      "action": "MERGE",
      "target_canonical_key": "coffee-shop"
    },
    {
      "suggested_cleanup_term": "九記牛腩",
      "platform": "instagram",
      "action": "CREATE",
      "canonical_key": "kau-kee-beef-brisket",
      "display_term": "九記牛腩",
      "enriched_description": "Iconic HK beef brisket noodle shop in Central, frequently trending on social media",
      "category": "poi",
      "potential": "medium"
    },
    {
      "suggested_cleanup_term": "港珠澳大橋",
      "platform": "google",
      "action": "DISCARD",
      "reason": "not F&B"
    },
    {
      "suggested_cleanup_term": "cctv 5",
      "platform": "google",
      "action": "DISCARD",
      "reason": "not F&B"
    },
    {
      "suggested_cleanup_term": "香港美食",
      "platform": "instagram",
      "action": "DISCARD",
      "reason": "too generic"
    },
    {
      "suggested_cleanup_term": "阿強小食",
      "platform": "instagram",
      "action": "DISCARD",
      "reason": "obscure single-mention restaurant"
    }
  ]
}
```

Rules:
- `suggested_cleanup_term` must match the input term exactly.
- `platform` must be `"google"` or `"instagram"`.
- For CREATE: include `canonical_key`, `display_term`, `enriched_description`, `category` (one of: `fnb`, `poi`, `location`), and `potential` (one of: `high`, `medium`, `low`).
- For MERGE: include `target_canonical_key` (must be an existing key from the list above).
- For DISCARD: include `reason` (short label explaining why).
- Classify ALL terms. Return ONLY the JSON.
