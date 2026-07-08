#!/usr/bin/env bash
# apify_fetch.sh — Trigger an Apify actor, poll until complete, download dataset.
#
# Usage: apify_fetch.sh <actor_id> <input_json> <output_path> [timeout_secs] [poll_interval_secs]
#
# Behavior:
# - POST to start actor run → get runId
# - Poll GET every N seconds until SUCCEEDED/FAILED/ABORTED/TIMED-OUT
# - On SUCCEEDED: fetch dataset items, write to output_path, exit 0
# - On FAILED/ABORTED/TIMED-OUT: exit 1
# - On timeout: exit 1
# - On empty dataset: write [] to output_path, exit 0
# - Retry up to 2 additional times on actor start failure (404, 5xx, network error)
set -euo pipefail

ACTOR_ID="${1:?Usage: apify_fetch.sh <actor_id> <input_json> <output_path> [timeout_secs] [poll_interval_secs]}"
INPUT_JSON="${2:?}"
OUTPUT_PATH="${3:?}"
TIMEOUT_SECS="${4:-300}"
POLL_INTERVAL="${5:-10}"

APIFY_BASE="https://api.apify.com/v2"
TOKEN="${APIFY_TOKEN:?APIFY_TOKEN environment variable is not set}"

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT_PATH")"

# ---------------------------------------------------------------------------
# Helper: call Apify API with retry on transient errors
# ---------------------------------------------------------------------------
_apify_call() {
  local method="$1" url="$2" data="${3:-}"
  local attempt=0 max_attempts=2

  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    local http_code
    if [ -n "$data" ]; then
      http_code=$(curl -s -w "%{http_code}" -o /tmp/apify_resp_$$.json \
        -X "$method" "$url" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "$data" 2>/dev/null)
    else
      http_code=$(curl -s -w "%{http_code}" -o /tmp/apify_resp_$$.json \
        -X "$method" "$url" \
        -H "Authorization: Bearer $TOKEN" 2>/dev/null)
    fi

    # 5xx → retry; 4xx → fail immediately
    if [ "$http_code" -ge 500 ] 2>/dev/null; then
      if [ $attempt -lt $max_attempts ]; then
        echo "[apify_fetch] HTTP $http_code, retrying (attempt $attempt/$max_attempts)..." >&2
        sleep 2
        continue
      fi
    fi

    echo "$http_code"
    return
  done
}

# ---------------------------------------------------------------------------
# Step 1: Start actor run (with retry: up to 3 total attempts)
# ---------------------------------------------------------------------------
MAX_START_ATTEMPTS=3
START_URL="${APIFY_BASE}/acts/${ACTOR_ID}/runs?token=${TOKEN}"

START_ATTEMPT=0
while [ $START_ATTEMPT -lt $MAX_START_ATTEMPTS ]; do
  START_ATTEMPT=$((START_ATTEMPT + 1))
  echo "[apify_fetch] Starting actor: $ACTOR_ID (attempt $START_ATTEMPT/$MAX_START_ATTEMPTS)" >&2
  HTTP_CODE=$(_apify_call "POST" "$START_URL" "$INPUT_JSON")

  if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "200" ]; then
    break
  fi

  echo "[apify_fetch] WARNING: Failed to start actor (HTTP $HTTP_CODE)" >&2
  cat /tmp/apify_resp_$$.json >&2
  rm -f /tmp/apify_resp_$$.json

  if [ $START_ATTEMPT -lt $MAX_START_ATTEMPTS ]; then
    SLEEP_SECS=$((START_ATTEMPT * 3))
    echo "[apify_fetch] Retrying in ${SLEEP_SECS}s..." >&2
    sleep $SLEEP_SECS
  fi
done

if [ "$HTTP_CODE" != "201" ] && [ "$HTTP_CODE" != "200" ]; then
  echo "[apify_fetch] ERROR: Failed to start actor after $MAX_START_ATTEMPTS attempts" >&2
  exit 1
fi

RUN_ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/apify_resp_$$.json'))['data']['id'])")
echo "[apify_fetch] Run started: $RUN_ID" >&2

# ---------------------------------------------------------------------------
# Step 2: Poll until terminal status
# ---------------------------------------------------------------------------
POLL_URL="${APIFY_BASE}/acts/${ACTOR_ID}/runs/${RUN_ID}?token=${TOKEN}"
ELAPSED=0
STATUS="RUNNING"

while [ "$ELAPSED" -lt "$TIMEOUT_SECS" ]; do
  sleep "$POLL_INTERVAL"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))

  HTTP_CODE=$(_apify_call "GET" "$POLL_URL")
  if [ "$HTTP_CODE" != "200" ]; then
    echo "[apify_fetch] WARNING: Poll returned HTTP $HTTP_CODE" >&2
    continue
  fi

  STATUS=$(python3 -c "import json,sys; d=json.load(open('/tmp/apify_resp_$$.json')); print(d.get('data',{}).get('status','UNKNOWN'))")

  case "$STATUS" in
    SUCCEEDED)
      echo "[apify_fetch] Actor finished successfully after ${ELAPSED}s" >&2
      break
      ;;
    FAILED|ABORTED|TIMED-OUT)
      echo "[apify_fetch] ERROR: Actor ended with status $STATUS" >&2
      cat /tmp/apify_resp_$$.json >&2
      rm -f /tmp/apify_resp_$$.json
      exit 1
      ;;
    *)
      echo "[apify_fetch] Status: $STATUS (${ELAPSED}s / ${TIMEOUT_SECS}s)" >&2
      ;;
  esac
done

if [ "$STATUS" != "SUCCEEDED" ]; then
  echo "[apify_fetch] ERROR: Timed out after ${TIMEOUT_SECS}s (last status: $STATUS)" >&2
  rm -f /tmp/apify_resp_$$.json
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: Fetch dataset
# ---------------------------------------------------------------------------
DATASET_ID=$(python3 -c "import json,sys; d=json.load(open('/tmp/apify_resp_$$.json')); print(d.get('data',{}).get('defaultDatasetId',''))")
rm -f /tmp/apify_resp_$$.json

if [ -z "$DATASET_ID" ]; then
  echo "[apify_fetch] WARNING: No defaultDatasetId, writing empty array" >&2
  echo "[]" > "$OUTPUT_PATH"
  exit 0
fi

echo "[apify_fetch] Fetching dataset: $DATASET_ID" >&2
DATASET_URL="${APIFY_BASE}/datasets/${DATASET_ID}/items?token=${TOKEN}&format=json&clean=1"

HTTP_CODE=$(_apify_call "GET" "$DATASET_URL")
if [ "$HTTP_CODE" != "200" ]; then
  echo "[apify_fetch] ERROR: Failed to fetch dataset (HTTP $HTTP_CODE)" >&2
  rm -f /tmp/apify_resp_$$.json
  exit 1
fi

# Write dataset items to output
python3 -c "
import json
data = json.load(open('/tmp/apify_resp_$$.json'))
with open('$OUTPUT_PATH', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f'[apify_fetch] Wrote {len(data)} items to $OUTPUT_PATH')
" >&2

rm -f /tmp/apify_resp_$$.json
echo "[apify_fetch] Done." >&2
exit 0
