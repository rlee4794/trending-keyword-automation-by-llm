#!/usr/bin/env bash
# apify_fetch_threads.sh — Fetch Threads posts via Apify search actor.
#
# Reads config/apify_actors_v1.json for actor_id, input template, and search
# queries. Computes postedAfter (T-31) and postedBefore (T-1), fills the
# input template, and triggers a single actor run with all queries.
#
# Usage:
#   apify_fetch_threads.sh <target_date> [output_path]
#
#   target_date:  YYYY-MM-DD (default: yesterday)
#   output_path:  where to write raw JSON (default: runs/<date>/raw/_apify/threads_apify_raw.json)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_PATH="${PROJECT_ROOT}/config/apify_actors_v1.json"
SOCIAL_CONFIG_PATH="${PROJECT_ROOT}/config/social_listening_v1.json"
APIFY_FETCH="${SCRIPT_DIR}/apify_fetch.sh"

# ── parse args ───────────────────────────────────────────────────────────

if [ $# -ge 1 ]; then
  TARGET_DATE="$1"
else
  TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d)
fi

OUTPUT_PATH="${2:-${PROJECT_ROOT}/runs/${TARGET_DATE}/raw/_apify/threads_apify_raw.json}"

# ── validate ─────────────────────────────────────────────────────────────

if [ ! -f "$CONFIG_PATH" ]; then
  echo "ERROR: Config not found: $CONFIG_PATH" >&2
  exit 1
fi

if [ ! -f "$SOCIAL_CONFIG_PATH" ]; then
  echo "ERROR: Config not found: $SOCIAL_CONFIG_PATH" >&2
  exit 1
fi

if [ -z "${APIFY_TOKEN:-}" ]; then
  echo "ERROR: APIFY_TOKEN environment variable is not set." >&2
  exit 1
fi

# ── compute date range ───────────────────────────────────────────────────

# postedAfter  = T - 31 days
# postedBefore = T - 1 day  (exclusive, so up to yesterday)
POSTED_AFTER=$(date -d "$TARGET_DATE - 31 days" +%Y-%m-%d)
POSTED_BEFORE=$(date -d "$TARGET_DATE - 1 day" +%Y-%m-%d)

echo "[threads] Target date: $TARGET_DATE" >&2
echo "[threads] Date range:  $POSTED_AFTER → $POSTED_BEFORE" >&2

# ── read config ──────────────────────────────────────────────────────────

ACTOR_ID=$(python3 -c "
import json
with open('$CONFIG_PATH') as f:
    cfg = json.load(f)
print(cfg['threads']['actor_id'])
")

INPUT_TEMPLATE=$(python3 -c "
import json
with open('$CONFIG_PATH') as f:
    cfg = json.load(f)
tpl = dict(cfg['threads']['input'])
tpl['postedAfter'] = '$POSTED_AFTER'
tpl['postedBefore'] = '$POSTED_BEFORE'
with open('$SOCIAL_CONFIG_PATH') as f:
    social = json.load(f)
tpl['searchQueries'] = social['broad_seeds']['threads_search_queries']
print(json.dumps(tpl))
")

NUM_QUERIES=$(python3 -c "import json; print(len(json.loads('$INPUT_TEMPLATE')['searchQueries']))")
echo "[threads] Actor: $ACTOR_ID, $NUM_QUERIES search queries" >&2

# ── fetch ────────────────────────────────────────────────────────────────

echo "[threads] Starting actor run..." >&2
bash "$APIFY_FETCH" "$ACTOR_ID" "$INPUT_TEMPLATE" "$OUTPUT_PATH" 600 15

# ── verify ───────────────────────────────────────────────────────────────

if [ -f "$OUTPUT_PATH" ] && [ -s "$OUTPUT_PATH" ]; then
  COUNT=$(python3 -c "import json; print(len(json.load(open('$OUTPUT_PATH'))))")
  echo "[threads] Done: $COUNT posts saved to $OUTPUT_PATH" >&2
else
  echo "[threads] WARNING: Output file is empty or missing: $OUTPUT_PATH" >&2
fi
