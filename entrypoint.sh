#!/bin/sh
set -eu
if [ "${YDOWN_MODE:-extractor}" = "download-site" ]; then
    exec uvicorn download_site:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
fi
# Optional operator-provided cookies; no implicit third-party account registration.
if [ -n "${YOUTUBE_COOKIES:-}" ]; then
    umask 077
    mkdir -p "${YDOWN_DATA_DIR:-/data}"
    printf '%s\n' "$YOUTUBE_COOKIES" > "${YDOWN_DATA_DIR:-/data}/cookies.txt"
    export YDOWN_COOKIE_FILE="${YDOWN_DATA_DIR:-/data}/cookies.txt"
fi
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
