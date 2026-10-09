#!/usr/bin/env bash
# Usage: sync-upstream.sh <upstream-ref> <branch>
#
# Merge <upstream-ref> into a new local <branch> cut from HEAD.
# stdout: "uptodate", "merged", or "conflict" followed by one conflicting path per line.
# Exit status: 0 uptodate or merged, 2 usage error or unknown ref, 3 conflict.
set -euo pipefail

usage() { sed -n '2,6p' "$0" | sed -E 's/^# ?//'; }

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 2 ]]; then
  usage >&2
  exit 2
fi
upstream_ref=$1
branch=$2

if ! git rev-parse --verify --quiet "${upstream_ref}^{commit}" >/dev/null; then
  echo "sync-upstream: cannot resolve '${upstream_ref}'. Run 'git fetch upstream' first." >&2
  exit 2
fi

if git merge-base --is-ancestor "$upstream_ref" HEAD; then
  echo uptodate
  exit 0
fi

git switch --quiet -c "$branch"
if git merge --quiet --no-edit --no-ff "$upstream_ref" >/dev/null 2>&1; then
  echo merged
  exit 0
fi

echo conflict
git diff --name-only --diff-filter=U
git merge --abort
exit 3
