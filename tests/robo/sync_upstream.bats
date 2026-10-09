#!/usr/bin/env bats

setup() {
  export GIT_CONFIG_NOSYSTEM=1
  export GIT_CONFIG_GLOBAL="$BATS_TEST_TMPDIR/gitconfig"
  git config --global user.name test
  git config --global user.email test@example.invalid
  git config --global commit.gpgsign false
  git config --global init.defaultBranch main
  SCRIPT="$BATS_TEST_DIRNAME/../../.github/scripts/sync-upstream.sh"
  UP="$BATS_TEST_TMPDIR/upstream"
  FORK="$BATS_TEST_TMPDIR/fork"
  git init --quiet "$UP"
  echo base >"$UP/file.txt"
  git -C "$UP" add file.txt && git -C "$UP" commit --quiet -m base
  git clone --quiet "$UP" "$FORK"
  git -C "$FORK" remote rename origin upstream
}

@test "--help prints usage and exits 0" {
  run "$SCRIPT" --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"Usage: sync-upstream.sh"* ]]
}

@test "wrong argument count exits 2" {
  run "$SCRIPT" only-one
  [ "$status" -eq 2 ]
}

@test "unknown ref exits 2 and names the ref" {
  cd "$FORK"
  run "$SCRIPT" upstream/nope sync/x
  [ "$status" -eq 2 ]
  [[ "$output" == *"upstream/nope"* ]]
}

@test "no new upstream commits prints uptodate" {
  cd "$FORK"
  run "$SCRIPT" upstream/main sync/x
  [ "$status" -eq 0 ]
  [ "$output" = "uptodate" ]
  run git rev-parse --verify --quiet sync/x
  [ "$status" -ne 0 ]
}

@test "new upstream commit is merged into a new branch with a merge commit" {
  echo more >>"$UP/other.txt" && git -C "$UP" add other.txt && git -C "$UP" commit --quiet -m more
  echo fork >"$FORK/fork.txt"
  git -C "$FORK" add fork.txt && git -C "$FORK" commit --quiet -m fork
  cd "$FORK" && git fetch --quiet upstream
  run "$SCRIPT" upstream/main sync/x
  [ "$status" -eq 0 ]
  [ "$output" = "merged" ]
  [ "$(git branch --show-current)" = "sync/x" ]
  [ "$(git rev-list --parents -n 1 HEAD | wc -w)" -eq 3 ]
}

@test "conflict prints the paths, exits 3, and leaves no merge in progress" {
  echo upstream-side >"$UP/file.txt" && git -C "$UP" commit --quiet -am up
  echo fork-side >"$FORK/file.txt" && git -C "$FORK" commit --quiet -am fork
  cd "$FORK" && git fetch --quiet upstream
  run "$SCRIPT" upstream/main sync/x
  [ "$status" -eq 3 ]
  [ "${lines[0]}" = "conflict" ]
  [ "${lines[1]}" = "file.txt" ]
  [ ! -f .git/MERGE_HEAD ]
}
