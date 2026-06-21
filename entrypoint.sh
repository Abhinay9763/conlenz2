#!/bin/bash
set -e

# GitHub Actions passes inputs as environment variables: INPUT_<INPUT_NAME>
MODE="${INPUT_MODE:-deep}"
PATH_TO_SCAN="${INPUT_PATH:-${GITHUB_WORKSPACE}}"

echo "Starting Conlenz Scan in mode: $MODE"
echo "Scanning path: $PATH_TO_SCAN"

# Run the CLI scanner
python -m app.cli_scan \
    --path "$PATH_TO_SCAN" \
    --mode "$MODE" \
    --out "${GITHUB_WORKSPACE}/reports"

echo "Scan complete."
