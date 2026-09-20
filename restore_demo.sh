#!/bin/bash
set -e
cd "$(dirname "$0")"

LATEST=$(ls -1td artifacts/snapshots/*/ 2>/dev/null | head -n 1)
if [ -z "$LATEST" ]; then
    echo "No snapshots found."
    exit 1
fi

echo "Restoring from snapshot: $LATEST"
cp "$LATEST"*.json artifacts/ 2>/dev/null || true
cp "$LATEST"decision_log.jsonl artifacts/ 2>/dev/null || true
if [ -f "$LATEST"validation_report.json ]; then
    cp "$LATEST"validation_report.json eval/ 2>/dev/null || true
fi
echo "Restore complete."
