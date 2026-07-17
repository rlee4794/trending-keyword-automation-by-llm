#!/usr/bin/env bash
# run_fetch_only.sh — Step 1 only: fetch + normalize for HK and TW independently.
#
# Each region runs independently — if one fails, the other still proceeds.
# Abort criteria: run_fetch.sh exits non-zero (Apify actors failed) for that region.
#
# Usage:
#   run_fetch_only.sh --date 2026-07-12
#   run_fetch_only.sh                    # defaults to yesterday
#
# Environment:
#   APIFY_TOKEN — Apify API authentication (required)

set -euo pipefail

DATE=""

usage() {
    echo "Usage: $0 [--date YYYY-MM-DD]" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --date) DATE="$2"; shift 2 ;;
        *)      usage ;;
    esac
done

[[ -z "$DATE" ]] && DATE=$(date -d "yesterday" +%Y-%m-%d)
[[ -z "${APIFY_TOKEN:-}" ]] && { echo "ERROR: APIFY_TOKEN not set" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RUN_FETCH="${SCRIPT_DIR}/run_fetch.sh"
NORMALIZE="${SCRIPT_DIR}/normalize_raw.py"
SOCIAL_CFG="${PROJECT_DIR}/config/social_listening_v1.json"

echo "============================================"
echo "[fetch_only] Date: $DATE"
echo "[fetch_only] Start: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================"

HK_OK=0
TW_OK=0

# ── HK ────────────────────────────────────────────────────────────────

echo ""
echo ">>> [HK] Starting fetch..."
if bash "$RUN_FETCH" --date "$DATE" --region hk; then
    echo ">>> [HK] Fetch OK, normalizing..."
    if python3 "$NORMALIZE" --date "$DATE" --run-dir "${PROJECT_DIR}/runs/${DATE}" --config "$SOCIAL_CFG"; then
        echo ">>> [HK] Normalize OK"
        HK_OK=1
    else
        echo "!!! [HK] Normalize FAILED" >&2
    fi
else
    echo "!!! [HK] Fetch FAILED (Apify actors did not complete)" >&2
fi

# ── TW ────────────────────────────────────────────────────────────────

echo ""
echo ">>> [TW] Starting fetch..."
if bash "$RUN_FETCH" --date "$DATE" --region tw; then
    echo ">>> [TW] Fetch OK, normalizing..."
    if python3 "$NORMALIZE" --date "$DATE" --run-dir "${PROJECT_DIR}/runs/${DATE}" --config "$SOCIAL_CFG"; then
        echo ">>> [TW] Normalize OK"
        TW_OK=1
    else
        echo "!!! [TW] Normalize FAILED" >&2
    fi
else
    echo "!!! [TW] Fetch FAILED (Apify actors did not complete)" >&2
fi

# ── Summary ───────────────────────────────────────────────────────────

echo ""
echo "============================================"
echo "[fetch_only] Summary:"
echo "  HK: $([ "$HK_OK" -eq 1 ] && echo '✅ OK' || echo '❌ FAILED')"
echo "  TW: $([ "$TW_OK" -eq 1 ] && echo '✅ OK' || echo '❌ FAILED')"
echo "[fetch_only] End: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "============================================"

if [ "$HK_OK" -eq 0 ] && [ "$TW_OK" -eq 0 ]; then
    exit 1
fi
exit 0
