#!/usr/bin/env bash
# Publish the local results/ directory to the orphan `results` branch as a
# single commit (force-push). Used by .github/workflows/clip.yml:
#   - at the start: results/ holds run_status.json ("running")
#   - at the end:   results/ holds run_status.json + liveclip_clips.json +
#                   clip MP4s/SRTs + the export ZIP
# The Studio page reads that branch from raw.githubusercontent.com, so no
# file ever needs to be downloaded or uploaded by hand.
#
# Auth: this uses the checkout's own credentials (actions/checkout persists
# the workflow token in the repo's git config, which linked worktrees share),
# so no token is handled here and no token URL is built. Do NOT go back to
# a token URL: cloning a public repo works anonymously, so a bad token only
# fails at push time with "Invalid username or token".
# Usage: bash .github/scripts/publish_results.sh "<commit message>"
set -euo pipefail
MSG="${1:-results}"

# If nothing was produced yet (e.g. the config step failed), still publish
# an error status so the page can say what happened instead of hanging.
if [ ! -f "results/run_status.json" ]; then
  mkdir -p results
  printf '{"status": "error", "source_url": "", "clips": 0, "message": "The run failed before clipping started."}' > results/run_status.json
fi

WORKTREE="/tmp/liveclip-results-work"
if [ ! -d "$WORKTREE" ]; then
  git worktree add --detach "$WORKTREE" >/dev/null
  cd "$WORKTREE"
  git fetch origin results 2>/dev/null || true
  if git show-ref --verify --quiet refs/remotes/origin/results; then
    git checkout -b results origin/results
  else
    git checkout --orphan results
  fi
else
  cd "$WORKTREE"
  git checkout results 2>/dev/null || git checkout --orphan results
fi

git rm -rf . >/dev/null 2>&1 || true
cp -r "${GITHUB_WORKSPACE}/results/." .
git add -A
git -c user.name="LiveClip Bot" -c user.email="actions@github.com" commit -qm "$MSG"
git push --force origin results
echo "published results branch: $MSG"
