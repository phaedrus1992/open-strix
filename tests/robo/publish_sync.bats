#!/usr/bin/env bats

setup() {
  SCRIPT="$BATS_TEST_DIRNAME/../../.github/scripts/publish-sync.sh"
  STUBS="$BATS_TEST_TMPDIR/bin"
  CALLS="$BATS_TEST_TMPDIR/calls"
  mkdir -p "$STUBS"
  : >"$CALLS"
  for cmd in gh git; do
    cat >"$STUBS/$cmd" <<EOF
#!/usr/bin/env bash
echo "$cmd \$*" >>"$CALLS"
case "$cmd \$1 \$2" in
  "gh pr list") echo "\${STUB_OPEN_PRS:-0}" ;;
  "gh issue list")
    case "\$*" in
      *"Upstream sync ready"*) echo "\${STUB_OPEN_READY:-0}" ;;
      *) echo "\${STUB_OPEN_ISSUES:-0}" ;;
    esac
    ;;
esac
EOF
    chmod +x "$STUBS/$cmd"
  done
  export PATH="$STUBS:$PATH" CALLS GITHUB_REPOSITORY=owner/open-strix
  RESULT="$BATS_TEST_TMPDIR/result"
}

@test "--help exits 0" {
  run "$SCRIPT" --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"Usage: publish-sync.sh"* ]]
}

@test "missing result file exits 2" {
  run "$SCRIPT" "$BATS_TEST_TMPDIR/nope" sync/upstream-20261012
  [ "$status" -eq 2 ]
}

@test "uptodate does nothing" {
  echo uptodate >"$RESULT"
  run "$SCRIPT" "$RESULT" sync/upstream-20261012
  [ "$status" -eq 0 ]
  [ "$output" = "nothing-to-do" ]
  ! grep -q "git push" "$CALLS"
}

@test "merged pushes, starts ci, and opens a ready issue with a compare link" {
  echo merged >"$RESULT"
  run "$SCRIPT" "$RESULT" sync/upstream-20261012
  [ "$status" -eq 0 ]
  [ "$output" = "ready-issue-opened" ]
  grep -q "git push --set-upstream origin sync/upstream-20261012" "$CALLS"
  grep -q "gh workflow run ci.yml --ref sync/upstream-20261012" "$CALLS"
  grep -q "gh issue create --title Upstream sync ready: sync/upstream-20261012" "$CALLS"
  grep -q "https://github.com/owner/open-strix/compare/main...sync/upstream-20261012" "$CALLS"
  ! grep -q "gh pr create" "$CALLS"
}

@test "merged with an open sync PR skips" {
  echo merged >"$RESULT"
  STUB_OPEN_PRS=1 run "$SCRIPT" "$RESULT" sync/upstream-20261012
  [ "$status" -eq 0 ]
  [ "$output" = "skipped-open-sync" ]
  ! grep -q "git push" "$CALLS"
}

@test "merged with an open ready issue skips" {
  echo merged >"$RESULT"
  STUB_OPEN_READY=1 run "$SCRIPT" "$RESULT" sync/upstream-20261012
  [ "$status" -eq 0 ]
  [ "$output" = "skipped-open-sync" ]
  ! grep -q "git push" "$CALLS"
}

@test "conflict opens an issue that lists the files" {
  printf 'conflict\nopen_strix/app.py\n' >"$RESULT"
  run "$SCRIPT" "$RESULT" sync/upstream-20261012
  [ "$status" -eq 0 ]
  [ "$output" = "conflict-issue-opened" ]
  grep -q "gh issue create --title Upstream sync conflict" "$CALLS"
  grep -q "open_strix/app.py" "$CALLS"
}

@test "conflict with an open conflict issue skips" {
  printf 'conflict\nopen_strix/app.py\n' >"$RESULT"
  STUB_OPEN_ISSUES=1 run "$SCRIPT" "$RESULT" sync/upstream-20261012
  [ "$status" -eq 0 ]
  [ "$output" = "skipped-open-conflict" ]
  ! grep -q "gh issue create" "$CALLS"
}

@test "unknown result exits 2" {
  echo surprise >"$RESULT"
  run "$SCRIPT" "$RESULT" sync/upstream-20261012
  [ "$status" -eq 2 ]
  [[ "$output" == *"surprise"* ]]
}
