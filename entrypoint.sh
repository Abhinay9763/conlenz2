#!/bin/bash
set -e

# GitHub Actions passes inputs as environment variables: INPUT_<INPUT_NAME>
MODE="${INPUT_MODE:-deep}"
PATH_TO_SCAN="${INPUT_PATH:-${GITHUB_WORKSPACE}}"
TOKEN="${INPUT_TOKEN:-}"

# Expose API URL to the python process if provided by the user
export CONLENZ_API_URL="${CONLENZ_API_URL:-http://localhost:8000}"

echo "Starting Conlenz Scan in mode: $MODE"
echo "Scanning path: $PATH_TO_SCAN"

# Change directory to where the conlenz app is installed inside the Docker container
cd /app

# Run the CLI scanner
python -m app.cli_scan \
    --path "$PATH_TO_SCAN" \
    --mode "$MODE" \
    --token "$TOKEN" \
    --recipient "$REPORT_RECIPIENT" \
    --out "${GITHUB_WORKSPACE}/reports"

echo "Scan complete."
