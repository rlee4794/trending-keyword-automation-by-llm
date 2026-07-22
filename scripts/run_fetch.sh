#!/usr/bin/env bash
# run_fetch.sh — Dispatch all Apify actors for a region with concurrency control.
#
# Reads config/apify_actors_v1.json and config/social_listening_v1.json,
# builds a job list, then runs them with xargs -P to respect Apify's
# concurrent actor limit (32).
#
# Usage:
#   run_fetch.sh --date 2026-07-09 --region hk
#   run_fetch.sh --date 2026-07-09 --region tw
#   run_fetch.sh --date 2026-07-09 --region hk --max-concurrent 30
#
# Environment:
#   APIFY_TOKEN — Apify API authentication (required)
#
# Output:
#   runs/{date}/raw/_apify/{region}/*.json

set -euo pipefail

DATE=""
REGION=""
MAX_CONCURRENT="${MAX_CONCURRENT:-30}"

usage() {
    echo "Usage: $0 --date YYYY-MM-DD --region hk|tw [--max-concurrent N]" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --date)       DATE="$2"; shift 2 ;;
        --region)     REGION="$2"; shift 2 ;;
        --max-concurrent) MAX_CONCURRENT="$2"; shift 2 ;;
        *)            usage ;;
    esac
done

[[ -z "$DATE" || -z "$REGION" ]] && usage
[[ "$REGION" != "hk" && "$REGION" != "tw" ]] && { echo "ERROR: region must be 'hk' or 'tw'" >&2; exit 1; }
[[ -z "${APIFY_TOKEN:-}" ]] && { echo "ERROR: APIFY_TOKEN not set" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RUN_DIR="${PROJECT_DIR}/runs/${DATE}/raw/_apify/${REGION}"
mkdir -p "$RUN_DIR"

APIFY_CFG="${PROJECT_DIR}/config/apify_actors_v1.json"
SOCIAL_CFG="${PROJECT_DIR}/config/social_listening_v1.json"
FETCH_SCRIPT="${SCRIPT_DIR}/apify_fetch.sh"

JOB_FILE="/tmp/apify_jobs_${DATE}_${REGION}.txt"
> "$JOB_FILE"   # truncate / create

# ── Helpers ──────────────────────────────────────────────────────────

_build_job() {
    local actor_id="$1"
    local input_json="$2"
    local output_path="$3"
    printf '%s|%s|%s\n' "$actor_id" "$input_json" "$output_path" >> "$JOB_FILE"
}

_run_job() {
    # $1 = "actor_id|input_json|output_path"
    local line="$1"
    local actor_id input_json output_path
    actor_id="${line%%|*}"
    local rest="${line#*|}"
    input_json="${rest%|*}"
    output_path="${line##*|}"

    echo "[run_fetch] Dispatching: $output_path" >&2
    bash "$FETCH_SCRIPT" "$actor_id" "$input_json" "$output_path"
}

export FETCH_SCRIPT APIFY_TOKEN
export -f _run_job

# ── Build job list ────────────────────────────────────────────────────

ACTORS=$(python3 -c "
import json, sys

with open('${APIFY_CFG}') as f:
    actors = json.load(f)
with open('${SOCIAL_CFG}') as f:
    social = json.load(f)
with open('config/threshold.json') as f:
    threshold = json.load(f)
google_enabled = threshold.get('google', {}).get('enabled', True)

region = '${REGION}'
run_dir = '${RUN_DIR}'

jobs = []

# --- Google Trends ---
if google_enabled:
    if region == 'hk':
        google_cfg = actors['google']
        input_json = json.dumps(google_cfg['input'])
        jobs.append((google_cfg['actor_id'], input_json, f'{run_dir}/google_apify_raw.json'))
    else:
        google_cfg = actors['google_taiwan']
        input_json = json.dumps(google_cfg['input'])
        jobs.append((google_cfg['actor_id'], input_json, f'{run_dir}/google_apify_raw.json'))
else:
    print('google: DISABLED (config/threshold.json → google.enabled=false)', file=sys.stderr)

# --- Instagram hashtags (HK only) ---
if region == 'hk':
    ig_cfg = actors['instagram']
    for hashtag in social['broad_seeds']['instagram']:
        inp = dict(ig_cfg['input'])
        inp['hashtag'] = hashtag.lstrip('#')
        input_json = json.dumps(inp)
        # Sanitize filename: #hkfood → ig_hkfood_apify_raw.json
        safe_name = hashtag.lstrip('#').replace('/', '_')
        jobs.append((ig_cfg['actor_id'], input_json, f'{run_dir}/ig_{safe_name}_apify_raw.json'))

# --- Instagram users ---
user_cfg = actors['instagram_users']
users_key = 'instagram_users_taiwan' if region == 'tw' else 'instagram_users'
file_prefix = 'ig_tw_user_' if region == 'tw' else 'ig_user_'
for username in social['broad_seeds'][users_key]:
    inp = dict(user_cfg['input'])
    inp['username'] = username
    input_json = json.dumps(inp)
    jobs.append((user_cfg['actor_id'], input_json, f'{run_dir}/{file_prefix}{username}_apify_raw.json'))

# --- Threads (HK only) ---
if region == 'hk':
    threads_cfg = actors['threads']
    inp = dict(threads_cfg['input'])
    inp['keywords'] = social['broad_seeds']['threads_search_queries']
    input_json = json.dumps(inp)
    jobs.append((threads_cfg['actor_id'], input_json, f'{run_dir}/threads_apify_raw.json'))

# Write job file
with open('${JOB_FILE}', 'w') as f:
    for actor_id, input_json, output_path in jobs:
        f.write(f'{actor_id}|{input_json}|{output_path}\n')

print(f'Jobs: {len(jobs)}')
" 2>/dev/null)

JOB_COUNT=$(wc -l < "$JOB_FILE")
echo "[run_fetch] ${REGION}: ${JOB_COUNT} jobs, max-concurrent=${MAX_CONCURRENT}"

# ── Dispatch with xargs -P ────────────────────────────────────────────

xargs -d '\n' -P "$MAX_CONCURRENT" -I {} bash -c '_run_job "$@"' _ {} < "$JOB_FILE"

# ── Verify all expected outputs ──────────────────────────────────────

FAILED=""
for f in "$RUN_DIR"/*_apify_raw.json; do
    [ -s "$f" ] && continue
    FAILED="$FAILED  $(basename "$f")\n"
done

if [ -n "$FAILED" ]; then
    FAILED_COUNT=$(echo -e "$FAILED" | grep -c .)
    printf "[run_fetch] ERROR: ${REGION}: %d platform(s) failed to produce output:\n%b" \
           "$FAILED_COUNT" "$FAILED" >&2
    echo "[run_fetch] Pipeline aborted — fix failing actors before retrying." >&2
    exit 1
fi

# Cleanup
rm -f "$JOB_FILE"

echo "[run_fetch] ${REGION}: All ${JOB_COUNT} outputs verified."
