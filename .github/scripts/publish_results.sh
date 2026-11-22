#!/usr/bin/env bash
# Publish the local results/ directory to the orphan `results` branch as a
# single commit (force-push). Used by .github/workflows/clip.yml:
#   - at the start: results/ holds run_status.json ("running")
#   - at the end:   results/ holds run_status.json + liveclip_clips.json +
#                   clip MP4s/SRTs + the export ZIP
# The Studio page reads that branch from raw.githubusercontent.com, so no
# file ever needs to be downloaded or uploaded by hand.
# Usage: bash .github/scripts/publish_results.sh "<commit message>"
set -euo pipefail
MSG="${1:-results}"

# If nothing was produced yet (e.g. the config step failed), still publish
# an error status so the page can say what happened instead of hanging.
if [ ! -f "results/run_status.json" ]; then
  mkdir -p results
  printf '{"status": "error", "source_url": "", "clips": 0, "message": "The run failed before clipping started."}' > results/run_status.json
fi

REPO="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
TMP="$(mktemp -d)"
git clone --quiet "$REPO" "$TMP"
cd "$TMP"
git config user.name "LiveClip Bot"
git config user.email "actions@github.com"
git checkout --orphan results
git rm -rf . >/dev/null 2>&1 || true
cp -r "${GITHUB_WORKSPACE}/results/." .
git add -A
git commit -qm "$MSG"
git push --force origin results
echo "published results branch: $MSG"
