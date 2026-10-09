#!/usr/bin/env bash
# Usage: publish-sync.sh <result-file> <branch>
#
# Act on the output of sync-upstream.sh: push <branch> and open a "sync ready"
# issue with a compare link, or open a conflict issue. Skip when an earlier sync
# PR, ready issue, or conflict issue is still open.
# stdout: ready-issue-opened, conflict-issue-opened, skipped-open-sync,
# skipped-open-conflict, or nothing-to-do.
# Exit status: 0 done, 2 usage error or unknown result.
# Environment: GITHUB_REPOSITORY (owner/name, set by GitHub Actions).
set -euo pipefail

usage() { sed -n '2,10p' "$0" | sed -E 's/^# ?//'; }

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 2 || ! -f "$1" ]]; then
  usage >&2
  exit 2
fi
result_file=$1
branch=$2
result=$(head -n 1 "$result_file")
ready_title="Upstream sync ready"
conflict_title="Upstream sync conflict"

open_issue_count() {
  gh issue list --state open --search "in:title \"$1\"" --json number --jq length
}

case "$result" in
  uptodate)
    echo nothing-to-do
    ;;
  merged)
    repo=${GITHUB_REPOSITORY:?publish-sync: set GITHUB_REPOSITORY to owner/name}
    open_prs=$(gh pr list --state open --search "head:sync/upstream-" --json number --jq length)
    open_ready=$(open_issue_count "$ready_title")
    if [[ "$open_prs" != "0" || "$open_ready" != "0" ]]; then
      echo skipped-open-sync
      exit 0
    fi
    git push --set-upstream origin "$branch"
    # A push by GITHUB_TOKEN starts no CI run, but a workflow_dispatch run does.
    gh workflow run ci.yml --ref "$branch"
    # The workflow does not open the PR: that needs the repo setting that also lets
    # Actions approve PRs, which would let a write-access account approve its own PR.
    gh issue create --title "$ready_title: $branch" \
      --body "Upstream main merged cleanly into \`$branch\`. CI runs on the branch.

Open the PR: https://github.com/$repo/compare/main...$branch

Review the upstream changes before you merge. Close this issue when the PR is open."
    echo ready-issue-opened
    ;;
  conflict)
    open=$(open_issue_count "$conflict_title")
    if [[ "$open" != "0" ]]; then
      echo skipped-open-conflict
      exit 0
    fi
    # The backticks are Markdown code marks for the issue body, not command substitution.
    # shellcheck disable=SC2016
    files=$(tail -n +2 "$result_file" | sed 's/^/- `/; s/$/`/')
    gh issue create --title "$conflict_title" \
      --body "Merging upstream/main into main conflicts in these files:

$files

Resolve it by hand in a branch with a merge commit (FORK.md, Upstream sync)."
    echo conflict-issue-opened
    ;;
  *)
    echo "publish-sync: unknown result '$result' in $result_file." >&2
    echo "Expected uptodate, merged, or conflict." >&2
    exit 2
    ;;
esac
