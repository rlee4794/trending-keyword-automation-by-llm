### Judgment Framework

LLM should consider a keyword luxury if it involves:

| Signal | Examples |
|--------|---------|
| **貴價食材** | 魚子醬、鵝肝、和牛、龍蝦、鮑魚、海膽、松露、花膠、燕窩、西班牙黑豚、貓山王榴槤 |
| **精緻料理形式** | Omakase、割烹、懷石料理、Fine Dining、米芝蓮星級、預約制限定 |
| **溢價體驗** | 人均 $500+、名人飯堂、聯乘限定、過江龍名店、星級名廚客座 |

Exclude: 連鎖快餐、茶餐廳日常、放題/任食（除非主打貴價食材如榴槤放題）、街頭小食。

### Output Format

Agent outputs JSON:

```json
{
  "top_keywords": [
    {"rank": 1, "term": "龍蝦", "type": "dish",
     "key_signal": "鐵板燒$888+預約制龍蝦湯拉麵",
     "post_count": 9, "likes": 22300}
  ],
  "signal_distribution": {
    "🦞 龍蝦": {"count": 2, "representatives": ["龍蝦", "龍蝦汁海膽闊麵"]}
  },
  "summary": {
    "luxury_signal_count": 15,
    "top_trend": "..."
  }
}
```

